"""initial schema

Revision ID: 20261109_0001
Revises:
Create Date: 2026-11-09
"""

from alembic import op
import sqlalchemy as sa

revision = "20261109_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("company_name", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("password_salt", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "rfq_auctions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("reference_id", sa.String(length=80), nullable=False),
        sa.Column("british_auction_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_close_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forced_close_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pickup_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_window_minutes", sa.Integer(), nullable=False),
        sa.Column("extension_minutes", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("reference_id", name="uq_rfq_auctions_reference_id"),
    )
    op.create_index("ix_rfq_auctions_created_by_user_id", "rfq_auctions", ["created_by_user_id"], unique=False)
    op.create_index("ix_rfq_auctions_reference_id", "rfq_auctions", ["reference_id"], unique=False)

    op.create_table(
        "auction_invitations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("auction_id", sa.String(length=36), nullable=False),
        sa.Column("supplier_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["auction_id"], ["rfq_auctions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_user_id"], ["users.id"]),
        sa.UniqueConstraint("auction_id", "supplier_user_id", name="uq_auction_supplier_invitation"),
    )
    op.create_index("ix_auction_invitations_auction_id", "auction_invitations", ["auction_id"], unique=False)
    op.create_index("ix_auction_invitations_supplier_user_id", "auction_invitations", ["supplier_user_id"], unique=False)

    op.create_table(
        "bids",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("auction_id", sa.String(length=36), nullable=False),
        sa.Column("supplier_user_id", sa.String(length=36), nullable=False),
        sa.Column("carrier_name", sa.String(length=160), nullable=False),
        sa.Column("freight_charges", sa.Numeric(12, 2), nullable=False),
        sa.Column("origin_charges", sa.Numeric(12, 2), nullable=False),
        sa.Column("destination_charges", sa.Numeric(12, 2), nullable=False),
        sa.Column("transit_time", sa.String(length=80), nullable=False),
        sa.Column("validity", sa.String(length=80), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["auction_id"], ["rfq_auctions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_user_id"], ["users.id"]),
    )
    op.create_index("ix_bids_auction_id", "bids", ["auction_id"], unique=False)
    op.create_index("ix_bids_supplier_user_id", "bids", ["supplier_user_id"], unique=False)
    op.create_index("ix_bids_submitted_at", "bids", ["submitted_at"], unique=False)
    op.create_index("ix_bids_auction_supplier_submitted", "bids", ["auction_id", "supplier_user_id", "submitted_at"], unique=False)

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("auction_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["auction_id"], ["rfq_auctions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_activity_logs_actor_user_id", "activity_logs", ["actor_user_id"], unique=False)
    op.create_index("ix_activity_logs_auction_id", "activity_logs", ["auction_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_activity_logs_auction_id", table_name="activity_logs")
    op.drop_index("ix_activity_logs_actor_user_id", table_name="activity_logs")
    op.drop_table("activity_logs")
    op.drop_index("ix_bids_auction_supplier_submitted", table_name="bids")
    op.drop_index("ix_bids_submitted_at", table_name="bids")
    op.drop_index("ix_bids_supplier_user_id", table_name="bids")
    op.drop_index("ix_bids_auction_id", table_name="bids")
    op.drop_table("bids")
    op.drop_index("ix_auction_invitations_supplier_user_id", table_name="auction_invitations")
    op.drop_index("ix_auction_invitations_auction_id", table_name="auction_invitations")
    op.drop_table("auction_invitations")
    op.drop_index("ix_rfq_auctions_reference_id", table_name="rfq_auctions")
    op.drop_index("ix_rfq_auctions_created_by_user_id", table_name="rfq_auctions")
    op.drop_table("rfq_auctions")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
