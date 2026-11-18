"""TripParadox counterfactual test engine.

Only the bundled ASGI simulator is reachable. No socket/network target input exists.
The correct oracle is the persisted booking/refund state, not an LLM judgment.
"""
import asyncio
from datetime import datetime, timezone
import httpx
import json
from pathlib import Path
from sqlalchemy import select, func
from .safety import SafetyGate, StopScan
from .inventory import rebuild_inventory
from ..database import SessionLocal
from ..auth import issue_token
from ..models import (Booking, Refund, User, ScanRun, Finding, Evidence, Audit,
                      Ticket, SimulatorConfig, Deploy, RunEvent, utcnow)

RUN_LOCK = asyncio.Lock()


def record_event(run_id: int, phase: str, title: str, details: dict | None = None, status: str = "info"):
    """SQL-persisted, scrubbed progress events, safe for polling UI."""
    with SessionLocal() as db:
        db.add(RunEvent(run_id=run_id, phase=phase, title=title, status=status, details=details or {}))
        db.commit()



CASES = {
    "cross_agency": {
        "title": "Cross-agency booking boundary violation",
        "severity": "critical", "owner": "Booking API Team",
        "description": "A synthetic user from another agency can read a booking they do not own.",
        "fix": "Enforce agency-scoped object authorization on every booking lookup; test across all roles.",
        "fingerprint": "BOLA:GET:/sim/bookings/{id}",
    },
    "double_refund": {
        "title": "Duplicate refund breaks financial conservation",
        "severity": "critical", "owner": "Payments Team",
        "description": "Repeated synthetic refund commands exceed the amount originally paid.",
        "fix": "Enforce idempotency using a unique key plus an atomic transaction and cumulative refund limit.",
        "fingerprint": "LOGIC:POST:/sim/bookings/{id}/refund",
    },
    "legacy_bypass": {
        "title": "Zombie v1 API bypasses agency authorization",
        "severity": "high", "owner": "Legacy Integration Team",
        "description": "A legacy synthetic endpoint allows cross-agency booking access despite current access policy.",
        "fix": "Remove or restrict legacy endpoint; centralize the agency authorization policy.",
        "fingerprint": "BOLA:GET:/sim/legacy/v1/bookings/{id}",
    },
}


def actor_tokens():
    with SessionLocal() as db:
        users = {u.username: u for u in db.scalars(select(User)).all()}
        return {name: issue_token(users[name]) for name in ("admin", "atlas_agent", "bluebird_agent")}


def baseline_booking() -> int:
    with SessionLocal() as db:
        atlas = db.scalar(select(User).where(User.username == "atlas_agent"))
        booking = db.scalar(select(Booking).where(Booking.agency_id == atlas.agency_id, Booking.universe == "baseline"))
        if not booking:
            raise RuntimeError("Synthetic seed booking missing")
        return booking.id


def fresh_universe(original_id: int, label: str) -> int:
    """Create an isolated logical snapshot; no production data and no side effects outside demo DB."""
    with SessionLocal() as db:
        original = db.get(Booking, original_id)
        clone = Booking(agency_id=original.agency_id, amount_paise=original.amount_paise,
                        itinerary=original.itinerary, original_booking_id=original.id,
                        universe=label[:80], status=original.status)
        db.add(clone); db.commit(); return clone.id


def read_refund_total(booking_id: int) -> int:
    with SessionLocal() as db:
        return int(db.scalar(select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(Refund.booking_id == booking_id)) or 0)


class SafeASGI:
    def __init__(self, app, gate: SafetyGate, tokens: dict):
        self.app, self.gate, self.tokens = app, gate, tokens
        self.client = None

    async def __aenter__(self):
        # ASGITransport performs NO network IO; requests stay within this FastAPI process.
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                        base_url="http://synthetic-only.invalid", timeout=5)
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()

    async def call(self, actor: str, method: str, path: str, json=None):
        await self.gate.check(method, path)
        response = None
        error_type = None
        try:
            response = await self.client.request(
                method, path,
                headers={"Authorization": f"Bearer {self.tokens[actor]}",
                         "X-Scan-Origin": "TripParadox-Local"}, json=json)
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            # Every attempted in-process request is auditable, even if the ASGI
            # server raises before providing an HTTP status. No auth tokens or
            # request bodies enter the log.
            with SessionLocal() as db:
                import re
                normalized = re.sub(r'/\d+(?=/|$)', '/{id}', path)
                db.add(Audit(action="synthetic_request", actor=actor,
                             result=str(response.status_code) if response else "error",
                             metadata_={"scan_id": self.gate.run_id,
                                        "method": method,
                                        "path_template": normalized,
                                        "sequence": self.gate.total,
                                        "error_type": error_type}))
                db.commit()
        if response.status_code in (429, 500, 502, 503, 504):
            raise StopScan(f"Target health threshold reached (HTTP {response.status_code})")
        return response


async def case_cross_agency(safe: SafeASGI, run_id: int, verify=True):
    root = baseline_booking()
    a = fresh_universe(root, f"run-{run_id}-authorized")
    b = fresh_universe(root, f"run-{run_id}-foreign")
    own = await safe.call("atlas_agent", "GET", f"/sim/bookings/{a}")
    foreign = await safe.call("bluebird_agent", "GET", f"/sim/bookings/{b}")
    violated = own.status_code == 200 and foreign.status_code == 200
    confirmed = violated
    if violated and verify:
        verify_id = fresh_universe(root, f"run-{run_id}-reproduce")
        confirmation = await safe.call("bluebird_agent", "GET", f"/sim/bookings/{verify_id}")
        confirmed = confirmation.status_code == 200
    return {
        "violated": violated, "confirmed": confirmed,
        "expected": "own=200, foreign=403", "observed": f"own={own.status_code}, foreign={foreign.status_code}",
        "details": {"authorized_status": own.status_code, "cross_agency_status": foreign.status_code,
                    "reproduced": confirmed, "rule": "Agency ownership must be enforced", "synthetic_only": True}
    }


async def case_double_refund(safe: SafeASGI, run_id: int, verify=True):
    root = baseline_booking()
    def amt():
        with SessionLocal() as db:
            return db.get(Booking, root).amount_paise
    amount = amt()

    async def sequence(suffix, repeats):
        cloned = fresh_universe(root, f"run-{run_id}-{suffix}")
        bodies = []
        for _ in range(repeats):
            r = await safe.call("atlas_agent", "POST", f"/sim/bookings/{cloned}/refund",
                                json={"amount_paise": amount, "idempotency_key": f"proof-{run_id}-{suffix}"})
            bodies.append({"status": r.status_code, "idempotent": r.json().get("idempotent_replay", False) if r.status_code == 200 else None})
        return read_refund_total(cloned), bodies

    baseline_total, _ = await sequence("baseline", 1)
    alternate_total, outcomes = await sequence("counterfactual", 2)
    violated = baseline_total == amount and alternate_total > amount
    confirmed = violated
    if violated and verify:
        reproducing_total, _ = await sequence("reproduce", 2)
        confirmed = reproducing_total > amount
    return {
        "violated": violated, "confirmed": confirmed,
        "expected": f"refund total <= {amount} paise", "observed": f"parallel total={alternate_total} paise",
        "details": {"baseline_total_paise": baseline_total, "alternate_total_paise": alternate_total,
                    "paid_paise": amount, "reproduced": confirmed, "responses": outcomes,
                    "rule": "Refund must not exceed original payment", "synthetic_only": True}
    }


async def case_legacy_bypass(safe: SafeASGI, run_id: int, verify=True):
    root = baseline_booking()
    b = fresh_universe(root, f"run-{run_id}-legacy")
    forbidden = await safe.call("bluebird_agent", "GET", f"/sim/legacy/v1/bookings/{b}")
    violated = forbidden.status_code == 200
    confirmed = violated
    if violated and verify:
        b2 = fresh_universe(root, f"run-{run_id}-legacy-reproduce")
        r2 = await safe.call("bluebird_agent", "GET", f"/sim/legacy/v1/bookings/{b2}")
        confirmed = r2.status_code == 200
    return {"violated": violated, "confirmed": confirmed,
            "expected": "foreign=403", "observed": f"foreign={forbidden.status_code}",
            "details": {"foreign_status": forbidden.status_code, "reproduced": confirmed,
                        "rule": "Legacy endpoint must preserve agency access boundaries", "synthetic_only": True}}


CASE_FUNCTIONS = {"cross_agency": case_cross_agency,
                  "double_refund": case_double_refund, "legacy_bypass": case_legacy_bypass}


def persist_test(run_id: int, kind: str, result: dict, retest_of: int | None = None):
    with SessionLocal() as db:
        db.add(Evidence(scan_id=run_id, test=kind, universe="counterfactual",
                        passed=not result["violated"], expected=result["expected"],
                        observed=result["observed"], details=result["details"]))
        if result["violated"] and result["confirmed"] and retest_of is None:
            spec = CASES[kind]
            finding = Finding(scan_id=run_id, fingerprint=spec["fingerprint"], kind=kind,
                              title=spec["title"], severity=spec["severity"], owner=spec["owner"],
                              description=spec["description"], recommended_fix=spec["fix"],
                              proof={"expected": result["expected"], "observed": result["observed"],
                                     "details": result["details"], "method": "bounded synthetic replay"})
            db.add(finding); db.flush()
            db.add(Ticket(finding_id=finding.id, owner=spec["owner"],
                          state="needs-human-review", note="Confirmed on synthetic state; human review before escalation."))
        db.commit()


async def run_pipeline(app, deploy_id: int | None = None, kinds: list[str] | None = None,
                       retest_of: int | None = None, existing_run_id: int | None = None) -> int:
    """Autonomous local ML-guided planner + deterministic, bounded proof engine."""
    from .ml_planner import prioritize, train_models
    from .model_registry import save_prediction
    async with RUN_LOCK:
        with SessionLocal() as db:
            if existing_run_id:
                run = db.get(ScanRun, existing_run_id)
                if not run or run.status not in ('queued', 'running'):
                    raise ValueError('Unknown or completed scan')
                run.status = 'running'
                run.started_at = utcnow()
            else:
                run = ScanRun(deploy_id=deploy_id, status='running')
                db.add(run)
            db.commit(); run_id = run.id
            db.add(Audit(action='scan_started', actor='agent', result='allowed',
                         metadata_={'scan_id': run_id, 'deploy_id': deploy_id}))
            db.commit()
        record_event(run_id, 'init', 'Safety envelope established', {
            'mode': 'in-process local ASGI only', 'budget': 40,
            'allowlist': ['/sim/bookings/{id}', '/sim/bookings/{id}/refund', '/sim/legacy/v1/bookings/{id}'],
            'external_requests': False, 'backend': 'services.safety.SafetyGate'}, 'active')
        # Approved rule registry, never user-provided/generated executable instructions.
        rule_file = Path(__file__).resolve().parents[1] / 'fixtures' / 'security_invariants.json'
        approved = {r['checker'] for r in json.loads(rule_file.read_text())['rules']
                    if r.get('checker') in CASE_FUNCTIONS}
        if kinds is not None:
            selected = kinds
        elif deploy_id is not None:
            from .planner import affected_cases
            with SessionLocal() as db:
                selected = affected_cases(db.get(Deploy, deploy_id))
        else:
            selected = list(CASES)
        selected = [case for case in selected if case in approved]
        plan = prioritize(selected)
        selected = [p['case'] for p in plan]
        with SessionLocal() as db:
            for prediction in plan:
                save_prediction(db, prediction, actor='synthetic-scan-agent',
                                case=prediction['case'], scan_id=run_id)
            db.commit()
        model_meta = train_models()[2]
        record_event(run_id, 'ml', 'Local ML models trained and evaluated', {
            'backend': 'services.ml_planner.train_models', 'models': [model_meta['risk_model'], model_meta['intent_model'], model_meta['anomaly_model']],
            'training_samples': model_meta['samples'],
            'synthetic_holdout_accuracy': model_meta['risk_holdout_accuracy_synthetic'],
            'dataset': model_meta['training_source'],
            'warning': 'Synthetic test accuracy is NOT real-world vulnerability accuracy'}, 'complete')
        record_event(run_id, 'plan', 'AI scored and prioritized the approved security journeys', {
            'backend': 'services.ml_planner.prioritize', 'ranked_tests': plan,
            'sql_tables': ['model_snapshots', 'model_predictions'],
            'model_version': model_meta['model_version'],
            'control': 'Every candidate must appear in approved invariant registry'}, 'complete')
        gate = SafetyGate(run_id)
        done, confirmed, outcomes = 0, 0, {}
        status = 'completed'
        try:
            with SessionLocal() as db:
                inventory = rebuild_inventory(db)
                inventory_labels = {i.path_template: i.classification for i in inventory}
            record_event(run_id, 'inventory', 'API surface reconstructed from approved fixtures', {
                'backend': 'services.inventory.rebuild_inventory', 'sql_tables': ['api_inventory', 'traffic'],
                'classification': inventory_labels}, 'complete')
            async with SafeASGI(app, gate, actor_tokens()) as safe:
                for item in plan:
                    kind = item['case']
                    with SessionLocal() as db:
                        if db.get(SimulatorConfig, 1).scanning_paused:
                            raise StopScan('Administrator paused scanning')
                    record_event(run_id, 'fork', f'Forking isolated booking universes · {kind}', {
                        'case': kind, 'backend': 'services.engine.fresh_universe',
                        'sql_tables': ['bookings', 'refunds'], 'model_risk_score': item['risk_priority_score'],
                        'principle': 'No real booking, payment or supplier API is touched'}, 'active')
                    result = await CASE_FUNCTIONS[kind](safe, run_id)
                    record_event(run_id, 'oracle', f'Business invariant evaluated · {kind}', {
                        'case': kind, 'backend': f'services.engine.case_{kind}',
                        'expected': result['expected'], 'observed': result['observed'],
                        'reproduced': result['confirmed'], 'violation': result['violated'],
                        'verified_by': 'deterministic persisted SQL state and HTTP response'},
                        'warning' if result['violated'] else 'complete')
                    persist_test(run_id, kind, result, retest_of)
                    done += 1
                    confirmed += int(result['violated'] and result['confirmed'])
                    outcomes[kind] = {'violated': result['violated'], 'confirmed': result['confirmed'],
                                      'observed': result['observed']}
                    record_event(run_id, 'evidence', f'{"Verified issue" if result["violated"] and result["confirmed"] else "Rule passed"} · {kind}', {
                        'case': kind, 'backend': 'services.engine.persist_test',
                        'sql_tables': ['evidence', 'findings', 'tickets'],
                        'human_review': bool(result['violated'] and result['confirmed']),
                        'requests_so_far': gate.total},
                        'warning' if result['violated'] else 'complete')
        except StopScan as exc:
            status = 'stopped'
            outcomes['safety_stop'] = str(exc)
            record_event(run_id, 'safety', 'Stopped by safety governor', {'reason': str(exc)}, 'blocked')
        except Exception as exc:
            status = 'error'
            outcomes['error'] = f'{type(exc).__name__}: {exc}'[:350]
            record_event(run_id, 'error', 'Scanner encountered a controlled failure',
                         {'exception_type': type(exc).__name__}, 'blocked')
        finally:
            with SessionLocal() as db:
                run = db.get(ScanRun, run_id)
                run.tests_run, run.confirmed, run.requests_sent = done, confirmed, gate.total
                run.finished_at, run.status = utcnow(), status
                run.summary = {'outcomes': outcomes, 'inventory': inventory_labels if 'inventory_labels' in locals() else {},
                               'target': 'bundled-synthetic-ASGI-only', 'max_requests': 40,
                               'test_set': selected, 'ml_ranked_plan': plan, 'no_external_network': True}
                db.add(Audit(action='scan_completed', actor='agent', result=status,
                             metadata_={'scan_id': run_id, 'confirmed': confirmed, 'requests': gate.total}))
                if retest_of is not None and status == 'completed' and done == 1:
                    prior = db.get(Finding, retest_of)
                    prior.retested_at = utcnow()
                    prior.status = 'fixed' if confirmed == 0 else 'confirmed'
                    ticket = db.scalar(select(Ticket).where(Ticket.finding_id == prior.id))
                    if ticket:
                        ticket.state = 'resolved' if confirmed == 0 else 'needs-human-review'
                db.commit()
            record_event(run_id, 'final', 'Run finalized and stored in SQL', {
                'status': status, 'tests': done, 'confirmed_findings': confirmed,
                'requests_sent': gate.total, 'backend': 'services.engine.run_pipeline',
                'sql_tables': ['scan_runs', 'run_events', 'audit']}, status)
        return run_id


async def safe_run_pipeline(app, deploy_id: int | None = None, kinds: list[str] | None = None,
                            retest_of: int | None = None, existing_run_id: int | None = None):
    """Ensure model/config/DB preflight failures do not strand a queued run.

    The inner runner already records controlled test-stage failures; this
    boundary also catches unexpected ML/inventory setup failures before that
    runner establishes its internal try/finally phase.
    """
    try:
        return await run_pipeline(app, deploy_id=deploy_id, kinds=kinds,
                                  retest_of=retest_of, existing_run_id=existing_run_id)
    except Exception as exc:
        if existing_run_id is None:
            raise
        with SessionLocal() as db:
            run = db.get(ScanRun, existing_run_id)
            if run is not None and run.status in ('queued', 'running'):
                run.status = 'error'; run.finished_at = utcnow()
                run.summary = {'reason': 'scanner-preflight-failed',
                               'exception_type': type(exc).__name__,
                               'external_requests': 0}
                db.add(RunEvent(run_id=existing_run_id, phase='error', status='blocked',
                                title='Scanner preflight failed safely',
                                details={'exception_type': type(exc).__name__}))
                db.add(Audit(action='scan_preflight_failure', actor='agent', result='error',
                             metadata_={'run_id': existing_run_id,
                                        'exception_type': type(exc).__name__}))
                db.commit()
        return existing_run_id
