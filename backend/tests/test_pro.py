"""Security controls, ML scheduling and full-stack synthetic workflow tests."""
import pytest
from app.services.ml_planner import predict_case, prioritize, train_models
from app.services.safety import SafetyGate, StopScan
from app.database import SessionLocal
from app.models import Booking, RunEvent
from sqlalchemy import select


def test_three_real_local_models_and_synthetic_disclaimer():
    risk, text, meta = train_models()
    assert len(risk.estimators_) == 120
    assert text.predict(['duplicate refund payment'])[0] == 'financial_logic'
    assert meta['training_source'] == 'GENERATED SYNTHETIC EXAMPLES ONLY'
    assert meta['external_inference'] is False
    assert 0 < meta['risk_holdout_accuracy_synthetic'] <= 1
    assert len(prioritize(['cross_agency','double_refund','legacy_bypass'])) == 3


def test_model_does_not_accept_unregistered_tests():
    with pytest.raises(ValueError):
        predict_case('http://outside.invalid')


def test_preview_plan_autonomous_models_and_code_paths(client, admin):
    r=client.get('/api/agent/plan?scenario=all',headers=admin)
    assert r.status_code == 200
    plan=r.json()
    assert len(plan['tests']) == 3
    assert len(plan['phases']) >= 8
    assert 'services.engine' in plan['phases'][4]['code']
    assert all('model' in x and len(x['feature_vector']) == 8 for x in plan['tests'])
    assert 'No internet target' in plan['constraints']
    assert client.get('/api/agent/plan?scenario=made-up',headers=admin).status_code == 422
    assert client.get('/api/agent/plan?scenario=all').status_code == 401


def test_model_information_authenticated(client, admin):
    assert client.get('/api/agent/model').status_code == 401
    result=client.get('/api/agent/model',headers=admin)
    assert result.status_code == 200
    assert result.json()['risk_model'].startswith('RandomForestClassifier')


def test_new_launch_auto_tests_and_persisted_trace(client, admin):
    r=client.post('/api/agent/start',headers=admin,json={'scenario':'all','auto_scan':True})
    assert r.status_code == 200, r.text
    run_id = r.json()['scan_id']
    detail=client.get(f'/api/agent/runs/{run_id}',headers=admin).json()
    assert detail['run']['status'] == 'completed'
    assert detail['run']['confirmed'] == 3
    assert detail['run']['requests_sent'] <= 40
    assert len(detail['evidence']) == 3
    phases={e['phase'] for e in detail['events']}
    assert {'init','ml','plan','inventory','fork','oracle','evidence','final'} <= phases
    assert any('risk_priority_score' in item for item in detail['run']['summary']['ml_ranked_plan'])
    with SessionLocal() as db:
        assert db.scalar(select(RunEvent).where(RunEvent.run_id == run_id)) is not None


def test_interactive_travel_clone_agency_and_idempotent_payment(client, admin, atlas, bluebird):
    catalog=client.get('/sim/catalog',headers=atlas)
    assert catalog.status_code == 200 and len(catalog.json()) == 3
    assert client.post('/sim/holds',headers=atlas,json={'offer_id':'DXB-102','agency_id':2}).status_code == 403
    hold=client.post('/sim/holds',headers=atlas,json={'offer_id':'DXB-102'})
    assert hold.status_code == 200,hold.text
    booking_id=hold.json()['id']
    assert client.get(f'/sim/bookings/{booking_id}',headers=bluebird).status_code == 403
    assert client.post(f'/sim/bookings/{booking_id}/pay',headers=bluebird).status_code == 403
    first=client.post(f'/sim/bookings/{booking_id}/pay',headers=atlas)
    second=client.post(f'/sim/bookings/{booking_id}/pay',headers=atlas)
    assert first.status_code == second.status_code == 200
    assert second.json()['idempotent_replay'] is True
    assert client.post(f'/sim/bookings/{booking_id}/cancel',headers=atlas).json()['status'] == 'cancelled'
    assert client.post(f'/sim/bookings/{booking_id}/cancel',headers=atlas).json()['idempotent_replay'] is True
    with SessionLocal() as db:
        assert db.get(Booking, booking_id).status == 'cancelled'


def test_sql_connectivity_and_security_assessment(client, admin):
    response=client.get('/api/db/status',headers=admin)
    assert response.status_code == 200
    assert response.json()['connected'] is True
    assert response.json()['tables']['bookings'] >= 2
    response=client.get('/api/agent/security-check',headers=admin)
    checks={a['name']:a['state'] for a in response.json()['checks']}
    assert checks['Argon2 password hashing'] == 'configured'
    assert checks['External scan boundary'] == 'enforced'
    assert 'not a certification' in response.json()['honest_assessment']
    assert client.get('/api/db/status').status_code == 401


@pytest.mark.asyncio
async def test_scanner_only_accepts_exact_in_process_routes(client):
    gate=SafetyGate(123, max_requests=1, min_interval=0)
    for path in ['/sim/catalog', '/sim/holds', '/sim/bookings/1/../../api/overview',
                 '/sim/bookings/1?q=2', '/api/overview', 'http://tbo.test.invalid']:
        with pytest.raises(StopScan):
            await gate.check('GET', path)
    assert gate.total == 0


def test_frontend_references_real_endpoints(client):
    js=client.get('/lab-assets/app.js').text
    assert '/agent/start' in js
    assert '/agent/plan' in js
    assert '/db/status' in js
    assert '/holds' in js
    assert 'window.localStorage' not in js


def test_http_security_headers_and_trusted_host(client):
    response=client.get('/lab')
    assert response.headers['x-frame-options']=='DENY'
    assert response.headers['x-content-type-options']=='nosniff'
    assert 'script-src' in response.headers['content-security-policy']
    assert response.headers['permissions-policy'].startswith('camera=')
    wrong_host=client.get('/health',headers={'host':'malicious.example'})
    assert wrong_host.status_code == 400


def test_role_protection_for_new_ui_endpoints(client,atlas,admin):
    for ep in ('/api/agent/plan', '/api/agent/model', '/api/db/status', '/api/agent/security-check'):
        assert client.get(ep,headers=atlas).status_code == 403
        assert client.get(ep,headers=admin).status_code == 200


def test_inventory_learns_from_live_synthetic_travel_activity(client, admin, atlas):
    hold=client.post('/sim/holds',headers=atlas,json={'offer_id':'SIN-201'})
    assert hold.status_code == 200
    routes=client.get('/api/agent/inventory',headers=admin).json()
    newly_seen=[r for r in routes if r['path_template']=='/sim/holds']
    assert newly_seen and newly_seen[0]['classification']=='shadow'
    assert newly_seen[0]['documented'] is False
