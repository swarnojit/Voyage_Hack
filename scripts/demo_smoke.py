"""Run a complete demonstration in-process; run with env loaded and backend installed.
Usage: cd backend && python ../scripts/demo_smoke.py
"""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    login=client.post('/api/auth/login',json={'username':'admin','password':os.environ['TP_ADMIN_PASSWORD']})
    login.raise_for_status()
    auth={'Authorization':'Bearer '+login.json()['access_token']}
    deploy=client.post('/api/demo/deploy',headers=auth,json={'scenario':'all','auto_scan':False})
    deploy.raise_for_status()
    scan=client.post('/api/agent/run',headers=auth)
    scan.raise_for_status()
    outcome=client.get('/api/agent/runs',headers=auth).json()[0]
    print('Deployment:',deploy.json())
    print('Scan:',{k:outcome[k] for k in ['status','tests_run','requests_sent','confirmed']})
    print('Outcomes:',outcome['summary']['outcomes'])
    assert outcome['confirmed']==3 and outcome['status']=='completed'
    found=client.get('/api/agent/findings',headers=auth).json()
    print('Verified findings:', [(f['kind'],f['severity']) for f in found if f['scan_id']==outcome['id']])
    client.post('/api/demo/deploy',headers=auth,json={'scenario':'secure','auto_scan':False}).raise_for_status()
    f=next(x for x in found if x['scan_id']==outcome['id'])
    retest=client.post(f"/api/agent/findings/{f['id']}/retest",headers=auth)
    retest.raise_for_status()
    print('Retest:', retest.json())
    print('SUCCESS — safely detected seeded vulnerabilities and retested a fix.')
