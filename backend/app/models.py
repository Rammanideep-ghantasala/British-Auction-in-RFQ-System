from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(StrEnum):
    BUYER = "buyer"
    SUPPLIER = "supplier"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    company_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    created_auctions: Mapped[list["RFQAuction"]] = relationship(back_populates="created_by")
    supplier_bids: Mapped[list["Bid"]] = relationship(back_populates="supplier_user")
    invitations: Mapped[list["AuctionInvitation"]] = relationship(back_populates="supplier_user")
    activity_logs: Mapped[list["ActivityLog"]] = relationship(back_populates="actor_user")


class RFQAuction(Base):
    __tablename__ = "rfq_auctions"
    __table_args__ = (UniqueConstraint("reference_id", name="uq_rfq_auctions_reference_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    british_auction_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forced_close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pickup_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)

    trigger_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    extension_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(40), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    created_by: Mapped[User] = relationship(back_populates="created_auctions")
    bids: Mapped[list["Bid"]] = relationship(
        back_populates="auction",
        cascade="all, delete-orphan",
        order_by="Bid.submitted_at",
    )
    activity_logs: Mapped[list["ActivityLog"]] = relationship(
        back_populates="auction",
        cascade="all, delete-orphan",
        order_by="ActivityLog.at",
    )
    invitations: Mapped[list["AuctionInvitation"]] = relationship(
        back_populates="auction",
        cascade="all, delete-orphan",
    )


class AuctionInvitation(Base):
    __tablename__ = "auction_invitations"
    __table_args__ = (
        UniqueConstraint("auction_id", "supplier_user_id", name="uq_auction_supplier_invitation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    auction_id: Mapped[str] = mapped_column(ForeignKey("rfq_auctions.id", ondelete="CASCADE"), index=True)
    supplier_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    auction: Mapped[RFQAuction] = relationship(back_populates="invitations")
    supplier_user: Mapped[User] = relationship(back_populates="invitations")


class Bid(Base):
    __tablename__ = "bids"
    __table_args__ = (Index("ix_bids_auction_supplier_submitted", "auction_id", "supplier_user_id", "submitted_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    auction_id: Mapped[str] = mapped_column(ForeignKey("rfq_auctions.id", ondelete="CASCADE"), index=True)
    supplier_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    carrier_name: Mapped[str] = mapped_column(String(160), nullable=False)
    freight_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    origin_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    destination_charges: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transit_time: Mapped[str] = mapped_column(String(80), nullable=False)
    validity: Mapped[str] = mapped_column(String(80), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    auction: Mapped[RFQAuction] = relationship(back_populates="bids")
    supplier_user: Mapped[User] = relationship(back_populates="supplier_bids")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    auction_id: Mapped[str] = mapped_column(ForeignKey("rfq_auctions.id", ondelete="CASCADE"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    sequence_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    event_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    auction: Mapped[RFQAuction] = relationship(back_populates="activity_logs")
    actor_user: Mapped[User | None] = relationship(back_populates="activity_logs")


@event.listens_for(ActivityLog, "before_update")
def prevent_activity_log_update(*_) -> None:
    raise ValueError("Activity logs are append-only and cannot be updated.")


@event.listens_for(ActivityLog, "before_delete")
def prevent_activity_log_delete(*_) -> None:
    raise ValueError("Activity logs are append-only and cannot be deleted.")
