"""Repeatable release gate; isolated temp SQLite, never touches external hosts.

Example: python scripts/verify_release.py --safe 12 --planted 9 --fixes 3 --out /tmp/report.json
A passing release gate establishes only the INCLUDED synthetic invariants.
"""
from __future__ import annotations
import argparse
import json
import os
import secrets
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--safe',type=int,default=12)
parser.add_argument('--planted',type=int,default=9)
parser.add_argument('--fixes',type=int,default=3)
parser.add_argument('--out',type=Path,default=ROOT/'docs/release_gate_result.json')
opts=parser.parse_args()
assert 1<=opts.safe<=200 and 1<=opts.planted<=200 and 0<=opts.fixes<=200
sys.path.insert(0,str(ROOT/'backend'))
with tempfile.TemporaryDirectory(prefix='tripparadox-release-gate-') as tmp:
    os.environ.update({
      'TP_DATABASE_URL':f'sqlite:///{tmp}/release.db',
      'TP_DEMO_MODE':'true','TP_ALLOW_INTENTIONAL_FLAWS':'true',
      'TP_JWT_SECRET':secrets.token_urlsafe(48),
      'TP_ADMIN_PASSWORD':secrets.token_urlsafe(24),
      'TP_AGENCY_PASSWORD':secrets.token_urlsafe(24),
    })
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import SessionLocal
    from app.models import ScanRun, Finding, ModelPrediction, RunEvent
    from app.services.ml_planner import train_models
    from sqlalchemy import select,func
    timing=[];safe_ids=[];planted_ids=[];fix_ids=[]
    with TestClient(app) as client:
        resp=client.post('/api/auth/login',json={'username':'admin','password':os.environ['TP_ADMIN_PASSWORD']})
        assert resp.status_code==200,resp.text
        auth={'Authorization':f"Bearer {resp.json()['access_token']}"}
        meta_start=train_models()[2]
        def scan(scenario,expected):
            start=time.perf_counter()
            r=client.post('/api/agent/start',json={'scenario':scenario,'auto_scan':True},headers=auth)
            assert r.status_code==200,(scenario,r.status_code,r.text)
            rid=r.json()['scan_id']
            d=client.get(f'/api/agent/runs/{rid}',headers=auth).json()
            elapsed=time.perf_counter()-start
            timing.append(round(elapsed,4))
            run=d['run']
            assert run['status']=='completed',(rid,run)
            assert run['tests_run']==3,(rid,run)
            assert run['confirmed']==expected,(rid,run)
            assert run['requests_sent']<=40,(rid,run)
            phases={e['phase'] for e in d['events']}
            assert {'init','ml','plan','inventory','fork','oracle','evidence','final'} <= phases,phases
            preds=client.get(f'/api/ml/predictions?scan_id={rid}',headers=auth).json()
            assert len(preds)==3,(rid,len(preds))
            assert len(d['evidence'])==3
            assert sum(not e['passed'] for e in d['evidence'])==expected
            details=d['run']['summary']
            assert details['no_external_network'] is True
            return rid
        for i in range(opts.safe):
            safe_ids.append(scan('secure',0))
        for i in range(opts.planted):
            planted_ids.append(scan('all',3))
        for i in range(opts.fixes):
            # Real plant → secure patch → single-finding retest → fixed ticket.
            prior=scan('all',3)
            findings=client.get('/api/agent/findings',headers=auth).json()
            selected=next(f for f in findings if f['scan_id']==prior and f['kind']=='double_refund')
            safe_ids.append(scan('secure',0))
            ret=client.post(f"/api/agent/findings/{selected['id']}/retest",headers=auth)
            assert ret.status_code==200,ret.text
            rid=ret.json()['scan_id']
            d=client.get(f'/api/agent/runs/{rid}',headers=auth).json()
            assert d['run']['status']=='completed' and d['run']['confirmed']==0
            assert d['run']['tests_run']==1
            row=next(f for f in client.get('/api/agent/findings',headers=auth).json() if f['id']==selected['id'])
            assert row['status']=='fixed'
            fix_ids.append(rid)
        meta_end=train_models()[2]
        assert meta_end['risk_metrics']==meta_start['risk_metrics']
        assert meta_end['intent_metrics']==meta_start['intent_metrics']
        assert meta_end['model_version']==meta_start['model_version']
        with SessionLocal() as db:
            all_runs=db.scalar(select(func.count(ScanRun.id)))
            all_predictions=db.scalar(select(func.count(ModelPrediction.id)))
            pending=db.scalar(select(func.count(ScanRun.id)).where(ScanRun.status.in_(['queued','running'])))
            assert pending==0
        result={
            'timestamp_utc':datetime.now(timezone.utc).isoformat(),
            'target':'isolated in-process fictional travel API',
            'mode':'release-gate only, no external network or customer data',
            'safe_scenarios_scanned':len(safe_ids),
            'safe_scenario_confirmed_findings':0,
            'injected_vulnerable_scans':opts.planted+opts.fixes,
            'seeded_vulnerabilities_confirmed':(opts.planted+opts.fixes)*3,
            'seeded_vulnerabilities_expected':(opts.planted+opts.fixes)*3,
            'patch_and_retest_cycles':len(fix_ids),
            'runs_total':all_runs,
            'model_predictions_persisted':all_predictions,
            'pending_runs_after_gate':pending,
            'mean_synthetic_scan_seconds':round(statistics.mean(timing),4),
            'max_synthetic_scan_seconds':round(max(timing),4),
            'risk_model_version':meta_end['model_version'],
            'risk_model_synthetic_roc_auc':meta_end['risk_metrics']['roc_auc'],
            'threat_model_synthetic_macro_f1':meta_end['intent_metrics']['macro_f1'],
            'result':'PASS: covered secure invariants found no violations; planted scenarios still detected',
            'limits':'Does NOT certify zero vulnerabilities; does NOT test live TBO or PostgreSQL Docker runtime'
        }
    opts.out.parent.mkdir(parents=True,exist_ok=True)
    opts.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
