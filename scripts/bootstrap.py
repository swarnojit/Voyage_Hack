#!/usr/bin/env python3
"""Generate local-only demo credentials without shipping passwords or JWT keys."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
path = root / ".env"
if path.exists():
    print(".env already exists; refusing to overwrite secrets")
    raise SystemExit(1)
admin = secrets.token_urlsafe(18)
agency = secrets.token_urlsafe(18)
key = secrets.token_urlsafe(48)
pg_admin = secrets.token_urlsafe(28)
pg_app = secrets.token_urlsafe(28)
path.write_text(f"TP_DEMO_MODE=true\nTP_ALLOW_INTENTIONAL_FLAWS=false\nTP_JWT_SECRET={key}\nTP_ADMIN_PASSWORD={admin}\nTP_AGENCY_PASSWORD={agency}\nTP_DATABASE_URL=sqlite:///./tripparadox.db\nTP_PG_ADMIN_PASSWORD={pg_admin}\nTP_DB_PASSWORD={pg_app}\nTP_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173\n", encoding="utf-8")
path.chmod(0o600)
print("Generated .env (ignored by Git). Use these accounts:")
print(f"Admin:   admin / {admin}")
print(f"Agency A: atlas_agent / {agency}")
print(f"Agency B: bluebird_agent / {agency}")
print("PostgreSQL credentials are stored ONLY inside the ignored .env file.")
print("For PostgreSQL: docker compose up --build")
print("Store credentials locally. Never connect this demo to real systems.")
