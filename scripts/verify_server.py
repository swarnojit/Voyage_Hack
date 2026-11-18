"""Smoke test the REAL Uvicorn HTTP process, then restart with same disposable DB.

Do not use live customer/staging data. No external URLs are contacted.
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
BACKEND=ROOT/'backend'
report={'scope':'127.0.0.1 only / fake accounts / disposable SQLite',
        'checks':[],'postgresql_runtime_tested':False}
with tempfile.TemporaryDirectory(prefix='tripparadox-uvicorn-check-') as temp:
    dbfile=Path(temp)/'livecheck.db'
    env=os.environ.copy()
    env.update({'TP_DATABASE_URL':'sqlite:///'+str(dbfile),'TP_DEMO_MODE':'true','TP_ALLOW_INTENTIONAL_FLAWS':'true',
                'TP_JWT_SECRET':secrets.token_urlsafe(48),
                'TP_ADMIN_PASSWORD':secrets.token_urlsafe(22),
                'TP_AGENCY_PASSWORD':secrets.token_urlsafe(22)})
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    logs=Path(temp)/'server.log'
    def launch():
        f=logs.open('a')
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app',
                               '--host','127.0.0.1','--port',str(port),'--workers','1'],
                              cwd=str(BACKEND),env=env,stdout=f,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+18
        while time.monotonic()<deadline:
            if proc.poll() is not None: raise RuntimeError(f'Process exited: {logs.read_text()[-2500:]}')
            try:
                r=httpx.get(base+'/health/db',timeout=1)
                if r.status_code==200:
                    assert r.json()['database']=='sqlite'
                    return proc,f
            except (httpx.ConnectError,httpx.ConnectTimeout,httpx.ReadTimeout):pass
            time.sleep(.15)
        raise RuntimeError('Uvicorn startup timed out: '+logs.read_text()[-2500:])
    def stop(proc, f):
        proc.terminate()
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=4)
        f.close()
    proc,f=launch()
    try:
        with httpx.Client(base_url=base,timeout=20) as c:
            login=c.post('/api/auth/login',json={'username':'admin','password':env['TP_ADMIN_PASSWORD']})
            assert login.status_code==200,login.text
            c.headers['Authorization']='Bearer '+login.json()['access_token']
            report['checks'].append('actual HTTP/Uvicorn boot, JWT login, DB ready')
            page=c.get('/lab');assert page.status_code==200
            assert page.headers.get('x-frame-options')=='DENY'
            assert "script-src 'self'" in page.headers.get('content-security-policy','')
            report['checks'].append('real HTTP frontend and security headers')
            model=c.get('/api/ml/overview'); assert model.status_code==200
            schema=model.json()['feature_schema']
            flags={f['name']:0 for f in schema}
            preview=c.post('/api/ml/preview',json={'features':flags,'description':'safe synthetic staging booking api'})
            assert preview.status_code==200,preview.text
            report['checks'].append('three real sklearn models + SQL model registry on HTTP')
            for scenario,count in (('secure',0),('all',3)):
                started=c.post('/api/agent/start',json={'scenario':scenario,'auto_scan':True})
                assert started.status_code==200,started.text
                rid=started.json()['scan_id']
                end=time.monotonic()+20
                while time.monotonic()<end:
                    obj=c.get(f'/api/agent/runs/{rid}').json()
                    if obj['run']['status'] not in ('queued','running'):break
                    time.sleep(.15)
                assert obj['run']['status']=='completed',obj['run']
                assert obj['run']['confirmed']==count,obj['run']
                report['checks'].append(f'HTTP backend {scenario} full scan: {count} expected findings')
            before=c.get('/api/overview').json()['runs']
    finally:stop(proc,f)
    report['checks'].append('graceful Uvicorn shutdown')
    proc,f=launch()
    try:
        with httpx.Client(base_url=base,timeout=12) as c:
            login=c.post('/api/auth/login',json={'username':'admin','password':env['TP_ADMIN_PASSWORD']})
            assert login.status_code==200
            c.headers['Authorization']='Bearer '+login.json()['access_token']
            after=c.get('/api/overview').json()['runs']
            assert before==after and after>=2,(before,after)
            assert c.get('/api/ml/predictions').status_code==200
            assert c.get('/api/db/status').json()['connected'] is True
            report['checks'].append(f'cold restart retained {after} scan records and model predictions')
    finally:stop(proc,f)
report['result']='PASS'
report['limits']='Uvicorn+SQLite smoke only; PostgreSQL container unavailable; no security certification'
(ROOT/'docs/release_uvicorn_result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
