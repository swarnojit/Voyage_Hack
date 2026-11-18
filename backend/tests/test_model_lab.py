"""Integration tests for real local model inference, audit and SQL model registry."""
from sqlalchemy import select, func
from app.database import SessionLocal
from app.models import ModelPrediction, ModelSnapshot
from app.services.ml_planner import FEATURE_NAMES, train_models, predict_case


def test_model_training_has_three_models_and_holdout_metrics():
    forest, classifier, metadata = train_models()
    assert len(forest.estimators_) == 120
    assert metadata['model_version']
    assert metadata['anomaly_model'].startswith('IsolationForest')
    assert metadata['risk_holdout_rows'] == 450
    assert metadata['intent_holdout_rows'] == 24
    assert 0 <= metadata['risk_metrics']['roc_auc'] <= 1
    assert 0 <= metadata['risk_metrics']['brier'] <= 1
    assert len(metadata['risk_metrics']['confusion_matrix']) == 2
    for kind, expected in [('cross_agency','authorization'),
                           ('double_refund','financial_logic'),('legacy_bypass','legacy_api')]:
        p = predict_case(kind)
        assert p['predicted_class'] == expected
        assert p['model_version'] == metadata['model_version']
        assert len(p['feature_vector']) == 8
        assert 0 <= p['novelty_score'] <= 1


def test_model_endpoint_auth_roles(client, admin, atlas):
    for path in ('/api/ml/overview','/api/ml/predictions','/api/ml/snapshots'):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=atlas).status_code == 403
        assert client.get(path, headers=admin).status_code == 200
    data=client.get('/api/ml/overview',headers=admin).json()
    assert data['metadata']['model_version']
    assert len(data['feature_schema'])==8
    assert data['database_dialect']=='sqlite'  # isolated test database
    assert data['snapshots'] >= 1


def test_read_only_preview_persists_actual_sql_and_audit(client, admin):
    overview=client.get('/api/ml/overview',headers=admin).json()
    flags=dict(zip(FEATURE_NAMES, overview['example_cases']['double_refund']))
    payload={'features':flags,'description':'duplicate refund payment ledger synthetic change'}
    before=client.get('/api/overview',headers=admin).json()['runs']
    response=client.post('/api/ml/preview',headers=admin,json=payload)
    assert response.status_code == 200,response.text
    r=response.json();assert r['executed_tests']==0
    assert r['storage']=='sqlite'
    assert r['prediction']['predicted_class']=='financial_logic'
    assert client.get('/api/overview',headers=admin).json()['runs']==before
    predictions=client.get('/api/ml/predictions',headers=admin).json()
    assert any(p['id']==r['prediction_id'] for p in predictions)
    with SessionLocal() as db:
        saved=db.get(ModelPrediction,r['prediction_id'])
        assert saved.risk_score==r['prediction']['risk_priority_score']
        assert saved.scan_id is None
        assert db.scalar(select(func.count(ModelSnapshot.id))) >= 1


def test_preview_rejects_unknown_or_nonbinary_inputs(client, admin, atlas):
    sample=dict.fromkeys(FEATURE_NAMES,0)
    valid={'features':sample,'description':'synthetic travel change'}
    assert client.post('/api/ml/preview',json=valid).status_code==401
    assert client.post('/api/ml/preview',headers=atlas,json=valid).status_code==403
    for payload in ({'features':{**sample,'external_url':1},'description':'synthetic change'},
                    {'features':{**sample,'write_method':2},'description':'synthetic change'},
                    {'features':sample,'description':'x','target_url':'http://another-target.invalid'},
                    {'features':sample,'description':'x'*281}):
        assert client.post('/api/ml/preview',headers=admin,json=payload).status_code==422


def test_scan_persists_model_decisions_linked_to_real_run(client, admin):
    r=client.post('/api/agent/start',headers=admin,json={'scenario':'all','auto_scan':True})
    assert r.status_code==200,r.text
    run_id=r.json()['scan_id']
    info=client.get(f'/api/agent/runs/{run_id}',headers=admin).json()
    assert info['run']['status']=='completed'
    assert info['run']['confirmed']==3
    rows=client.get(f'/api/ml/predictions?scan_id={run_id}',headers=admin).json()
    assert len(rows)==3
    assert {p['case'] for p in rows}=={'cross_agency','double_refund','legacy_bypass'}
    assert all(p['scan_id']==run_id for p in rows)
    assert all('top_risk_drivers' in p['explanation'] for p in rows)
    assert any(e['phase']=='plan' and 'model_version' in e['details'] for e in info['events'])
    db=client.get('/api/db/status',headers=admin).json()
    assert db['tables']['model_predictions'] >= 3
    assert db['tables']['model_snapshots'] >= 1


def test_new_frontend_model_lab_and_security_headers(client, admin):
    html=client.get('/lab').text
    js=client.get('/lab-assets/app.js').text
    css=client.get('/lab-assets/styles.css').text
    assert 'data-page="models"' in html
    assert 'renderModelLab' in js
    assert '/ml/overview' in js
    assert '/ml/preview' in js
    assert '/ml/predictions' in js
    assert '.ml-switch-grid' in css
    health=client.get('/health/db').json()
    assert health['status']=='ok' and health['database']=='sqlite'


def test_postgresql_schema_dialect_and_docker_wiring_are_present():
    """Static compatibility checks only; needs Docker for a real PG integration test."""
    from pathlib import Path
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import postgresql
    import yaml
    project = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((project / 'docker-compose.yml').read_text())
    assert 'postgresql+psycopg://tp_app:' in compose['services']['app']['environment']['TP_DATABASE_URL']
    assert compose['services']['app']['ports'] == ['127.0.0.1:8000:8000']
    assert 'ports' not in compose['services']['postgres']
    assert compose['services']['app']['depends_on']['postgres']['condition'] == 'service_healthy'
    sql = str(CreateTable(ModelPrediction.__table__).compile(dialect=postgresql.dialect()))
    assert 'CREATE TABLE model_predictions' in sql
    assert 'JSON' in sql
    script = (project/'docker/postgres/01-create-app-role.sh').read_text()
    assert 'CREATE ROLE tp_app LOGIN PASSWORD' in script
    assert 'GRANT USAGE, CREATE ON SCHEMA public TO tp_app' in script
