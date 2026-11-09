from decimal import Decimal
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth as auth_routes
from app.api import rfqs as rfq_routes
from app.main import health
from app.models import Base, User, UserRole
from app.schemas import AuctionConfigIn, AuctionCreate, BidCreate, LoginRequest
from app.security import decode_access_token, get_current_user, seed_demo_users
from app.services.auction import TriggerType


def make_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = testing_session_local()
    seed_demo_users(db)
    return db


def users(db):
    buyer = db.scalars(select(User).where(User.role == UserRole.BUYER.value)).first()
    suppliers = list(db.scalars(select(User).where(User.role == UserRole.SUPPLIER.value).order_by(User.company_name)))
    return buyer, suppliers[0], suppliers[1]


def auction_payload(reference_id="RFQ-API-1", supplier_ids=None) -> AuctionCreate:
    return AuctionCreate(
        name="API Test Auction",
        reference_id=reference_id,
        british_auction_enabled=True,
        start_at="2026-01-01T09:00:00Z",
        close_at="2026-01-01T10:00:00Z",
        forced_close_at="2026-01-01T10:30:00Z",
        pickup_at="2026-01-02T09:00:00Z",
        config=AuctionConfigIn(
            trigger_window_minutes=10,
            extension_minutes=5,
            trigger_type=TriggerType.BID_RECEIVED,
        ),
        supplier_ids=supplier_ids or [],
    )


def freeze_now(monkeypatch, value: str):
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    monkeypatch.setattr(rfq_routes, "_now", lambda: instant)


def bid_payload(carrier=None, freight="1000.00") -> BidCreate:
    return BidCreate(
        carrier_name=carrier,
        freight_charges=Decimal(freight),
        origin_charges=Decimal("100.00"),
        destination_charges=Decimal("100.00"),
        transit_time="2 days",
        validity="7 days",
    )


def create_auction(db, buyer, supplier_ids=None, reference_id="RFQ-API-1"):
    return rfq_routes.create_auction(auction_payload(reference_id, supplier_ids), db=db, current_user=buyer)


def expect_http_error(status_code, func):
    try:
        func()
    except HTTPException as error:
        assert error.status_code == status_code
        return error
    raise AssertionError(f"Expected HTTPException {status_code}")


def test_health():
    assert health() == {"status": "ok"}


def test_login_returns_signed_token_and_current_user_can_be_loaded():
    db = make_db()
    login = auth_routes.login(LoginRequest(email="buyer@gocomet.test", password="password123"), db=db)

    payload = decode_access_token(login["access_token"])

    assert login["token_type"] == "bearer"
    assert login["user"].email == "buyer@gocomet.test"
    assert payload["sub"] == login["user"].id


def test_login_rejects_bad_password():
    db = make_db()

    error = expect_http_error(
        401,
        lambda: auth_routes.login(LoginRequest(email="buyer@gocomet.test", password="wrong-password"), db=db),
    )

    assert error.detail == "Invalid email or password."


def test_create_and_list_auction_with_pagination():
    db = make_db()
    buyer, supplier, _ = users(db)
    created = create_auction(db, buyer, [supplier.id])

    listed = rfq_routes.list_auctions(limit=10, offset=0, db=db, current_user=buyer)

    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]
    assert listed["items"][0]["reference_id"] == "RFQ-API-1"


def test_supplier_sees_only_invited_auctions():
    db = make_db()
    buyer, invited_supplier, other_supplier = users(db)
    create_auction(db, buyer, [invited_supplier.id])

    invited_page = rfq_routes.list_auctions(db=db, current_user=invited_supplier)
    other_page = rfq_routes.list_auctions(db=db, current_user=other_supplier)

    assert invited_page["total"] == 1
    assert other_page["total"] == 0


def test_supplier_cannot_create_auction():
    db = make_db()
    _, supplier, _ = users(db)

    error = expect_http_error(
        403,
        lambda: rfq_routes.create_auction(auction_payload(), db=db, current_user=supplier),
    )

    assert error.detail == "This action is not allowed for your role."


def test_duplicate_reference_is_rejected():
    db = make_db()
    buyer, supplier, _ = users(db)
    create_auction(db, buyer, [supplier.id])

    error = expect_http_error(
        409,
        lambda: rfq_routes.create_auction(auction_payload("rfq-api-1", [supplier.id]), db=db, current_user=buyer),
    )

    assert error.detail == ["Reference ID must be unique."]


def test_submit_bid_extends_auction_and_logs_activity(monkeypatch):
    db = make_db()
    buyer, supplier, _ = users(db)
    freeze_now(monkeypatch, "2026-01-01T09:55:00Z")
    created = create_auction(db, buyer, [supplier.id])
    body = rfq_routes.submit_bid(created["id"], bid_payload(), db=db, current_user=supplier)

    assert body["current_lowest_bid"] == Decimal("1200.00")
    assert body["close_at"].isoformat() == "2026-01-01T10:05:00+00:00"
    assert body["rankings"][0]["rank"] == "L1"
    assert {entry["type"] for entry in body["activity_log"]} == {"created", "bid", "extension"}


def test_supplier_cannot_bid_on_uninvited_auction(monkeypatch):
    db = make_db()
    buyer, invited_supplier, other_supplier = users(db)
    freeze_now(monkeypatch, "2026-01-01T09:55:00Z")
    created = create_auction(db, buyer, [invited_supplier.id])

    error = expect_http_error(
        403,
        lambda: rfq_routes.submit_bid(created["id"], bid_payload(), db=db, current_user=other_supplier),
    )

    assert error.detail == "You do not have access to this RFQ."


def test_supplier_cannot_spoof_another_carrier_name(monkeypatch):
    db = make_db()
    buyer, supplier, _ = users(db)
    freeze_now(monkeypatch, "2026-01-01T09:55:00Z")
    created = create_auction(db, buyer, [supplier.id])

    error = expect_http_error(
        403,
        lambda: rfq_routes.submit_bid(created["id"], bid_payload(carrier="Different Carrier"), db=db, current_user=supplier),
    )

    assert error.detail == "Suppliers can only submit quotes as their assigned company."


def test_client_cannot_supply_bid_timestamp():
    with pytest.raises(ValidationError):
        BidCreate(
            freight_charges=Decimal("1000.00"),
            origin_charges=Decimal("100.00"),
            destination_charges=Decimal("100.00"),
            transit_time="2 days",
            validity="7 days",
            submitted_at="2026-01-01T09:55:00Z",
        )


def test_supplier_detail_masks_competitor_bid_breakdown(monkeypatch):
    db = make_db()
    buyer, apex_supplier, swift_supplier = users(db)
    freeze_now(monkeypatch, "2026-01-01T09:55:00Z")
    created = create_auction(db, buyer, [apex_supplier.id, swift_supplier.id])
    rfq_routes.submit_bid(created["id"], bid_payload(freight="800.00"), db=db, current_user=apex_supplier)
    freeze_now(monkeypatch, "2026-01-01T09:56:00Z")
    rfq_routes.submit_bid(
        created["id"],
        bid_payload(freight="700.00"),
        db=db,
        current_user=swift_supplier,
    )

    detail = rfq_routes.get_auction(created["id"], db=db, current_user=apex_supplier)
    hidden_rows = [rank for rank in detail["rankings"] if rank["carrier_name"].startswith("Supplier L")]

    assert len(detail["bids"]) == 1
    assert detail["bids"][0]["carrier_name"] == apex_supplier.company_name
    assert hidden_rows
    assert hidden_rows[0]["freight_charges"] == Decimal("0.00")
    assert hidden_rows[0]["transit_time"] == "Hidden"


def test_decimal_money_avoids_float_rounding_failure(monkeypatch):
    db = make_db()
    buyer, supplier, _ = users(db)
    freeze_now(monkeypatch, "2026-01-01T09:55:00Z")
    created = create_auction(db, buyer, [supplier.id])

    body = rfq_routes.submit_bid(
        created["id"],
        bid_payload(freight="0.10"),
        db=db,
        current_user=supplier,
    )

    assert body["current_lowest_bid"] == Decimal("200.10")


def test_rejects_non_lowering_supplier_rebid(monkeypatch):
    db = make_db()
    buyer, supplier, _ = users(db)
    freeze_now(monkeypatch, "2026-01-01T09:55:00Z")
    created = create_auction(db, buyer, [supplier.id])
    rfq_routes.submit_bid(created["id"], bid_payload(freight="800.00"), db=db, current_user=supplier)
    freeze_now(monkeypatch, "2026-01-01T09:56:00Z")

    error = expect_http_error(
        400,
        lambda: rfq_routes.submit_bid(
            created["id"],
            bid_payload(freight="1200.00"),
            db=db,
            current_user=supplier,
        ),
    )

    assert error.detail == ["Supplier quote must be lower than their current quote of 1000.00."]


def test_rejects_bid_after_close(monkeypatch):
    db = make_db()
    buyer, supplier, _ = users(db)
    freeze_now(monkeypatch, "2026-01-01T10:01:00Z")
    created = create_auction(db, buyer, [supplier.id])

    error = expect_http_error(
        400,
        lambda: rfq_routes.submit_bid(
            created["id"],
            bid_payload(),
            db=db,
            current_user=supplier,
        ),
    )

    assert error.detail == ["Auction is closed and cannot accept bids."]
