"""Change-aware case planner: only test invariants affected by a synthetic deploy.
Manual full scans still cover all registered invariants.
"""
from ..models import Deploy
from .engine import CASES

CASE_ROUTES = {
    'cross_agency': 'GET /sim/bookings/{id}',
    'double_refund': 'POST /sim/bookings/{id}/refund',
    'legacy_bypass': 'GET /sim/legacy/v1/bookings/{id}',
}


def affected_cases(deploy: Deploy | None) -> list[str]:
    if deploy is None: return list(CASES)
    changed = set(deploy.changed_routes or [])
    return [kind for kind, route in CASE_ROUTES.items() if route in changed]
