"""Studio UI smoke tests; all static resources are same-origin under the lab CSP."""
from pathlib import Path


def test_studio_uses_real_html_with_complete_navigation(client):
    response = client.get('/lab')
    assert response.status_code == 200
    html = response.text
    assert 'TripParadox Studio — Security Operations' in html
    assert 'Autonomous scanner' in html
    assert 'Travel booking clone' in html
    assert 'Verified findings' in html
    assert 'Security & audit' in html
    assert 'id="theme-toggle"' in html
    assert 'id="menu-toggle"' in html
    assert '/lab-assets/vendor/tabler-core.css' in html
    assert response.headers['content-security-policy'].startswith("default-src 'self'")


def test_offline_styles_and_original_city_art_are_served(client):
    for asset in ('styles.css', 'app.js', 'vendor/tabler-core.css',
                  'art/dubai.svg', 'art/singapore.svg', 'art/coast.svg'):
        resp=client.get('/lab-assets/'+asset)
        assert resp.status_code == 200,asset
        assert resp.headers['x-content-type-options'] == 'nosniff'
    css=client.get('/lab-assets/styles.css').text
    assert '@media(max-width:740px)' in css
    assert '.market-grid' in css
    assert '.modal-shell' in css
    assert '.auth-radar' in css


def test_new_booking_search_controls_are_not_dummy(client):
    js=client.get('/lab-assets/app.js').text
    assert "'search-travel'" in js
    assert "'reset-travel'" in js
    assert 'state.travelFilter' in js
    assert "'hold:'" in js
    assert "'/holds'" in js
    assert "'/agent/plan" in js
    assert "'/agent/start" in js
    assert "'/agent/runs/" in js
    assert "'/db/status'" in js


def test_synthetic_scanner_is_still_not_open_to_external_network(client):
    r=client.get('/health')
    assert r.json()['external_scanning'] is False
    html=client.get('/lab').text
    assert 'https://' not in html
    assert '<script src="https:' not in html
