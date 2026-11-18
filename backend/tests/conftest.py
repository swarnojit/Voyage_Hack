import os
import tempfile
from pathlib import Path

# Configure isolated test DB before importing app.database (module-level engine).
TEST_ROOT = Path(tempfile.mkdtemp(prefix="tripparadox-tests-"))
os.environ["TP_DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'lab.db'}"
os.environ["TP_DEMO_MODE"] = "true"
os.environ["TP_ALLOW_INTENTIONAL_FLAWS"] = "true"
os.environ["TP_JWT_SECRET"] = "tests-only-secret-with-more-than-thirty-two-randomish-characters"
os.environ["TP_ADMIN_PASSWORD"] = "SyntheticAdminPassword123!"
os.environ["TP_AGENCY_PASSWORD"] = "SyntheticAgencyPassword123!"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from app.database import SessionLocal
from app.main import app
from app.models import (SimulatorConfig, Deploy, Finding, Evidence, ScanRun, Audit, Ticket)


@pytest.fixture
def client():
    with TestClient(app) as c:
        with SessionLocal() as db:
            cfg = db.get(SimulatorConfig, 1)
            cfg.cross_agency_bug = False
            cfg.double_refund_bug = False
            cfg.legacy_bypass_bug = False
            cfg.scanning_paused = False
            db.commit()
        yield c


@pytest.fixture
def admin(client):
    login = client.post('/api/auth/login', json={'username':'admin','password':os.environ['TP_ADMIN_PASSWORD']})
    assert login.status_code == 200, login.text
    return {'Authorization':f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def atlas(client):
    r=client.post('/api/auth/login',json={'username':'atlas_agent','password':os.environ['TP_AGENCY_PASSWORD']})
    assert r.status_code==200
    return {'Authorization':f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def bluebird(client):
    r=client.post('/api/auth/login',json={'username':'bluebird_agent','password':os.environ['TP_AGENCY_PASSWORD']})
    assert r.status_code==200
    return {'Authorization':f"Bearer {r.json()['access_token']}"}
