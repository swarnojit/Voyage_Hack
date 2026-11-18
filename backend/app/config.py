"""Strong separation of synthetic demo settings from any production infrastructure."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    admin_password: str
    agency_password: str
    cors_origins: tuple[str, ...]
    demo_mode: bool
    allow_intentional_flaws: bool


def settings() -> Settings:
    secret = os.getenv("TP_JWT_SECRET", "")
    admin_password = os.getenv("TP_ADMIN_PASSWORD", "")
    agency_password = os.getenv("TP_AGENCY_PASSWORD", "")
    if not secret or len(secret) < 32:
        raise RuntimeError("TP_JWT_SECRET must be set to at least 32 characters. Run scripts/bootstrap.py")
    if len(admin_password) < 12 or len(agency_password) < 12:
        raise RuntimeError("Set TP_ADMIN_PASSWORD and TP_AGENCY_PASSWORD to 12+ characters")
    origins = os.getenv("TP_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        database_url=os.getenv("TP_DATABASE_URL", "sqlite:///./tripparadox.db"),
        jwt_secret=secret,
        admin_password=admin_password,
        agency_password=agency_password,
        cors_origins=tuple(v.strip() for v in origins.split(",") if v.strip()),
        demo_mode=os.getenv("TP_DEMO_MODE", "true").lower() == "true",
        allow_intentional_flaws=os.getenv("TP_ALLOW_INTENTIONAL_FLAWS", "false").lower() == "true",
    )
