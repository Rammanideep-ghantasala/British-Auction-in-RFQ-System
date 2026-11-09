from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.auction import (
    BidCandidate,
    TriggerType,
    auction_status,
    current_rankings,
    evaluate_bid,
    validate_imported_bid_history,
)


UTC = timezone.utc


@dataclass
class Auction:
    start_at: datetime
    close_at: datetime
    forced_close_at: datetime
    trigger_window_minutes: int = 10
    extension_minutes: int = 5
    trigger_type: str = TriggerType.BID_RECEIVED.value


@dataclass
class Bid:
    carrier_name: str
    freight_charges: float
    origin_charges: float
    destination_charges: float
    transit_time: str = "2 days"
    validity: str = "7 days"
    submitted_at: datetime = datetime(2026, 1, 1, 9, 55, tzinfo=UTC)


def auction(**overrides):
    values = {
        "start_at": datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
        "close_at": datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        "forced_close_at": datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
    }
    values.update(overrides)
    return Auction(**values)


def bid(**overrides):
    values = {
        "carrier_name": "Apex Roadways",
        "freight_charges": 1000,
        "origin_charges": 100,
        "destination_charges": 100,
    }
    values.update(overrides)
    return Bid(**values)


def test_status_lifecycle():
    rfq = auction()

    assert auction_status(rfq, datetime(2026, 1, 1, 8, 59, tzinfo=UTC)) == "Scheduled"
    assert auction_status(rfq, datetime(2026, 1, 1, 9, 0, tzinfo=UTC)) == "Active"
    assert auction_status(rfq, datetime(2026, 1, 1, 10, 0, tzinfo=UTC)) == "Closed"
    assert auction_status(rfq, datetime(2026, 1, 1, 10, 30, tzinfo=UTC)) == "Force Closed"


def test_rankings_use_total_quote():
    rankings = current_rankings(
        [
            bid(carrier_name="Low Freight", freight_charges=700, origin_charges=400, destination_charges=400),
            bid(carrier_name="Low Total", freight_charges=900, origin_charges=50, destination_charges=50),
        ]
    )

    assert rankings[0].carrier_name == "Low Total"
    assert rankings[0].rank == "L1"


def test_bid_received_extends_inside_trigger_window():
    result = evaluate_bid(auction(), [], bid())

    assert result.errors == []
    assert result.extension
    assert result.extension.applied is True
    assert result.extension.next_close_at == datetime(2026, 1, 1, 10, 5, tzinfo=UTC)


def test_extension_is_capped_by_forced_close():
    rfq = auction(
        close_at=datetime(2026, 1, 1, 10, 26, tzinfo=UTC),
        forced_close_at=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
        extension_minutes=10,
    )
    result = evaluate_bid(rfq, [], bid(submitted_at=datetime(2026, 1, 1, 10, 25, tzinfo=UTC)))

    assert result.extension
    assert result.extension.applied is True
    assert result.extension.next_close_at == datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
    assert result.extension.capped_by_forced_close is True


def test_l1_trigger_requires_lowest_bidder_change():
    rfq = auction(trigger_type=TriggerType.L1_RANK_CHANGE.value)
    existing = [
        bid(carrier_name="Apex Roadways", freight_charges=800, submitted_at=datetime(2026, 1, 1, 9, 10, tzinfo=UTC)),
        bid(carrier_name="Vector Logistics", freight_charges=900, submitted_at=datetime(2026, 1, 1, 9, 12, tzinfo=UTC)),
    ]

    no_change = evaluate_bid(
        rfq,
        existing,
        bid(carrier_name="Vector Logistics", freight_charges=850),
    )
    changed = evaluate_bid(
        rfq,
        existing,
        bid(carrier_name="Northstar Freight", freight_charges=700),
    )

    assert no_change.extension
    assert no_change.extension.applied is False
    assert changed.extension
    assert changed.extension.applied is True


def test_supplier_rebid_must_lower_current_quote():
    result = evaluate_bid(
        auction(),
        [bid(freight_charges=800, origin_charges=100, destination_charges=100)],
        bid(freight_charges=1200, origin_charges=100, destination_charges=100),
    )

    assert result.errors == ["Supplier quote must be lower than their current quote of 1000.00."]


def test_imported_bid_history_rejects_supplier_increase():
    rfq = auction()
    errors = validate_imported_bid_history(
        rfq,
        [
            bid(freight_charges=800, origin_charges=100, destination_charges=100),
            bid(
                freight_charges=1200,
                origin_charges=100,
                destination_charges=100,
                submitted_at=datetime(2026, 1, 1, 9, 56, tzinfo=UTC),
            ),
        ],
    )

    assert any("Supplier quote must be lower" in error for error in errors)
