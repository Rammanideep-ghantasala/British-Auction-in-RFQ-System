from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityLog


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _canonical_json(value: object) -> str:
    return json.dumps(value, default=_json_default, separators=(",", ":"), sort_keys=True)


def activity_entry_hash(
    *,
    auction_id: str,
    actor_user_id: str | None,
    sequence_number: int,
    previous_entry_hash: str | None,
    log_type: str,
    message: str,
    at: datetime,
    event_metadata: dict | None,
) -> str:
    payload = {
        "actor_user_id": actor_user_id,
        "at": _as_utc(at).isoformat(),
        "auction_id": auction_id,
        "event_metadata": event_metadata or {},
        "message": message,
        "previous_entry_hash": previous_entry_hash,
        "sequence_number": sequence_number,
        "type": log_type,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def append_activity_log(
    db: Session,
    *,
    auction_id: str,
    log_type: str,
    message: str,
    at: datetime | None = None,
    event_metadata: dict | None = None,
    actor_user_id: str | None = None,
) -> ActivityLog:
    previous_log = db.scalars(
        select(ActivityLog)
        .where(ActivityLog.auction_id == auction_id)
        .order_by(ActivityLog.sequence_number.desc().nullslast(), ActivityLog.at.desc())
        .limit(1)
    ).first()
    sequence_number = (previous_log.sequence_number if previous_log and previous_log.sequence_number else 0) + 1
    previous_entry_hash = previous_log.entry_hash if previous_log and previous_log.entry_hash else None
    logged_at = _as_utc(at or _utc_now())
    entry_hash = activity_entry_hash(
        auction_id=auction_id,
        actor_user_id=actor_user_id,
        sequence_number=sequence_number,
        previous_entry_hash=previous_entry_hash,
        log_type=log_type,
        message=message,
        at=logged_at,
        event_metadata=event_metadata,
    )

    log = ActivityLog(
        auction_id=auction_id,
        actor_user_id=actor_user_id,
        sequence_number=sequence_number,
        previous_entry_hash=previous_entry_hash,
        entry_hash=entry_hash,
        type=log_type,
        message=message,
        at=logged_at,
        event_metadata=event_metadata,
    )
    db.add(log)
    db.flush()
    return log


def verify_activity_log_chain(logs: Iterable[ActivityLog]) -> bool:
    previous_hash: str | None = None
    for expected_sequence, log in enumerate(logs, start=1):
        if log.sequence_number != expected_sequence:
            return False
        if log.previous_entry_hash != previous_hash:
            return False
        if log.entry_hash != activity_entry_hash(
            auction_id=log.auction_id,
            actor_user_id=log.actor_user_id,
            sequence_number=expected_sequence,
            previous_entry_hash=previous_hash,
            log_type=log.type,
            message=log.message,
            at=log.at,
            event_metadata=log.event_metadata,
        ):
            return False
        previous_hash = log.entry_hash
    return True
