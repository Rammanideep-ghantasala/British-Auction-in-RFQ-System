from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole
from app.services.auction import TriggerType

Money = Decimal


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    company_name: str
    role: UserRole


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class AuctionConfigIn(BaseModel):
    trigger_window_minutes: int = Field(gt=0, le=1440)
    extension_minutes: int = Field(gt=0, le=1440)
    trigger_type: TriggerType


class AuctionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    reference_id: str = Field(min_length=1, max_length=80)
    british_auction_enabled: bool = True
    start_at: datetime
    close_at: datetime
    forced_close_at: datetime
    pickup_at: datetime
    config: AuctionConfigIn
    supplier_ids: list[str] = Field(default_factory=list, max_length=50)


class BidCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carrier_name: str | None = Field(default=None, min_length=1, max_length=160)
    freight_charges: Money = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    origin_charges: Money = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    destination_charges: Money = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)
    transit_time: str = Field(min_length=1, max_length=80)
    validity: str = Field(min_length=1, max_length=80)


class BidRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    carrier_name: str
    freight_charges: Money
    origin_charges: Money
    destination_charges: Money
    transit_time: str
    validity: str
    submitted_at: datetime
    total: Money


class RankedQuoteRead(BaseModel):
    is_own_quote: bool = False
    carrier_name: str
    freight_charges: Money
    origin_charges: Money
    destination_charges: Money
    transit_time: str
    validity: str
    submitted_at: datetime
    total: Money
    rank_number: int
    rank: str


class ActivityLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    message: str
    at: datetime
    event_metadata: dict | None = None


class AuctionConfigRead(BaseModel):
    trigger_window_minutes: int
    extension_minutes: int
    trigger_type: str


class AuctionSummary(BaseModel):
    id: str
    name: str
    reference_id: str
    current_lowest_bid: Money | None
    close_at: datetime
    forced_close_at: datetime
    status: str


class AuctionPage(BaseModel):
    items: list[AuctionSummary]
    total: int
    limit: int
    offset: int


class AuctionDetail(BaseModel):
    id: str
    name: str
    reference_id: str
    british_auction_enabled: bool
    start_at: datetime
    original_close_at: datetime
    close_at: datetime
    forced_close_at: datetime
    pickup_at: datetime
    status: str
    config: AuctionConfigRead
    current_lowest_bid: Money | None
    invited_supplier_ids: list[str]
    rankings: list[RankedQuoteRead]
    bids: list[BidRead]
    activity_log: list[ActivityLogRead]
    bids_total: int
    activity_total: int
    history_limit: int
    bids_offset: int
    activity_offset: int
