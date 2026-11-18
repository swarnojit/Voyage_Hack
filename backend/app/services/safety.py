"""In-process only, fixed-scope security tester: cannot target external hosts.
Enforces bounded requests and an immediate persistent kill switch.
"""
import asyncio
import re
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ..models import Audit, SimulatorConfig
from ..database import SessionLocal


class StopScan(Exception):
    pass


class SafetyGate:
    def __init__(self, run_id: int, max_requests: int = 40, min_interval: float = .015):
        self.run_id = run_id
        self.remaining = max_requests
        self.total = 0
        self.min_interval = min_interval

    async def check(self, method: str, path: str):
        # All traffic is routed to the in-memory ASGI application, never to a URL.
        route_allowlist = (("GET", r"/sim/bookings/[0-9]+"),
                           ("POST", r"/sim/bookings/[0-9]+/refund"),
                           ("GET", r"/sim/legacy/v1/bookings/[0-9]+"))
        if not any(method.upper() == m and re.fullmatch(pattern, path) for m, pattern in route_allowlist):
            raise StopScan("Request outside the exact approved synthetic route allowlist")
        with SessionLocal() as db:
            cfg = db.get(SimulatorConfig, 1)
            if not cfg or cfg.scanning_paused:
                db.add(Audit(action="security_gate", actor="agent", result="blocked", metadata_={"reason": "kill-switch"}))
                db.commit()
                raise StopScan("Administrator kill switch is active")
            if self.remaining <= 0:
                db.add(Audit(action="security_gate", actor="agent", result="blocked", metadata_={"reason": "request-budget"}))
                db.commit()
                raise StopScan("Request budget exhausted")
        self.remaining -= 1
        self.total += 1
        await asyncio.sleep(self.min_interval)
