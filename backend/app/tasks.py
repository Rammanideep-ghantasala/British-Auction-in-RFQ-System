from datetime import datetime, timezone
from sqlalchemy import delete
from sqlalchemy.exc import OperationalError

from app.celery_app import celery_app
from app.db import SessionLocal
from app.services.auction import as_utc
from app.services.auction_closure import close_expired_auctions as close_expired_auctions_service
from app.models import JobHeartbeat, RevokedToken


@celery_app.task(name="app.tasks.close_expired_auctions", autoretry_for=(OperationalError,), retry_backoff=True, max_retries=3)
def close_expired_auctions(now_iso: str | None = None) -> dict[str, int]:
    now = as_utc(datetime.fromisoformat(now_iso.replace("Z", "+00:00"))) if now_iso else None
    db = SessionLocal()
    try:
        closed_count = 0
        for _ in range(50):
            count = close_expired_auctions_service(db, now=now)
            closed_count += count
            if count < 100:
                break
        succeeded_at = datetime.now(timezone.utc)
        db.merge(JobHeartbeat(name="auction-close", succeeded_at=succeeded_at, processed_count=closed_count))
        db.execute(delete(RevokedToken).where(RevokedToken.expires_at < succeeded_at))
        db.commit()
        return {"closed_count": closed_count}
    finally:
        db.close()
