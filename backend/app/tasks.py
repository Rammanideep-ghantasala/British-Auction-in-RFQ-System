from datetime import datetime

from app.celery_app import celery_app
from app.db import SessionLocal
from app.services.auction import as_utc
from app.services.auction_closure import close_expired_auctions as close_expired_auctions_service


@celery_app.task(name="app.tasks.close_expired_auctions")
def close_expired_auctions(now_iso: str | None = None) -> dict[str, int]:
    now = as_utc(datetime.fromisoformat(now_iso.replace("Z", "+00:00"))) if now_iso else None
    db = SessionLocal()
    try:
        closed_count = close_expired_auctions_service(db, now=now)
        return {"closed_count": closed_count}
    finally:
        db.close()
