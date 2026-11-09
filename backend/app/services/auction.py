from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Iterable, Protocol

MONEY_QUANT = Decimal("0.01")
ZERO = Decimal("0.00")


class TriggerType(StrEnum):
    BID_RECEIVED = "bid-received"
    ANY_RANK_CHANGE = "any-rank-change"
    L1_RANK_CHANGE = "l1-rank-change"


class AuctionLike(Protocol):
    start_at: datetime
    close_at: datetime
    forced_close_at: datetime
    trigger_window_minutes: int
    extension_minutes: int
    trigger_type: str


class BidLike(Protocol):
    carrier_name: str
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    transit_time: str
    validity: str
    submitted_at: datetime


@dataclass(frozen=True)
class BidCandidate:
    carrier_name: str
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    transit_time: str
    validity: str
    submitted_at: datetime


@dataclass(frozen=True)
class RankedQuote:
    carrier_name: str
    carrier_key: str
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    transit_time: str
    validity: str
    submitted_at: datetime
    total: Decimal
    rank_number: int

    @property
    def rank(self) -> str:
        return f"L{self.rank_number}"


@dataclass(frozen=True)
class ExtensionDecision:
    applied: bool
    previous_close_at: datetime
    next_close_at: datetime
    reason: str
    capped_by_forced_close: bool = False


@dataclass(frozen=True)
class BidDecision:
    errors: list[str]
    extension: ExtensionDecision | None = None


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def money(value: Decimal | int | float | str) -> Decimal:
    try:
        return Decimal(str(value)).quantize(MONEY_QUANT)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid money amount.") from exc


def normalize_reference(reference_id: str) -> str:
    return reference_id.strip().upper()


def carrier_key(carrier_name: str) -> str:
    return carrier_name.strip().lower()


def quote_total(bid: BidLike) -> Decimal:
    return money(money(bid.freight_charges) + money(bid.origin_charges) + money(bid.destination_charges))


def validate_auction_window(
    *,
    name: str,
    reference_id: str,
    british_auction_enabled: bool,
    start_at: datetime,
    close_at: datetime,
    forced_close_at: datetime,
    pickup_at: datetime,
    trigger_window_minutes: int,
    extension_minutes: int,
    trigger_type: str,
) -> list[str]:
    errors: list[str] = []

    if not name.strip():
        errors.append("RFQ name is required.")
    if not reference_id.strip():
        errors.append("Reference ID is required.")
    if not british_auction_enabled:
        errors.append("British Auction option must be enabled.")
    if as_utc(start_at) >= as_utc(close_at):
        errors.append("Bid close date and time must be later than bid start date and time.")
    if as_utc(forced_close_at) <= as_utc(close_at):
        errors.append("Forced bid close date and time must be later than bid close date and time.")
    if not pickup_at:
        errors.append("Pickup or service date is required.")
    if trigger_window_minutes <= 0:
        errors.append("Trigger window must be greater than zero.")
    if extension_minutes <= 0:
        errors.append("Extension duration must be greater than zero.")
    if trigger_type not in {item.value for item in TriggerType}:
        errors.append("Select an extension trigger.")

    return errors


def validate_bid_payload(bid: BidLike) -> list[str]:
    errors: list[str] = []

    if not bid.carrier_name.strip():
        errors.append("Carrier name is required.")

    for label, amount in (
        ("Freight charges", bid.freight_charges),
        ("Origin charges", bid.origin_charges),
        ("Destination charges", bid.destination_charges),
    ):
        if money(amount) < ZERO:
            errors.append(f"{label} must be zero or greater.")

    if quote_total(bid) <= ZERO:
        errors.append("Quote total must be greater than zero.")
    if not bid.transit_time.strip():
        errors.append("Transit time is required.")
    if not bid.validity.strip():
        errors.append("Quote validity is required.")
    if not bid.submitted_at:
        errors.append("Bid submission date and time is required.")

    return errors


def current_rankings(bids: Iterable[BidLike]) -> list[RankedQuote]:
    latest_by_carrier: dict[str, BidLike] = {}

    for bid in bids:
        key = carrier_key(bid.carrier_name)
        existing = latest_by_carrier.get(key)
        if existing is None or as_utc(bid.submitted_at) >= as_utc(existing.submitted_at):
            latest_by_carrier[key] = bid

    ranked = sorted(
        latest_by_carrier.values(),
        key=lambda bid: (quote_total(bid), as_utc(bid.submitted_at), bid.carrier_name.casefold()),
    )

    return [
        RankedQuote(
            carrier_name=bid.carrier_name,
            carrier_key=carrier_key(bid.carrier_name),
            freight_charges=money(bid.freight_charges),
            origin_charges=money(bid.origin_charges),
            destination_charges=money(bid.destination_charges),
            transit_time=bid.transit_time,
            validity=bid.validity,
            submitted_at=as_utc(bid.submitted_at),
            total=quote_total(bid),
            rank_number=index + 1,
        )
        for index, bid in enumerate(ranked)
    ]


def auction_status(auction: AuctionLike, now: datetime) -> str:
    if getattr(auction, "closed_at", None) is not None:
        return "Force Closed" if getattr(auction, "close_reason", None) == "forced-close" else "Closed"

    current_time = as_utc(now)
    start_at = as_utc(auction.start_at)
    close_at = as_utc(auction.close_at)
    forced_close_at = as_utc(auction.forced_close_at)

    if current_time >= forced_close_at:
        return "Force Closed"
    if current_time >= close_at:
        return "Closed" if close_at < forced_close_at else "Force Closed"
    if current_time < start_at:
        return "Scheduled"
    return "Active"


def validate_imported_bid_history(auction: AuctionLike, bids: list[BidLike]) -> list[str]:
    errors: list[str] = []

    for index, bid in enumerate(bids):
        errors.extend([f"Bid {index + 1}: {error}" for error in validate_bid_payload(bid)])
        submitted_at = as_utc(bid.submitted_at)

        if submitted_at < as_utc(auction.start_at):
            errors.append(f"Bid {index + 1}: Bid submission cannot be before bid start date and time.")
        if submitted_at >= as_utc(auction.close_at):
            errors.append(f"Bid {index + 1}: Bid submission must be before current bid close date and time.")
        if submitted_at >= as_utc(auction.forced_close_at):
            errors.append(f"Bid {index + 1}: Bid submission must be before forced bid close date and time.")

    bids_by_carrier: dict[str, list[tuple[int, BidLike]]] = {}
    for index, bid in enumerate(bids):
        bids_by_carrier.setdefault(carrier_key(bid.carrier_name), []).append((index, bid))

    for carrier_bids in bids_by_carrier.values():
        chronological_bids = sorted(carrier_bids, key=lambda item: (as_utc(item[1].submitted_at), item[0]))
        for item_index in range(1, len(chronological_bids)):
            previous_bid = chronological_bids[item_index - 1][1]
            current_index, current_bid = chronological_bids[item_index]
            if quote_total(current_bid) >= quote_total(previous_bid):
                errors.append(
                    f"Bid {current_index + 1}: Supplier quote must be lower than their previous quote of {quote_total(previous_bid):.2f}."
                )

    return errors


def trigger_label(trigger_type: str) -> str:
    if trigger_type == TriggerType.ANY_RANK_CHANGE:
        return "Any supplier rank change"
    if trigger_type == TriggerType.L1_RANK_CHANGE:
        return "Lowest bidder rank change"
    return "Bid received"


def _rank_map(rankings: list[RankedQuote]) -> dict[str, int]:
    return {quote.carrier_key: quote.rank_number for quote in rankings}


def _any_rank_changed(before: list[RankedQuote], after: list[RankedQuote]) -> bool:
    before_ranks = _rank_map(before)
    after_ranks = _rank_map(after)
    return any(before_ranks.get(key) != after_ranks.get(key) for key in set(before_ranks) | set(after_ranks))


def _l1_changed(before: list[RankedQuote], after: list[RankedQuote]) -> bool:
    if not before or not after:
        return False
    return before[0].carrier_key != after[0].carrier_key


def _trigger_matched(trigger_type: str, before: list[RankedQuote], after: list[RankedQuote]) -> bool:
    if trigger_type == TriggerType.BID_RECEIVED:
        return True
    if trigger_type == TriggerType.ANY_RANK_CHANGE:
        return _any_rank_changed(before, after)
    if trigger_type == TriggerType.L1_RANK_CHANGE:
        return _l1_changed(before, after)
    return False


def evaluate_bid(auction: AuctionLike, existing_bids: list[BidLike], bid: BidCandidate) -> BidDecision:
    errors = validate_bid_payload(bid)
    if errors:
        return BidDecision(errors=errors)

    submitted_at = as_utc(bid.submitted_at)
    status = auction_status(auction, submitted_at)
    if status != "Active":
        return BidDecision(errors=[f"Auction is {status.lower()} and cannot accept bids."])

    before_rankings = current_rankings(existing_bids)
    current_supplier_quote = next(
        (quote for quote in before_rankings if quote.carrier_key == carrier_key(bid.carrier_name)),
        None,
    )

    if current_supplier_quote and quote_total(bid) >= current_supplier_quote.total:
        return BidDecision(
            errors=[
                f"Supplier quote must be lower than their current quote of {current_supplier_quote.total:.2f}."
            ]
        )

    after_rankings = current_rankings([*existing_bids, bid])
    close_at = as_utc(auction.close_at)
    forced_close_at = as_utc(auction.forced_close_at)
    remaining = close_at - submitted_at
    in_trigger_window = timedelta(0) <= remaining <= timedelta(minutes=auction.trigger_window_minutes)
    extension = ExtensionDecision(
        applied=False,
        previous_close_at=close_at,
        next_close_at=close_at,
        reason="",
    )

    if in_trigger_window and _trigger_matched(auction.trigger_type, before_rankings, after_rankings):
        requested_close = close_at + timedelta(minutes=auction.extension_minutes)
        capped_close = min(requested_close, forced_close_at)

        if capped_close > close_at:
            extension = ExtensionDecision(
                applied=True,
                previous_close_at=close_at,
                next_close_at=capped_close,
                reason=(
                    f"{trigger_label(auction.trigger_type)} inside the last "
                    f"{auction.trigger_window_minutes} minutes."
                ),
                capped_by_forced_close=capped_close < requested_close,
            )

    return BidDecision(errors=[], extension=extension)
