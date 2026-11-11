"""Bounded read models: one current quote per account, paginated history."""
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.models import Bid, ActivityLog


def latest_bids(db: Session, auction_ids: list[str]) -> list[Bid]:
    if not auction_ids:
        return []
    latest = select(
        Bid.id,
        func.row_number().over(
            partition_by=(Bid.auction_id, Bid.supplier_user_id),
            order_by=(Bid.submitted_at.desc(), Bid.id.desc()),
        ).label("position"),
    ).where(Bid.auction_id.in_(auction_ids)).subquery()
    return list(db.scalars(select(Bid).join(latest, Bid.id == latest.c.id).where(latest.c.position == 1)))


def history(db: Session, auction_id: str, viewer, limit: int, bids_offset: int, activity_offset: int):
    bids = select(Bid).where(Bid.auction_id == auction_id)
    logs = select(ActivityLog).where(ActivityLog.auction_id == auction_id)
    if viewer.role == "supplier":
        bids = bids.where(Bid.supplier_user_id == viewer.id)
        logs = logs.where(or_(ActivityLog.type != "bid", ActivityLog.actor_user_id == viewer.id))
    bid_count = db.scalar(select(func.count()).select_from(bids.subquery())) or 0
    log_count = db.scalar(select(func.count()).select_from(logs.subquery())) or 0
    bids = bids.order_by(Bid.freight_charges + Bid.origin_charges + Bid.destination_charges, Bid.submitted_at, Bid.id)
    logs = logs.order_by(ActivityLog.sequence_number.desc())
    return (
        list(db.scalars(bids.offset(bids_offset).limit(limit))),
        list(db.scalars(logs.offset(activity_offset).limit(limit))),
        bid_count, log_count,
    )
