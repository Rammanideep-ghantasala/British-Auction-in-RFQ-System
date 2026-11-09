from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RFQAuction
from app.services.audit import append_activity_log
from app.services.auction import as_utc

SCHEDULED_CLOSE = "scheduled-close"
FORCED_CLOSE = "forced-close"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _close_reason(auction: RFQAuction, now: datetime) -> tuple[str, datetime]:
    forced_close_at = as_utc(auction.forced_close_at)
    close_at = as_utc(auction.close_at)
    if now >= forced_close_at or close_at >= forced_close_at:
        return FORCED_CLOSE, forced_close_at
    return SCHEDULED_CLOSE, close_at


def close_expired_auctions(db: Session, now: datetime | None = None, limit: int = 100) -> int:
    current_time = as_utc(now or _now())
    expired_auctions = list(
        db.scalars(
            select(RFQAuction)
            .where(RFQAuction.closed_at.is_(None), RFQAuction.close_at <= current_time)
            .order_by(RFQAuction.close_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )

    closed_count = 0
    for auction in expired_auctions:
        reason, closed_at = _close_reason(auction, current_time)
        auction.closed_at = closed_at
        auction.close_reason = reason

        if reason == FORCED_CLOSE:
            message = f"RFQ {auction.reference_id} reached the forced close time."
        else:
            message = f"RFQ {auction.reference_id} closed at the scheduled bid close time."

        append_activity_log(
            db,
            auction_id=auction.id,
            log_type="closed",
            message=message,
            at=closed_at,
            event_metadata={"close_reason": reason, "closed_at": closed_at.isoformat()},
        )
        closed_count += 1

    if closed_count:
        db.commit()

    return closed_count
