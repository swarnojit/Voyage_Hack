"""Deployment-focused security/regression checks on the isolated fictional platform."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import asyncio
import itertools
import pytest
from sqlalchemy import create_engine, inspect, select, func, text
from app.database import SessionLocal
from app.main import app
from app.models import (Booking, Refund, ScanRun, Ticket, SimulatorConfig, ModelPrediction)
from app.migrations import migrate_demo_schema
from app.services.ml_planner import predict_features


def test_secure_concurrent_identical_refunds_only_paid_once(client, atlas, admin):
    hold = client.post('/sim/holds', headers=atlas, json={'offer_id':'DXB-102'})
    assert hold.status_code == 200
    bid = hold.json()['id']
    assert client.post(f'/sim/bookings/{bid}/pay', headers=atlas).status_code == 200

    def refund(_):
        return client.post(f'/sim/bookings/{bid}/refund', headers=atlas,
                           json={'amount_paise': 1000000, 'idempotency_key': 'safe-race-2026'})
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses=list(pool.map(refund, range(20)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses if r.status_code != 200]
    assert sum(not r.json()['idempotent_replay'] for r in responses) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(Refund.amount_paise)).where(Refund.booking_id==bid))==1000000
        assert db.scalar(select(func.count(Refund.id)).where(Refund.booking_id==bid))==1


def test_concurrent_distinct_keys_respect_payment_cap(client, atlas):
    bid=client.post('/sim/holds',headers=atlas,json={'offer_id':'SIN-201'}).json()['id']
    assert client.post(f'/sim/bookings/{bid}/pay',headers=atlas).status_code==200
    def attempt(i):
        return client.post(f'/sim/bookings/{bid}/refund',headers=atlas,
                           json={'amount_paise':380000,'idempotency_key':f'unique-key-{i}'})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(attempt,range(12)))
    assert sum(r.status_code==200 for r in results)==2, [r.status_code for r in results]
    assert all(r.status_code in (200,409) for r in results)
    with SessionLocal() as db:
        assert db.scalar(select(func.coalesce(func.sum(Refund.amount_paise),0)).where(Refund.booking_id==bid))==760000


def test_refund_key_immutability_and_hold_status(client,atlas):
    bid=client.post('/sim/holds',headers=atlas,json={'offer_id':'BKK-305'}).json()['id']
    path=f'/sim/bookings/{bid}/refund'
    assert client.post(path,headers=atlas,json={'amount_paise':900,'idempotency_key':'reusable-safe-key'}).status_code==409
    client.post(f'/sim/bookings/{bid}/pay',headers=atlas)
    assert client.post(path,headers=atlas,json={'amount_paise':900,'idempotency_key':'reusable-safe-key'}).status_code==200
    assert client.post(path,headers=atlas,json={'amount_paise':901,'idempotency_key':'reusable-safe-key'}).status_code==409
    assert client.post(path,headers=atlas,json={'amount_paise':900,'idempotency_key':'reusable-safe-key'}).json()['idempotent_replay'] is True


def test_agency_and_unauthenticated_refunds_denied(client,atlas,bluebird):
    booking=client.post('/sim/holds',headers=atlas,json={'offer_id':'DXB-102'}).json()['id']
    client.post(f'/sim/bookings/{booking}/pay',headers=atlas)
    route=f'/sim/bookings/{booking}/refund'
    payload={'amount_paise':500,'idempotency_key':'foreign-key-safe'}
    assert client.post(route,json=payload).status_code==401
    assert client.post(route,headers=bluebird,json=payload).status_code==403
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Refund.id)).where(Refund.booking_id==booking))==0


def test_exclusive_deployment_and_retest_reservations(client,admin):
    with SessionLocal() as db:
        run=ScanRun(status='queued');db.add(run);db.commit();rid=run.id
    try:
        assert client.post('/api/agent/start',headers=admin,json={'scenario':'all'}).status_code==409
        assert client.post('/api/demo/deploy',headers=admin,json={'scenario':'secure','auto_scan':False}).status_code==409
        assert client.post('/api/agent/run',headers=admin).status_code==409
        assert client.post('/api/agent/pause',headers=admin,json={'paused':True}).status_code==200
    finally:
        with SessionLocal() as db:
            run=db.get(ScanRun,rid);run.status='completed';db.commit()
        client.post('/api/agent/pause',headers=admin,json={'paused':False})


def test_model_preflight_exception_marks_reserved_run_failed(client,admin,monkeypatch):
    import app.services.ml_planner as planner
    def fail(_): raise RuntimeError('synthetic injected model setup failure')
    monkeypatch.setattr(planner,'prioritize',fail)
    response=client.post('/api/agent/start',headers=admin,json={'scenario':'all','auto_scan':True})
    assert response.status_code==200,response.text
    run=client.get(f"/api/agent/runs/{response.json()['scan_id']}",headers=admin).json()
    assert run['run']['status']=='error'
    assert any(e['title']=='Scanner preflight failed safely' for e in run['events'])
    assert client.get('/api/agent/runs',headers=admin).status_code==200
    assert client.post('/api/demo/deploy',headers=admin,json={'scenario':'secure','auto_scan':False}).status_code==200


def test_legacy_schema_auto_upgrade(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path/"legacy.db"}')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE refunds (id INTEGER PRIMARY KEY, booking_id INTEGER NOT NULL, amount_paise INTEGER NOT NULL, idempotency_key VARCHAR(140))'))
        conn.execute(text('CREATE TABLE tickets (id INTEGER PRIMARY KEY, state VARCHAR(20))'))
    migrate_demo_schema(engine)
    migrate_demo_schema(engine)
    insp=inspect(engine)
    assert 'safe_idempotency_key' in {x['name'] for x in insp.get_columns('refunds')}
    assert any(idx['unique'] for idx in insp.get_indexes('refunds'))
    engine.dispose()


def test_model_outputs_bounded_for_diverse_synthetic_features():
    descriptions=['fictional cross agency booking ownership','duplicate synthetic refund transaction',
                  'old legacy version deprecated api', 'new supplier staging change']
    vectors=list(itertools.product((0,1),repeat=8))
    for index in range(0,len(vectors),9):
        p=predict_features(list(vectors[index]),descriptions[index%len(descriptions)])
        assert 0 <= p['risk_priority_score'] <= 1
        assert 0 <= p['novelty_score'] <= 1
        assert 0 <= p['class_confidence'] <= 1
        assert 0.999 <= sum(p['class_distribution'].values()) <= 1.001
        assert p['priority_band'] in {'routine','elevated','high'}
        assert len(p['model_version'])==16


def test_postgres_ticket_state_fits_production_field():
    assert Ticket.__table__.c.state.type.length>=len('approved_for_escalation')
    assert 'uq_secure_refund_booking_key' in {c.name for c in Refund.__table__.constraints}


def test_signed_token_cannot_be_forged_or_promoted(client, atlas, admin):
    import jwt
    import os
    valid=atlas['Authorization'].split(' ',1)[1]
    payload=jwt.decode(valid,os.environ['TP_JWT_SECRET'],algorithms=['HS256'],audience='tripparadox')
    payload['role']='admin'
    modified=jwt.encode(payload,os.environ['TP_JWT_SECRET'],algorithm='HS256')
    assert client.get('/api/db/status',headers={'Authorization':'Bearer '+modified}).status_code==401
    assert client.get('/api/db/status',headers={'Authorization':'Bearer '+valid+'X'}).status_code==401
    assert client.get('/api/db/status',headers=admin).status_code==200


def test_strict_request_validation_rejects_mass_assignment(client,atlas,admin):
    # Extra keys never become privileged actions in normal travel workflows.
    bad_hold=client.post('/sim/holds',headers=atlas,
                         json={'offer_id':'DXB-102','role':'admin','agency_id':1})
    assert bad_hold.status_code==422
    assert client.post('/api/agent/start',headers=admin,
                       json={'scenario':'secure','target':'https://unapproved.invalid'}).status_code==422
    assert client.post('/api/agent/pause',headers=admin,json={'paused':'true'}).status_code==422
    assert client.post('/sim/holds',headers=atlas,
                       json={'offer_id':'DXB-102','agency_id':2}).status_code==403


def test_login_throttling_does_not_reveal_accounts(client):
    candidate='unknown-throttle-test-login'
    for _ in range(6):
        r=client.post('/api/auth/login',json={'username':candidate,'password':'wrong'})
        assert r.status_code==401 and r.json()['detail']=='Invalid credentials'
    assert client.post('/api/auth/login',json={'username':candidate,'password':'wrong'}).status_code==429


def test_trusted_host_and_scope_restrictions(client,admin):
    assert client.get('/api/overview',headers={**admin,'Host':'attacker.invalid'}).status_code==400
    assert client.post('/api/agent/start',headers=admin,json={'scenario':'not-approved'}).status_code==422
    assert client.get('/api/db/status').status_code==401
    assert client.get('/api/agent/security-check',headers=admin).status_code==200


@pytest.mark.asyncio
async def test_agent_stops_on_target_failure_and_audits_attempt(client):
    import httpx
    from app.services.engine import SafeASGI,actor_tokens
    from app.services.safety import SafetyGate,StopScan
    from app.models import Audit
    gate=SafetyGate(run_id=989898,max_requests=4,min_interval=0)
    async with SafeASGI(app,gate,actor_tokens()) as runner:
        async def synthetic_bad_response(method,path,**kwargs):
            return httpx.Response(503,request=httpx.Request(method,'http://synthetic-only.invalid'+path))
        runner.client.request=synthetic_bad_response
        with pytest.raises(StopScan,match='health threshold'):
            await runner.call('atlas_agent','GET','/sim/bookings/1')
    with SessionLocal() as db:
        row=db.scalars(select(Audit).where(Audit.action=='synthetic_request').order_by(Audit.id.desc())).first()
        assert row.metadata_['scan_id']==989898
        assert row.result=='503'


@pytest.mark.asyncio
async def test_agent_logs_exception_before_receiving_response(client):
    from app.services.engine import SafeASGI,actor_tokens
    from app.services.safety import SafetyGate
    from app.models import Audit
    gate=SafetyGate(run_id=989899,max_requests=2,min_interval=0)
    async with SafeASGI(app,gate,actor_tokens()) as runner:
        async def raise_network_error(*args,**kwargs):
            raise RuntimeError('injected in-process ASGI exception')
        runner.client.request=raise_network_error
        with pytest.raises(RuntimeError,match='injected'):
            await runner.call('atlas_agent','GET','/sim/bookings/1')
    with SessionLocal() as db:
        row=db.scalars(select(Audit).where(Audit.action=='synthetic_request').order_by(Audit.id.desc())).first()
        assert row.metadata_['scan_id']==989899
        assert row.result=='error' and row.metadata_['error_type']=='RuntimeError'


def test_secure_default_deployment_rejects_unsafe_scenarios(client, admin, monkeypatch):
    monkeypatch.setenv('TP_ALLOW_INTENTIONAL_FLAWS', 'false')
    for scenario in ('all', 'cross_agency', 'double_refund', 'legacy_bypass'):
        assert client.post('/api/agent/start', headers=admin, json={'scenario': scenario}).status_code == 403
        assert client.post('/api/demo/deploy', headers=admin, json={
            'scenario': scenario, 'auto_scan': False}).status_code == 403
    result = client.get('/api/overview', headers=admin).json()
    assert result['intentional_flaws_enabled'] is False
    assert not any(result['flaws'].values())
