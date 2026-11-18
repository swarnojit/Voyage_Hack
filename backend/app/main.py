from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import text
from .config import settings
from .database import Base, engine, SessionLocal
from .models import SimulatorConfig
from .seed import seed
from .migrations import migrate_demo_schema
from .routers import api, simulator


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings().demo_mode:
        raise RuntimeError("This intentionally vulnerable simulator may run only with TP_DEMO_MODE=true")
    Base.metadata.create_all(bind=engine)
    migrate_demo_schema(engine)
    with SessionLocal() as db:
        seed(db)
        if not settings().allow_intentional_flaws:
            # Even if an old demo database was left in vulnerable training
            # mode, restart with the default secure configuration.
            flags = db.get(SimulatorConfig, 1)
            flags.cross_agency_bug = False
            flags.double_refund_bug = False
            flags.legacy_bypass_bug = False
            db.commit()
    yield


app = FastAPI(title="TripParadox AI — Synthetic Security Lab", version="1.0.0", lifespan=lifespan,
              description="In-process, bounded, synthetic B2B travel security demonstration")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver', 'synthetic-only.invalid'])
app.add_middleware(CORSMiddleware, allow_origins=list(settings().cors_origins),
                   allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
app.include_router(api.router)
app.include_router(simulator.router)
STATIC = Path(__file__).resolve().parent / 'static'
app.mount('/lab-assets', StaticFiles(directory=STATIC), name='lab-assets')

@app.get('/lab', include_in_schema=False)
def static_lab():
    return FileResponse(STATIC / 'index.html', media_type='text/html')


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resp.headers["Cache-Control"] = "no-store"
    if request.url.path == '/lab' or request.url.path.startswith('/lab-assets/'):
        resp.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    else:
        resp.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
    return resp


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "mode": "synthetic-only", "external_scanning": False}


@app.get("/health/db", tags=["health"])
def health_db():
    """No credentials or connection string exposed to clients."""
    with SessionLocal() as db:
        db.execute(text('SELECT 1')).scalar_one()
        return {"status": "ok", "database": db.bind.dialect.name,
                "mode": "synthetic-only", "external_scanning": False}
