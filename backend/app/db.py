from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models import Base


def _connect_args(database_url: str, runtime: bool = True) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {"connect_timeout": 10, **({"options": "-c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=30000"} if runtime else {})}


engine = create_engine(settings.database_url, connect_args=_connect_args(settings.database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    if settings.environment != "production":
        Base.metadata.create_all(bind=engine)
    from app.security import seed_demo_users

    db = SessionLocal()
    try:
        seed_demo_users(db)
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
