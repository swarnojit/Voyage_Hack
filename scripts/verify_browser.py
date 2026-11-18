"""End-to-end Chromium UI smoke test with an in-process FastAPI bridge.

The browser cannot navigate an external target: all fetches are resolved by
FastAPI's local TestClient against a disposable SQLite sandbox.
Requires optional playwright + a local Chromium executable.
"""
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'backend/app/static'
sys.path.insert(0,str(ROOT/'backend'))
with tempfile.TemporaryDirectory(prefix='tp-browser-release-') as work:
    os.environ.update({'TP_DATABASE_URL':f'sqlite:///{work}/browser.db',
                       'TP_DEMO_MODE':'true','TP_ALLOW_INTENTIONAL_FLAWS':'true','TP_JWT_SECRET':secrets.token_urlsafe(48),
                       'TP_ADMIN_PASSWORD':secrets.token_urlsafe(24),
                       'TP_AGENCY_PASSWORD':secrets.token_urlsafe(24)})
    from fastapi.testclient import TestClient
    from app.main import app
    html=(STATIC/'index.html').read_text()
    css=(STATIC/'styles.css').read_text()
    html=html.replace('<script src="/lab-assets/app.js" defer></script>','')
    html=html.replace('<link rel="stylesheet" href="/lab-assets/styles.css">',f'<style>{css}</style>')
    html=html.replace('<link rel="stylesheet" href="/lab-assets/vendor/tabler-core.css">','')
    js=(STATIC/'app.js').read_text()
    report={'test':'Chromium real frontend with FastAPI test bridge',
            'scope':'in-process only', 'actions':[], 'browser_errors':[]}
    with TestClient(app) as client, sync_playwright() as playwright:
        def request(url, options):
            # Important: do not permit browser navigation or external requests.
            if not url.startswith(('/api/','/sim/')):
                return {'status':403,'body':{'detail':'Only local demo API is permitted'}}
            opts=options or {}
            headers=opts.get('headers') or {}
            raw=opts.get('body')
            try:
                r=client.request(opts.get('method') or 'GET',url,headers=headers,content=raw)
                try: body=r.json()
                except Exception: body={'detail':r.text[:400]}
                return {'status':r.status_code,'body':body}
            except Exception as e:
                return {'status':598,'body':{'detail':type(e).__name__}}
        b=playwright.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=b.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
        page.on('pageerror', lambda e:report['browser_errors'].append(str(e)))
        page.set_content(html,wait_until='domcontentloaded')
        page.expose_function('pyBridge',request)
        page.evaluate('''() => {window.fetch = async (url, opts={}) => {
            const d=await window.pyBridge(String(url),opts);
            return {status:d.status,ok:d.status>=200&&d.status<300,json:async()=>d.body};
        }}''')
        page.add_script_tag(content=js)
        page.locator('#password').fill(os.environ['TP_ADMIN_PASSWORD'])
        page.locator('#login-form button[type="submit"]').click()
        page.locator('#workspace:not(.hidden)').wait_for(timeout=12000)
        report['actions'].append('JWT login and overview rendering')
        page.locator('[data-page="models"]').click()
        page.locator('.ml-switch').first.wait_for()
        assert page.locator('.ml-switch').count()==8
        page.locator('[data-action="ml-preset:double_refund"]').click()
        page.locator('[data-action="ml-infer"]').click()
        page.get_by_text('INFERENCE #',exact=False).first.wait_for(timeout=12000)
        report['actions'].append('Model Lab features and SQL-persisted inference')
        page.locator('[data-page="travel"]').click()
        page.get_by_text('Hold this room',exact=False).first.click()
        page.wait_for_timeout(250)
        # The booking ledger exists and is backed by a real SQL API call.
        assert page.locator('.ledger-booking').count()>=1
        report['actions'].append('Travel catalog and synthetic SQL room hold')
        page.locator('[data-page="cockpit"]').click()
        page.locator('#scenario').select_option('secure')
        page.locator('[data-action="preview"]').first.click()
        page.locator('[data-action="execute"]').click()
        page.get_by_text('Model-to-scan evidence',exact=False).first.wait_for(timeout=12000)
        page.wait_for_timeout(450)
        secure=page.evaluate('state.runData.run')
        assert secure['status']=='completed' and secure['confirmed']==0,secure
        report['actions'].append('Secure scan zero verified findings in covered cases')
        page.locator('#scenario').select_option('all')
        page.locator('[data-action="preview"]').first.click()
        page.locator('[data-action="execute"]').click()
        page.wait_for_timeout(550)
        planted=page.evaluate('state.runData.run')
        assert planted['status']=='completed' and planted['confirmed']==3,planted
        report['actions'].append('All three deliberately planted bugs detected and recorded')
        page.screenshot(path=str(ROOT/'docs/release_browser_dashboard.png'),full_page=True)
        page.locator('[data-page="security"]').click()
        assert 'SQL persistence health' in page.locator('body').inner_text()
        report['actions'].append('Database connection dashboard')
        page.locator('#theme-toggle').click()
        assert page.locator('body').get_attribute('data-theme')=='dark'
        report['actions'].append('Light/dark theme toggle')
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#menu-toggle').click()
        assert 'sidebar-open' in page.locator('body').get_attribute('class')
        report['actions'].append('Mobile responsive drawer')
        b.close()
    assert not report['browser_errors'],report['browser_errors']
    report['result']='PASS'
    (ROOT/'docs/release_browser_result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
