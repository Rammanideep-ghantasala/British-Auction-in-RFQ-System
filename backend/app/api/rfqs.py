from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import ActivityLog, AuctionInvitation, Bid, RFQAuction, User, UserRole
from app.schemas import AuctionCreate, AuctionDetail, AuctionPage, BidCreate
from app.security import ensure_role, get_current_user
from app.services.audit import append_activity_log
from app.services import auction as auction_service

router = APIRouter(prefix="/api/rfqs", tags=["rfqs"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_auction(db: Session, auction_id: str, *, for_update: bool = False) -> RFQAuction:
    statement = (
        select(RFQAuction)
        .where(RFQAuction.id == auction_id)
        .options(
            selectinload(RFQAuction.bids),
            selectinload(RFQAuction.activity_logs),
            selectinload(RFQAuction.invitations),
        )
    )
    if for_update:
        statement = statement.with_for_update()

    auction = db.scalars(statement).first()
    if auction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ auction not found.")

    return auction


def _user_can_view_auction(user: User, auction: RFQAuction) -> bool:
    if user.role == UserRole.BUYER.value:
        return auction.created_by_user_id == user.id
    if user.role == UserRole.SUPPLIER.value:
        return any(invitation.supplier_user_id == user.id for invitation in auction.invitations)
    return False


def _ensure_can_view(user: User, auction: RFQAuction) -> None:
    if not _user_can_view_auction(user, auction):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this RFQ.")


def _bid_read(bid: Bid) -> dict:
    return {
        "id": bid.id,
        "carrier_name": bid.carrier_name,
        "freight_charges": auction_service.money(bid.freight_charges),
        "origin_charges": auction_service.money(bid.origin_charges),
        "destination_charges": auction_service.money(bid.destination_charges),
        "transit_time": bid.transit_time,
        "validity": bid.validity,
        "submitted_at": auction_service.as_utc(bid.submitted_at),
        "total": auction_service.quote_total(bid),
    }


def _log_read(log: ActivityLog) -> dict:
    return {
        "id": log.id,
        "type": log.type,
        "message": log.message,
        "at": auction_service.as_utc(log.at),
        "event_metadata": log.event_metadata,
    }


def _rank_read(rank: auction_service.RankedQuote, viewer: User | None = None) -> dict:
    is_supplier = viewer is not None and viewer.role == UserRole.SUPPLIER.value
    is_own_quote = is_supplier and rank.carrier_key == auction_service.carrier_key(viewer.company_name)
    if is_supplier and not is_own_quote:
        return {
            "carrier_name": f"Supplier {rank.rank}",
            "freight_charges": Decimal("0.00"),
            "origin_charges": Decimal("0.00"),
            "destination_charges": Decimal("0.00"),
            "transit_time": "Hidden",
            "validity": "Hidden",
            "submitted_at": rank.submitted_at,
            "total": rank.total,
            "rank_number": rank.rank_number,
            "rank": rank.rank,
        }

    return {
        "carrier_name": rank.carrier_name,
        "freight_charges": rank.freight_charges,
        "origin_charges": rank.origin_charges,
        "destination_charges": rank.destination_charges,
        "transit_time": rank.transit_time,
        "validity": rank.validity,
        "submitted_at": rank.submitted_at,
        "total": rank.total,
        "rank_number": rank.rank_number,
        "rank": rank.rank,
    }


def _visible_activity_logs(auction: RFQAuction, viewer: User) -> list[ActivityLog]:
    if viewer.role == UserRole.BUYER.value:
        return list(auction.activity_logs)

    visible_logs: list[ActivityLog] = []
    for log in auction.activity_logs:
        carrier_name = (log.event_metadata or {}).get("carrier_name")
        if log.type != "bid" or auction_service.carrier_key(str(carrier_name)) == auction_service.carrier_key(viewer.company_name):
            visible_logs.append(log)
    return visible_logs


def _auction_summary(auction: RFQAuction, now: datetime) -> dict:
    rankings = auction_service.current_rankings(auction.bids)

    return {
        "id": auction.id,
        "name": auction.name,
        "reference_id": auction.reference_id,
        "current_lowest_bid": rankings[0].total if rankings else None,
        "close_at": auction_service.as_utc(auction.close_at),
        "forced_close_at": auction_service.as_utc(auction.forced_close_at),
        "status": auction_service.auction_status(auction, now),
    }


def _auction_detail(auction: RFQAuction, now: datetime, viewer: User) -> dict:
    rankings = auction_service.current_rankings(auction.bids)
    visible_bids = list(auction.bids)
    if viewer.role == UserRole.SUPPLIER.value:
        visible_bids = [bid for bid in visible_bids if bid.supplier_user_id == viewer.id]

    return {
        "id": auction.id,
        "name": auction.name,
        "reference_id": auction.reference_id,
        "british_auction_enabled": auction.british_auction_enabled,
        "start_at": auction_service.as_utc(auction.start_at),
        "original_close_at": auction_service.as_utc(auction.original_close_at),
        "close_at": auction_service.as_utc(auction.close_at),
        "forced_close_at": auction_service.as_utc(auction.forced_close_at),
        "pickup_at": auction_service.as_utc(auction.pickup_at),
        "status": auction_service.auction_status(auction, now),
        "config": {
            "trigger_window_minutes": auction.trigger_window_minutes,
            "extension_minutes": auction.extension_minutes,
            "trigger_type": auction.trigger_type,
        },
        "current_lowest_bid": rankings[0].total if rankings else None,
        "invited_supplier_ids": [invitation.supplier_user_id for invitation in auction.invitations],
        "rankings": [_rank_read(rank, viewer) for rank in rankings],
        "bids": [_bid_read(bid) for bid in sorted(visible_bids, key=auction_service.quote_total)],
        "activity_log": [_log_read(log) for log in reversed(_visible_activity_logs(auction, viewer))],
    }


def _auction_list_statement(user: User):
    if user.role == UserRole.BUYER.value:
        return select(RFQAuction).where(RFQAuction.created_by_user_id == user.id)

    if user.role == UserRole.SUPPLIER.value:
        return (
            select(RFQAuction)
            .join(AuctionInvitation, AuctionInvitation.auction_id == RFQAuction.id)
            .where(AuctionInvitation.supplier_user_id == user.id)
        )

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This action is not allowed for your role.")


def _invited_suppliers(db: Session, supplier_ids: list[str]) -> list[User]:
    unique_supplier_ids = sorted(set(supplier_ids))
    if not unique_supplier_ids:
        return []

    suppliers = list(
        db.scalars(
            select(User).where(
                User.id.in_(unique_supplier_ids),
                User.role == UserRole.SUPPLIER.value,
                User.is_active.is_(True),
            )
        )
    )
    if len(suppliers) != len(unique_supplier_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=["One or more suppliers are invalid."])
    return suppliers


@router.get("", response_model=AuctionPage)
def list_auctions(
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    base_statement = _auction_list_statement(current_user)
    total = db.scalar(select(func.count()).select_from(base_statement.subquery())) or 0
    auctions = db.scalars(
        base_statement.options(selectinload(RFQAuction.bids))
        .order_by(RFQAuction.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    now = _now()
    return {
        "items": [_auction_summary(auction, now) for auction in auctions],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", response_model=AuctionDetail, status_code=status.HTTP_201_CREATED)
def create_auction(
    payload: AuctionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    ensure_role(current_user, (UserRole.BUYER,))
    duplicate = db.scalars(
        select(RFQAuction).where(func.lower(RFQAuction.reference_id) == payload.reference_id.strip().lower())
    ).first()
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=["Reference ID must be unique."])

    config = payload.config
    errors = auction_service.validate_auction_window(
        name=payload.name,
        reference_id=payload.reference_id,
        british_auction_enabled=payload.british_auction_enabled,
        start_at=payload.start_at,
        close_at=payload.close_at,
        forced_close_at=payload.forced_close_at,
        pickup_at=payload.pickup_at,
        trigger_window_minutes=config.trigger_window_minutes,
        extension_minutes=config.extension_minutes,
        trigger_type=config.trigger_type.value,
    )
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)

    suppliers = _invited_suppliers(db, payload.supplier_ids)
    auction = RFQAuction(
        name=payload.name.strip(),
        reference_id=auction_service.normalize_reference(payload.reference_id),
        british_auction_enabled=payload.british_auction_enabled,
        created_by_user_id=current_user.id,
        start_at=auction_service.as_utc(payload.start_at),
        original_close_at=auction_service.as_utc(payload.close_at),
        close_at=auction_service.as_utc(payload.close_at),
        forced_close_at=auction_service.as_utc(payload.forced_close_at),
        pickup_at=auction_service.as_utc(payload.pickup_at),
        trigger_window_minutes=config.trigger_window_minutes,
        extension_minutes=config.extension_minutes,
        trigger_type=config.trigger_type.value,
    )
    db.add(auction)

    try:
        db.flush()
        for supplier in suppliers:
            db.add(AuctionInvitation(auction_id=auction.id, supplier_user_id=supplier.id))
        append_activity_log(
            db,
            auction_id=auction.id,
            log_type="created",
            message=f"RFQ {auction.reference_id} created.",
            at=auction.created_at,
            event_metadata={"supplier_count": len(suppliers)},
            actor_user_id=current_user.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=["Reference ID must be unique."]) from None

    db.expire_all()
    return _auction_detail(_load_auction(db, auction.id), _now(), current_user)


@router.get("/{auction_id}", response_model=AuctionDetail)
def get_auction(
    auction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    auction = _load_auction(db, auction_id)
    _ensure_can_view(current_user, auction)
    return _auction_detail(auction, _now(), current_user)


@router.post("/{auction_id}/bids", response_model=AuctionDetail, status_code=status.HTTP_201_CREATED)
def submit_bid(
    auction_id: str,
    payload: BidCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    ensure_role(current_user, (UserRole.SUPPLIER,))
    auction = _load_auction(db, auction_id, for_update=True)
    _ensure_can_view(current_user, auction)

    supplier_carrier_name = current_user.company_name.strip()
    requested_carrier_name = (payload.carrier_name or supplier_carrier_name).strip()
    if auction_service.carrier_key(requested_carrier_name) != auction_service.carrier_key(supplier_carrier_name):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Suppliers can only submit quotes as their assigned company.",
        )

    submitted_at = auction_service.as_utc(_now())
    candidate = auction_service.BidCandidate(
        carrier_name=supplier_carrier_name,
        freight_charges=auction_service.money(payload.freight_charges),
        origin_charges=auction_service.money(payload.origin_charges),
        destination_charges=auction_service.money(payload.destination_charges),
        transit_time=payload.transit_time.strip(),
        validity=payload.validity.strip(),
        submitted_at=submitted_at,
    )
    decision = auction_service.evaluate_bid(auction, auction.bids, candidate)

    if decision.errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=decision.errors)

    bid = Bid(
        auction_id=auction.id,
        supplier_user_id=current_user.id,
        carrier_name=candidate.carrier_name,
        freight_charges=candidate.freight_charges,
        origin_charges=candidate.origin_charges,
        destination_charges=candidate.destination_charges,
        transit_time=candidate.transit_time,
        validity=candidate.validity,
        submitted_at=submitted_at,
    )
    db.add(bid)
    append_activity_log(
        db,
        auction_id=auction.id,
        log_type="bid",
        message=f"{candidate.carrier_name} submitted a quote totaling {auction_service.quote_total(candidate):.2f}.",
        at=submitted_at,
        event_metadata={"carrier_name": candidate.carrier_name, "total": str(auction_service.quote_total(candidate))},
        actor_user_id=current_user.id,
    )

    if decision.extension and decision.extension.applied:
        auction.close_at = decision.extension.next_close_at
        capped_text = " The forced close cap was applied." if decision.extension.capped_by_forced_close else ""
        append_activity_log(
            db,
            auction_id=auction.id,
            log_type="extension",
            message=f"Bid close extended to {auction.close_at.isoformat()}. {decision.extension.reason}{capped_text}",
            at=submitted_at,
            event_metadata={
                "previous_close_at": decision.extension.previous_close_at.isoformat(),
                "next_close_at": decision.extension.next_close_at.isoformat(),
                "trigger_type": auction.trigger_type,
                "capped_by_forced_close": decision.extension.capped_by_forced_close,
            },
            actor_user_id=current_user.id,
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bid could not be saved. Please retry.") from None

    db.expire_all()
    return _auction_detail(_load_auction(db, auction.id), _now(), current_user)
