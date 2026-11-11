from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import HTTPAuthorizationCredentials
from datetime import datetime, timezone
import hashlib
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole, RevokedToken
from app.schemas import AuthResponse, LoginRequest, UserRead
from app.security import create_access_token, ensure_role, get_current_user, verify_password, hash_password, password_iterations, bearer_scheme, decode_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalars(select(User).where(func.lower(User.email) == payload.email.strip().lower())).first()
    if user is None or not user.is_active:
        hash_password(payload.password)  # Keep unknown-account failures comparably expensive.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    if not verify_password(payload.password, user.password_hash, user.password_salt):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    if not user.password_hash.startswith(f"pbkdf2_sha256${password_iterations}$"):
        user.password_hash, user.password_salt = hash_password(payload.password)
        db.commit()

    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user}


@router.post("/logout", status_code=204)
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
           current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = decode_access_token(credentials.credentials)
    db.merge(RevokedToken(token_hash=hashlib.sha256(credentials.credentials.encode()).hexdigest(),
                         expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc)))
    db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/suppliers", response_model=list[UserRead])
def list_suppliers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    ensure_role(current_user, (UserRole.BUYER,))
    return list(
        db.scalars(
            select(User)
            .where(User.role == UserRole.SUPPLIER.value, User.is_active.is_(True))
            .order_by(User.company_name)
        )
    )
