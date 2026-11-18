"""Discover synthetic routes from observed HAR-like logs and old JavaScript artifacts.

No OpenAPI spec is fed to discovery. This is a bounded offline adapter for the
kind of traffic/JS observations provided by the challenge. It does not enumerate
real hosts, domains, paths or credentials.
"""
import json
import re
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Inventory, Traffic, utcnow

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OWNER_GUESSES = {
    'legacy': 'Legacy Integration Team',
    'partner': 'Partner Integrations',
    'refund': 'Payments Team',
    'booking': 'Booking API Team',
}


def normalise(route: str) -> str:
    return re.sub(r'/\d+(?=/|$)', '/{id}', route.split('?')[0])


def infer_routes() -> list[tuple[str,str,bool,str]]:
    """Consolidate simulated sources instead of importing FastAPI's OpenAPI map."""
    documented = json.loads((FIXTURES / 'documented_api_routes.json').read_text())
    official = {(x['path'],x['method']): x['owner'] for x in documented}
    discovered = set(official)
    traffic = json.loads((FIXTURES / 'gateway_access.json').read_text())
    for event in traffic['observations']:
        path = normalise(event['path'])
        if path.startswith('/sim/'):
            discovered.add((path,event['method']))
    js = (FIXTURES / 'old_frontend_bundle.js.txt').read_text()
    for endpoint in re.findall(r'[\x27\"](/sim/[a-zA-Z0-9_./-]+)[\x27\"]',js):
        discovered.add((normalise(endpoint), 'GET'))
    rows = []
    for path,method in sorted(discovered):
        owner = official.get((path,method))
        if owner is None:
            owner = next((x for term,x in OWNER_GUESSES.items() if term in path),'Unknown - review owner')
        rows.append((path,method,(path,method) in official,owner))
    return rows


def rebuild_inventory(db: Session) -> list[Inventory]:
    cutoff = utcnow() - timedelta(days=30)
    # Dynamically incorporate legitimate local travel-portal calls, never scan traffic.
    # This demonstrates how a route absent from the published mapping becomes "shadow".
    routes = {(path, method): (documented, owner) for path, method, documented, owner in infer_routes()}
    observed = db.scalars(select(Traffic).where(Traffic.source == 'business')).all()
    for traffic in observed:
        key = (normalise(traffic.path_template), traffic.method)
        if key not in routes:
            owner = next((v for term, v in OWNER_GUESSES.items() if term in key[0]), 'Unknown - review owner')
            routes[key] = (False, owner)
    entries = []
    for (path, method), (documented, owner) in sorted(routes.items()):
        seen = db.scalars(select(Traffic).where(
            Traffic.path_template == path,
            Traffic.source == 'business', Traffic.recorded_at >= cutoff
        ).order_by(Traffic.recorded_at.desc())).first()
        kind = 'shadow' if seen and not documented else 'active' if seen else 'zombie'
        recommendation = {
            'shadow': 'Confirm owner and document; review least privilege.',
            'zombie': 'Restrict or retire only after dependency and usage review.',
            'active': 'Maintain ownership and regression coverage.'
        }[kind]
        entry = db.scalar(select(Inventory).where(Inventory.path_template==path))
        if entry is None:
            entry=Inventory(path_template=path,method=method,classification=kind,
                            documented=documented,seen_in_logs=bool(seen),
                            last_legitimate_seen=seen.recorded_at if seen else None,
                            owner=owner,recommendation=recommendation)
            db.add(entry)
        else:
            entry.method,entry.classification,entry.documented=method,kind,documented
            entry.seen_in_logs,entry.last_legitimate_seen=bool(seen),seen.recorded_at if seen else None
            entry.owner,entry.recommendation=owner,recommendation
        entries.append(entry)
    db.commit()
    return entries
