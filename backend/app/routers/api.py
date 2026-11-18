"""Authenticated management APIs for controlled synthetic security demonstrations."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, delete, update
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import current_user, require_admin, verify_password, issue_token
from ..models import (User, Booking, Refund, SimulatorConfig, Deploy, ScanRun, Finding,
                      Evidence, Inventory, Audit, Ticket, Traffic, RunEvent, ModelSnapshot, ModelPrediction)
from ..schemas import LoginIn, DeployIn, PauseIn, TicketDecisionIn
from ..services.serialize import obj
from ..services.engine import run_pipeline, safe_run_pipeline, CASES
from ..services.ml_planner import prioritize, train_models, predict_features, FEATURE_NAMES, FEATURE_HELP, CASE_FEATURES
from ..services.model_registry import ensure_model_snapshot, save_prediction
from ..services.planner import affected_cases
from ..config import settings
import time
from pydantic import BaseModel, Field, ConfigDict, field_validator
from ..services.inventory import rebuild_inventory

router = APIRouter(prefix="/api", tags=["security-control-plane"])
# Best-effort single-process demo login throttling; production requires a shared store.
_LOGIN_FAILURES = {}

FLAW_ROUTES = {
    "cross_agency": ["GET /sim/bookings/{id}"],
    "double_refund": ["POST /sim/bookings/{id}/refund"],
    "legacy_bypass": ["GET /sim/legacy/v1/bookings/{id}"],
    "all": ["GET /sim/bookings/{id}", "POST /sim/bookings/{id}/refund", "GET /sim/legacy/v1/bookings/{id}"],
    "secure": ["GET /sim/bookings/{id}", "POST /sim/bookings/{id}/refund", "GET /sim/legacy/v1/bookings/{id}"],
}


@router.post("/auth/login")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else 'local'}:{payload.username.lower()}"
    now = time.monotonic()
    failures = [t for t in _LOGIN_FAILURES.get(key, []) if now - t < 60]
    if len(failures) >= 6:
        raise HTTPException(429, 'Too many login attempts. Try again later.')
    # Login uses a generic response to avoid username enumeration.
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.pw_hash):
        failures.append(now)
        _LOGIN_FAILURES[key] = failures
        db.add(Audit(action="auth", actor="unknown", result="denied", metadata_={"reason": "invalid-credentials"}))
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    _LOGIN_FAILURES.pop(key, None)
    db.add(Audit(action="auth", actor=user.username, result="allowed", metadata_={}))
    db.commit()
    return {"access_token": issue_token(user), "token_type": "bearer", "role": user.role, "username": user.username}


@router.get("/auth/me")
def whoami(user: User = Depends(current_user)):
    return obj(user, "username", "role", "agency_id")


@router.get("/overview")
def overview(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = db.get(SimulatorConfig, 1)
    return {"version": cfg.version, "paused": cfg.scanning_paused,
            "intentional_flaws_enabled": settings().allow_intentional_flaws,
            "flaws": {"cross_agency": cfg.cross_agency_bug,
                      "double_refund": cfg.double_refund_bug, "legacy_bypass": cfg.legacy_bypass_bug},
            "runs": db.scalar(select(func.count(ScanRun.id))),
            "findings": db.scalar(select(func.count(Finding.id)).where(Finding.status == "confirmed")),
            "inventory": db.scalar(select(func.count(Inventory.id))),
            "tickets": db.scalar(select(func.count(Ticket.id)))}


@router.get("/bookings")
def bookings(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    data = db.scalars(select(Booking).where(Booking.universe == "baseline").order_by(Booking.id)).all()
    return [obj(r, "id", "agency_id", "itinerary", "amount_paise", "status") for r in data]


@router.get("/deploys")
def deploys(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [obj(d, "id", "version", "scenario", "changed_routes", "created_at") for d in db.scalars(select(Deploy).order_by(Deploy.id.desc()).limit(30))]


def guard_exclusive_scan(db: Session, require_unpaused: bool = True):
    """Serialize scan/deploy reservations via one DB row (Postgres and SQLite).

    Must be called BEFORE committing a queued run or toggling synthetic flaws.
    Unlike a process-local mutex, the database write lock also works across
    separate HTTP handler threads and concurrent app instances.
    """
    db.execute(update(SimulatorConfig).where(SimulatorConfig.id == 1)
               .values(version=SimulatorConfig.version))
    cfg = db.get(SimulatorConfig, 1)
    if cfg is None:
        raise HTTPException(503, 'Synthetic configuration not initialized')
    if require_unpaused and cfg.scanning_paused:
        raise HTTPException(409, 'Safety kill switch is active')
    pending = db.scalar(select(func.count(ScanRun.id))
                        .where(ScanRun.status.in_(['queued', 'running']))) or 0
    if pending:
        raise HTTPException(409, 'Cannot change deployment while a scan is active')
    return cfg


def reject_unapproved_demo_flaws(scenario: str):
    if scenario != 'secure' and not settings().allow_intentional_flaws:
        raise HTTPException(403, 'Deliberately vulnerable scenarios disabled at server startup')


@router.post("/demo/deploy")
def deploy(payload: DeployIn, tasks: BackgroundTasks, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    reject_unapproved_demo_flaws(payload.scenario)
    cfg = guard_exclusive_scan(db, require_unpaused=payload.auto_scan)
    cfg.version += 1
    cfg.cross_agency_bug = payload.scenario in ("cross_agency", "all")
    cfg.double_refund_bug = payload.scenario in ("double_refund", "all")
    cfg.legacy_bypass_bug = payload.scenario in ("legacy_bypass", "all")
    deploy_obj = Deploy(version=cfg.version, scenario=payload.scenario,
                        changed_routes=FLAW_ROUTES[payload.scenario])
    db.add(deploy_obj); db.flush()
    db.add(Audit(action="synthetic_deploy", actor=admin.username, result="applied",
                 metadata_={"deploy_id": deploy_obj.id, "scenario": payload.scenario}))
    scan_id = None
    if payload.auto_scan:
        run = ScanRun(deploy_id=deploy_obj.id, status='queued')
        db.add(run); db.flush(); scan_id = run.id
    db.commit()
    if payload.auto_scan:
        # The DB reservation is already visible BEFORE the task begins.
        from ..main import app
        tasks.add_task(safe_run_pipeline, app, deploy_id=deploy_obj.id, existing_run_id=scan_id)
    return {"deploy_id": deploy_obj.id, "version": cfg.version,
            "scenario": payload.scenario, "scan_id": scan_id,
            "automatic_scan_queued": payload.auto_scan}


@router.post("/agent/run")
async def run_now(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    guard_exclusive_scan(db)
    run = ScanRun(status='queued'); db.add(run); db.flush()
    run_id = run.id; db.commit()
    from ..main import app
    return {"scan_id": await safe_run_pipeline(app, existing_run_id=run_id)}


@router.post("/agent/pause")
def pause(payload: PauseIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = db.get(SimulatorConfig, 1)
    cfg.scanning_paused = payload.paused
    db.add(Audit(action="kill_switch", actor=admin.username, result="paused" if payload.paused else "resumed", metadata_={}))
    db.commit()
    return {"paused": cfg.scanning_paused}


@router.get("/agent/runs")
def runs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cols = ("id", "deploy_id", "status", "started_at", "finished_at", "tests_run", "requests_sent", "confirmed", "summary")
    return [obj(r, *cols) for r in db.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(30))]


@router.get("/agent/runs/{run_id}")
def run_details(run_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    run = db.get(ScanRun, run_id)
    if not run: raise HTTPException(404, "Scan not found")
    evidence = db.scalars(select(Evidence).where(Evidence.scan_id == run_id)).all()
    return {"run": obj(run, "id", "deploy_id", "status", "started_at", "finished_at", "tests_run", "requests_sent", "confirmed", "summary"),
            "evidence": [obj(x, "id", "test", "universe", "passed", "expected", "observed", "details") for x in evidence],
            "events": [obj(e, "id", "phase", "title", "status", "details", "created_at") for e in db.scalars(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.id))]}


@router.get("/agent/findings")
def findings(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cols = ("id", "scan_id", "kind", "title", "severity", "status", "owner", "description", "proof", "recommended_fix", "discovered_at", "retested_at")
    return [obj(f, *cols) for f in db.scalars(select(Finding).order_by(Finding.id.desc()).limit(100))]


@router.post("/agent/findings/{finding_id}/retest")
async def retest(finding_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    f = db.get(Finding, finding_id)
    if not f: raise HTTPException(404, "Finding not found")
    guard_exclusive_scan(db)
    run = ScanRun(status='queued'); db.add(run); db.flush()
    run_id = run.id; db.commit()
    from ..main import app
    return {"scan_id": await safe_run_pipeline(app, kinds=[f.kind], retest_of=f.id,
                                                existing_run_id=run_id), "retested_finding": f.id}


@router.get("/agent/inventory")
def inventory(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rebuild_inventory(db)
    cols = ("id", "path_template", "method", "classification", "documented", "seen_in_logs", "last_legitimate_seen", "owner", "recommendation")
    return [obj(r, *cols) for r in db.scalars(select(Inventory).order_by(Inventory.id))]


@router.get("/agent/tickets")
def tickets(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [obj(r, "id", "finding_id", "state", "owner", "note", "created_at") for r in db.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(100))]


@router.post("/agent/tickets/{ticket_id}/decision")
def review_ticket(ticket_id: int, payload: TicketDecisionIn,
                  admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Named human reviewer decision; never posts to an external ticket system."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None: raise HTTPException(404, "Ticket not found")
    if ticket.state == "resolved": raise HTTPException(409, "Resolved tickets cannot be escalated")
    ticket.state = "approved_for_escalation" if payload.decision == "approve" else "rejected"
    ticket.note = f"Human review by {admin.username}: {payload.note}"
    db.add(Audit(action="human_review", actor=admin.username, result=payload.decision,
                 metadata_={"ticket_id": ticket_id, "finding_id": ticket.finding_id}))
    db.commit()
    return obj(ticket, "id", "finding_id", "state", "owner", "note")


@router.get("/agent/audit")
def audit(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [obj(r, "id", "action", "actor", "result", "metadata_", "at") for r in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(150))]


@router.get("/agent/report")
def report(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"project": "TripParadox AI", "mode": "synthetic-only", "generated_at": datetime.now(timezone.utc).isoformat(),
            "findings": [obj(f, "id", "kind", "title", "severity", "status", "owner", "proof", "recommended_fix") for f in db.scalars(select(Finding).order_by(Finding.id))],
            "runs": [obj(r, "id", "status", "requests_sent", "tests_run", "confirmed") for r in db.scalars(select(ScanRun))],
            "scope": "ASGI in-process synthetic app only", "human_review": True}


class ModelPreviewIn(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    # No arbitrary target or payload field: this is a read-only local ML inference.
    features: dict[str, int]
    description: str = Field(min_length=1, max_length=280)

    @field_validator('features')
    @classmethod
    def strictly_valid_features(cls, values):
        if set(values) != set(FEATURE_NAMES) or any(type(x) is not int or x not in (0, 1) for x in values.values()):
            raise ValueError('Provide exactly the eight approved 0/1 feature flags')
        return values


@router.get('/ml/overview')
def ml_overview(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    metadata = train_models()[2]
    ensure_model_snapshot(db)
    db.commit()
    return {
        'metadata': metadata,
        'feature_schema': [{'name': key, 'help': FEATURE_HELP[key]} for key in FEATURE_NAMES],
        'example_cases': CASE_FEATURES,
        'postgresql_expected_in_docker': True,
        'database_dialect': db.bind.dialect.name,
        'saved_predictions': db.scalar(select(func.count(ModelPrediction.id))),
        'snapshots': db.scalar(select(func.count(ModelSnapshot.id))),
        'security_truth_source': 'Fixed SQL-backed invariants, not ML inference',
    }


@router.post('/ml/preview')
def ml_interactive_preview(payload: ModelPreviewIn, admin: User = Depends(require_admin),
                           db: Session = Depends(get_db)):
    scores = predict_features([payload.features[k] for k in FEATURE_NAMES], payload.description)
    stored = save_prediction(db, scores, actor=admin.username, case='interactive-preview')
    db.add(Audit(action='synthetic_ml_inference', actor=admin.username, result='stored',
                 metadata_={'prediction_id': stored.id, 'model_version': scores['model_version'],
                            'external_network': False}))
    db.commit()
    return {'prediction_id': stored.id, 'prediction': scores,
            'storage': db.bind.dialect.name, 'executed_tests': 0,
            'note': 'Read-only ML preview; it never invokes a security test.'}


@router.get('/ml/predictions')
def ml_predictions(scan_id: int | None = None, admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    query = select(ModelPrediction).order_by(ModelPrediction.id.desc()).limit(100)
    if scan_id is not None:
        query = select(ModelPrediction).where(ModelPrediction.scan_id == scan_id).order_by(ModelPrediction.id.asc()).limit(100)
    return [obj(m, 'id', 'scan_id', 'actor', 'case', 'model_version', 'feature_vector',
                'risk_score', 'novelty_score', 'predicted_class', 'class_confidence',
                'explanation', 'created_at') for m in db.scalars(query)]


@router.get('/ml/snapshots')
def model_snapshots(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ensure_model_snapshot(db); db.commit()
    return [obj(m, 'id', 'model_version', 'training_source', 'metrics', 'created_at')
            for m in db.scalars(select(ModelSnapshot).order_by(ModelSnapshot.id.desc()).limit(10))]


@router.get('/agent/model')
def ml_model_info(admin: User = Depends(require_admin)):
    return train_models()[2]


@router.get('/agent/plan')
def scan_plan(scenario: str = 'all', admin: User = Depends(require_admin)):
    if scenario not in FLAW_ROUTES:
        raise HTTPException(422, 'Unknown synthetic scenario')
    selected = [k for k, route in {
        'cross_agency': 'GET /sim/bookings/{id}',
        'double_refund': 'POST /sim/bookings/{id}/refund',
        'legacy_bypass': 'GET /sim/legacy/v1/bookings/{id}',
    }.items() if route in FLAW_ROUTES[scenario]]
    plan = prioritize(selected)
    return {'mode': 'SYNTHETIC / IN-PROCESS ONLY', 'scenario': scenario,
            'tests': plan, 'max_requests': 40,
            'phases': [
                {'name': 'Safety gate', 'code': 'services.safety.SafetyGate', 'description': 'Enforce locked local scope, request budget and kill switch'},
                {'name': 'ML training', 'code': 'services.ml_planner.train_models', 'description': 'Train and holdout-evaluate risk, threat class and anomaly models on synthetic examples'},
                {'name': 'AI test planning', 'code': 'services.ml_planner.prioritize', 'description': 'Score risk, threat class and novelty, then store every decision in SQL'},
                {'name': 'API inventory', 'code': 'services.inventory.rebuild_inventory', 'description': 'Compare known routes with synthetic traffic and old JavaScript fixtures'},
                {'name': 'Parallel universes', 'code': 'services.engine.fresh_universe', 'description': 'Fork isolated SQL booking snapshots before each test'},
                {'name': 'Safe replay', 'code': 'services.engine.SafeASGI', 'description': 'Execute bounded synthetic role / refund / legacy requests'},
                {'name': 'Invariant oracle', 'code': 'services.engine.CASE_FUNCTIONS', 'description': 'Prove or reject findings against persistent SQL state'},
                {'name': 'Evidence + retest', 'code': 'services.engine.persist_test', 'description': 'Store a reproducible proof and queue human review'},
            ],
            'constraints': ['No real TBO endpoint', 'No internet target', 'No live customer records',
                            'Only approved test accounts', 'No destructive external actions'],
            'note': 'ML predicts scheduling priority, not security truth. Tests are validated by deterministic rules.'}


@router.post('/agent/start')
def start_automated_scan(payload: DeployIn, tasks: BackgroundTasks,
                         admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    reject_unapproved_demo_flaws(payload.scenario)
    cfg = guard_exclusive_scan(db)
    cfg.version += 1
    cfg.cross_agency_bug = payload.scenario in ('cross_agency', 'all')
    cfg.double_refund_bug = payload.scenario in ('double_refund', 'all')
    cfg.legacy_bypass_bug = payload.scenario in ('legacy_bypass', 'all')
    deploy_obj = Deploy(version=cfg.version, scenario=payload.scenario,
                        changed_routes=FLAW_ROUTES[payload.scenario])
    db.add(deploy_obj); db.flush()
    run = ScanRun(deploy_id=deploy_obj.id, status='queued')
    db.add(run); db.flush()
    db.add(Audit(action='ml_scan_scheduled', actor=admin.username, result='queued',
                 metadata_={'run_id': run.id, 'deploy_id': deploy_obj.id,
                            'scenario': payload.scenario, 'synthetic': True}))
    run_id, deploy_id = run.id, deploy_obj.id
    db.commit()
    from ..main import app
    tasks.add_task(safe_run_pipeline, app, deploy_id=deploy_id, existing_run_id=run_id)
    return {'scan_id': run_id, 'deploy_id': deploy_id, 'scenario': payload.scenario,
            'status': 'queued', 'progress': f'/api/agent/runs/{run_id}', 'external_scanning': False}


@router.get('/agent/security-check')
def security_check(admin: User = Depends(require_admin)):
    cfg = settings()
    return {'environment': 'fictional isolated simulator', 'checks': [
        {'name': 'Long locally generated JWT secret', 'state': 'configured' if len(cfg.jwt_secret) >= 32 else 'fail',
         'detail': 'Signed HS256 access tokens; secret value not returned'},
        {'name': 'Argon2 password hashing', 'state': 'configured', 'detail': 'Passwords stored as salted Argon2 hashes'},
        {'name': 'Signed sessions / role gates', 'state': 'configured', 'detail': 'JWT expiry and admin / agency access enforced server-side'},
        {'name': 'Local-origin CORS policy', 'state': 'configured' if all(x.startswith(('http://localhost:', 'http://127.0.0.1:')) for x in cfg.cors_origins) else 'review',
         'detail': 'Allowed origins: ' + ', '.join(cfg.cors_origins)},
        {'name': 'SQL parameterization', 'state': 'configured', 'detail': 'SQLAlchemy ORM instead of SQL string concatenation'},
        {'name': 'Trusted Host validation', 'state': 'enforced', 'detail': 'Localhost, testserver and fixed in-process test host only'},
        {'name': 'External scan boundary', 'state': 'enforced', 'detail': 'ASGITransport in memory; no arbitrary host input'},
        {'name': 'Hard per-run limit', 'state': 'enforced', 'detail': '40 requests max, sequential, allowlisted paths'},
        {'name': 'Safety kill switch', 'state': 'enforced', 'detail': 'Persisted setting checked before each request'},
        {'name': 'Browser security headers', 'state': 'configured', 'detail': 'CSP, nosniff, frame denial, no-store'},
        {'name': 'Demonstration only', 'state': 'review', 'detail': 'Not penetration-tested, not hardened for public internet deployment'},
    ], 'honest_assessment': 'A configuration checklist, not a certification or full penetration test.'}


@router.get('/db/status')
def db_status(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from sqlalchemy import text
    db.execute(text('SELECT 1')).scalar_one()
    return {'connected': True, 'dialect': db.bind.dialect.name, 'connection': 'SQLAlchemy ORM',
            'tables': {'model_predictions': db.scalar(select(func.count(ModelPrediction.id))), 'model_snapshots': db.scalar(select(func.count(ModelSnapshot.id))), 'users': db.scalar(select(func.count(User.id))),
                       'bookings': db.scalar(select(func.count(Booking.id))),
                       'refunds': db.scalar(select(func.count(Refund.id))),
                       'scan_runs': db.scalar(select(func.count(ScanRun.id))),
                       'run_events': db.scalar(select(func.count(RunEvent.id))),
                       'evidence': db.scalar(select(func.count(Evidence.id))),
                       'findings': db.scalar(select(func.count(Finding.id))),
                       'audit': db.scalar(select(func.count(Audit.id)))},
            'note': 'Fictional data only; credentials are never included in the response'}
