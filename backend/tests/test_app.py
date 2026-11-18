import pytest
from app.services.safety import SafetyGate, StopScan
from app.database import SessionLocal
from app.models import Booking, SimulatorConfig
from sqlalchemy import select


def deploy(client,admin,scenario):
    r=client.post('/api/demo/deploy',headers=admin,json={'scenario':scenario,'auto_scan':False})
    assert r.status_code==200,r.text
    return r.json()


def scan(client,admin):
    r=client.post('/api/agent/run',headers=admin)
    assert r.status_code==200,r.text
    runs=client.get('/api/agent/runs',headers=admin).json()
    assert runs[0]['status']=='completed', runs[0]
    assert runs[0]['requests_sent'] <= 40
    assert runs[0]['tests_run']==3
    return runs[0]


def test_health(client):
    assert client.get('/health').json()['external_scanning'] is False


def test_auth_protects_admin(client,admin,atlas):
    assert client.get('/api/overview').status_code==401
    assert client.get('/api/overview',headers=atlas).status_code==403
    assert client.get('/api/overview',headers=admin).status_code==200
    assert client.post('/api/auth/login',json={'username':'admin','password':'wrong'}).status_code==401


def test_agency_isolation_by_default(client,atlas,bluebird):
    mine=client.get('/sim/bookings',headers=atlas).json()[0]['id']
    theirs=client.get('/sim/bookings',headers=bluebird).json()[0]['id']
    assert client.get(f'/sim/bookings/{mine}',headers=atlas).status_code==200
    assert client.get(f'/sim/bookings/{mine}',headers=bluebird).status_code==403
    assert client.get(f'/sim/bookings/{theirs}',headers=atlas).status_code==403


def test_secure_refund_idempotent(client,atlas):
    with SessionLocal() as db:
        b=db.scalar(select(Booking).where(Booking.universe=='baseline'))
        test_booking=Booking(agency_id=b.agency_id,amount_paise=b.amount_paise,
                             universe='unit-test-idempotence',itinerary=b.itinerary)
        db.add(test_booking);db.commit();id_=test_booking.id;amount=b.amount_paise
    payload={'amount_paise':amount,'idempotency_key':'once-and-only-once'}
    r1=client.post(f'/sim/bookings/{id_}/refund',json=payload,headers=atlas)
    r2=client.post(f'/sim/bookings/{id_}/refund',json=payload,headers=atlas)
    assert r1.status_code==200 and r2.status_code==200
    assert r2.json()['idempotent_replay'] is True
    summary=client.get(f'/sim/bookings/{id_}/refund-total',headers=atlas).json()
    assert summary['refunded_paise']==amount


def test_secure_baseline_has_no_findings(client,admin):
    deploy(client,admin,'secure')
    result=scan(client,admin)
    assert result['confirmed']==0
    assert all(not v['violated'] for v in result['summary']['outcomes'].values())


def test_detects_cross_agency_with_reproducible_proof(client,admin):
    deploy(client,admin,'cross_agency')
    result=scan(client,admin)
    assert result['confirmed']==1
    findings=client.get('/api/agent/findings',headers=admin).json()
    relevant=[f for f in findings if f['scan_id']==result['id']]
    assert len(relevant)==1
    assert relevant[0]['kind']=='cross_agency'
    assert relevant[0]['proof']['details']['reproduced'] is True


def test_detects_double_refund_with_state_oracle(client,admin):
    deploy(client,admin,'double_refund')
    result=scan(client,admin)
    assert result['confirmed']==1
    details=result['summary']['outcomes']['double_refund']
    assert details['confirmed'] is True
    findings=client.get('/api/agent/findings',headers=admin).json()
    target=[f for f in findings if f['scan_id']==result['id']][0]
    assert target['proof']['details']['alternate_total_paise']>target['proof']['details']['paid_paise']


def test_legacy_api_discovered_and_flagged(client,admin):
    deploy(client,admin,'legacy_bypass')
    result=scan(client,admin)
    assert result['confirmed']==1
    inventory=client.get('/api/agent/inventory',headers=admin).json()
    assert any(x['classification']=='zombie' and 'legacy' in x['path_template'] for x in inventory)
    assert any(x['classification']=='shadow' and 'shortcut' in x['path_template'] for x in inventory)


def test_all_finds_three_issues_and_ticket(client,admin):
    deploy(client,admin,'all')
    result=scan(client,admin)
    assert result['confirmed']==3
    ids={f['kind'] for f in client.get('/api/agent/findings',headers=admin).json() if f['scan_id']==result['id']}
    assert ids=={'cross_agency','double_refund','legacy_bypass'}
    tickets=client.get('/api/agent/tickets',headers=admin).json()
    assert len(tickets)>=3
    assert all(t['state'] in {'needs-human-review','resolved'} for t in tickets)


def test_patch_then_retest_closes_finding(client,admin):
    deploy(client,admin,'double_refund')
    run=scan(client,admin)
    f=next(f for f in client.get('/api/agent/findings',headers=admin).json() if f['scan_id']==run['id'])
    deploy(client,admin,'secure')
    retest=client.post(f"/api/agent/findings/{f['id']}/retest",headers=admin)
    assert retest.status_code==200, retest.text
    updated=next(f for f in client.get('/api/agent/findings',headers=admin).json() if f['id']==f['id'])
    assert updated['status']=='fixed'
    ticket=next(t for t in client.get('/api/agent/tickets',headers=admin).json() if t['finding_id']==f['id'])
    assert ticket['state']=='resolved'


def test_kill_switch_prevents_agent(client,admin):
    response=client.post('/api/agent/pause',json={'paused':True},headers=admin)
    assert response.status_code==200
    assert client.post('/api/agent/run',headers=admin).status_code==409
    assert client.post('/api/demo/deploy',headers=admin,json={'scenario':'all','auto_scan':True}).status_code==409
    assert client.post('/api/agent/pause',json={'paused':False},headers=admin).status_code==200


@pytest.mark.asyncio
async def test_scope_gate_blocks_non_synthetic_traffic(client):
    gate=SafetyGate(run_id=1,max_requests=2,min_interval=0)
    with pytest.raises(StopScan):
        await gate.check('GET','https://another.host/api')
    with pytest.raises(StopScan):
        await gate.check('DELETE','/sim/bookings/1')
    with pytest.raises(StopScan):
        await gate.check('GET','/sim/../api/auth/me')
    assert gate.total==0


def test_report_contains_only_synthetic_evidence(client,admin):
    report=client.get('/api/agent/report',headers=admin).json()
    assert report['mode']=='synthetic-only'
    assert report['human_review'] is True
    assert 'in-process' in report['scope']


def test_offline_dashboard_static_assets(client):
    page=client.get('/lab')
    assert page.status_code==200 and 'TripParadox' in page.text
    assert "script-src 'self'" in page.headers['content-security-policy']
    assert client.get('/lab-assets/app.js').status_code==200
    assert client.get('/lab-assets/styles.css').status_code==200


def test_auto_scan_only_affected_route(client,admin):
    response=client.post('/api/demo/deploy',headers=admin,json={'scenario':'cross_agency','auto_scan':True})
    assert response.status_code==200
    latest=client.get('/api/agent/runs',headers=admin).json()[0]
    assert latest['deploy_id']==response.json()['deploy_id']
    assert latest['status']=='completed'
    assert latest['tests_run']==1
    assert latest['confirmed']==1


def test_human_approves_ticket_with_audited_note(client,admin):
    deploy(client,admin,'legacy_bypass')
    r=scan(client,admin)
    f=next(f for f in client.get('/api/agent/findings',headers=admin).json() if f['scan_id']==r['id'])
    ticket=next(t for t in client.get('/api/agent/tickets',headers=admin).json() if t['finding_id']==f['id'])
    response=client.post(f"/api/agent/tickets/{ticket['id']}/decision", headers=admin,
                         json={'decision':'approve','note':'Confirmed in approved synthetic staging environment'})
    assert response.status_code==200,response.text
    assert response.json()['state']=='approved_for_escalation'
    assert any(a['action']=='human_review' and a['metadata_']['ticket_id']==ticket['id']
               for a in client.get('/api/agent/audit',headers=admin).json())


def test_every_scanner_request_is_audited(client,admin):
    deploy(client,admin,'double_refund')
    run=scan(client,admin)
    audit=client.get('/api/agent/audit',headers=admin).json()
    events=[a for a in audit if a['action']=='synthetic_request' and a['metadata_']['scan_id']==run['id']]
    assert len(events)==run['requests_sent']
