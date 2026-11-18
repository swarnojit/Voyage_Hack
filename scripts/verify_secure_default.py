"""Prove that packaged deployment boots secure and disables training flaws by default."""
import os
import secrets
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
with tempfile.TemporaryDirectory(prefix='tp-safe-default-') as temp:
    os.environ.update({'TP_DATABASE_URL':f'sqlite:///{temp}/secure-default.db',
                       'TP_DEMO_MODE':'true','TP_ALLOW_INTENTIONAL_FLAWS':'false',
                       'TP_JWT_SECRET':secrets.token_urlsafe(48),
                       'TP_ADMIN_PASSWORD':secrets.token_urlsafe(25),
                       'TP_AGENCY_PASSWORD':secrets.token_urlsafe(25)})
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import SessionLocal
    from app.models import SimulatorConfig
    def login(client):
        r=client.post('/api/auth/login',json={'username':'admin','password':os.environ['TP_ADMIN_PASSWORD']})
        assert r.status_code==200,r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}
    with TestClient(app) as c:
        admin=login(c)
        state=c.get('/api/overview',headers=admin).json()
        assert not any(state['flaws'].values())
        assert state['intentional_flaws_enabled'] is False
        for scenario in ('all','cross_agency','double_refund','legacy_bypass'):
            assert c.post('/api/demo/deploy',headers=admin,json={'scenario':scenario,'auto_scan':False}).status_code==403
            assert c.post('/api/agent/start',headers=admin,json={'scenario':scenario}).status_code==403
        r=c.post('/api/agent/start',headers=admin,json={'scenario':'secure'})
        assert r.status_code==200,r.text
        result=c.get(f"/api/agent/runs/{r.json()['scan_id']}",headers=admin).json()['run']
        assert result['status']=='completed' and result['confirmed']==0
    with SessionLocal() as db:
        # Simulate an old lab database left intentionally vulnerable before shutdown.
        cfg=db.get(SimulatorConfig,1)
        cfg.cross_agency_bug=cfg.double_refund_bug=cfg.legacy_bypass_bug=True
        db.commit()
    with TestClient(app) as c:
        admin=login(c)
        state=c.get('/api/overview',headers=admin).json()
        assert not any(state['flaws'].values()),state
        assert c.post('/api/agent/run',headers=admin).json()['scan_id']>0
        assert c.get('/api/agent/runs',headers=admin).json()[0]['confirmed']==0
    print('PASS: safe deployment default; 4 planted scenarios locked; restart resets stale insecure flags; secure scan 0 findings')
