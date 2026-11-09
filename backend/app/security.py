from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Iterable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models import User, UserRole

password_iterations = 120_000
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class DemoUser:
    email: str
    password: str
    name: str
    company_name: str
    role: UserRole


DEMO_USERS = (
    DemoUser("buyer@gocomet.test", "password123", "Priya Buyer", "GoComet", UserRole.BUYER),
    DemoUser("apex@carrier.test", "password123", "Apex Dispatcher", "Apex Roadways", UserRole.SUPPLIER),
    DemoUser("swift@carrier.test", "password123", "Swift Ops", "Swift Freight", UserRole.SUPPLIER),
)


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    password_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt.encode("utf-8"),
        password_iterations,
    )
    return digest.hex(), password_salt


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    candidate_hash, _ = hash_password(password, password_salt)
    return hmac.compare_digest(candidate_hash, password_hash)


def create_access_token(user: User) -> str:
    expires_at = int(time.time()) + settings.access_token_minutes * 60
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "exp": expires_at,
    }
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(settings.secret_key.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_base64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed bearer token.") from exc

    expected_signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    supplied_signature = _base64url_decode(encoded_signature)
    if not hmac.compare_digest(expected_signature, supplied_signature):
        raise ValueError("Invalid bearer token signature.")

    payload = json.loads(_base64url_decode(encoded_payload))
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise ValueError("Bearer token has expired.")

    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    try:
        payload = decode_access_token(credentials.credentials)
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.") from None

    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive or no longer exists.")

    return user


def ensure_role(user: User, roles: Iterable[UserRole]) -> User:
    allowed = {role.value for role in roles}
    if user.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not allowed for your role.")
    return user


def require_buyer(current_user: User = Depends(get_current_user)) -> User:
    return ensure_role(current_user, (UserRole.BUYER,))


def require_supplier(current_user: User = Depends(get_current_user)) -> User:
    return ensure_role(current_user, (UserRole.SUPPLIER,))


def seed_demo_users(db: Session) -> None:
    if not settings.seed_demo_users:
        return

    for demo_user in DEMO_USERS:
        existing = db.scalars(select(User).where(User.email == demo_user.email)).first()
        if existing:
            continue

        password_hash, password_salt = hash_password(demo_user.password)
        db.add(
            User(
                email=demo_user.email,
                name=demo_user.name,
                company_name=demo_user.company_name,
                role=demo_user.role.value,
                password_hash=password_hash,
                password_salt=password_salt,
            )
        )

    db.commit()
