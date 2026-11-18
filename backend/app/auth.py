"""Signed short-lived JWT authentication; no credentials inside source code."""
import datetime as dt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db
from .models import User

ph = PasswordHasher()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(pw: str) -> str:
    return ph.hash(pw)


def verify_password(pw: str, hash_: str) -> bool:
    try:
        return ph.verify(hash_, pw)
    except (VerifyMismatchError, VerificationError):
        return False


def issue_token(user: User, ttl_minutes: int = 40) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({
        "sub": str(user.id), "role": user.role, "agency": user.agency_id,
        "aud": "tripparadox", "iat": now, "exp": now + dt.timedelta(minutes=ttl_minutes)
    }, settings().jwt_secret, algorithm="HS256")


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, settings().jwt_secret, algorithms=["HS256"], audience="tripparadox")
        user = db.get(User, int(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    if user is None or payload.get("role") != user.role or payload.get("agency") != user.agency_id:
        raise HTTPException(401, "Invalid session")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return user
