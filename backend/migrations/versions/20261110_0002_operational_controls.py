"""operational controls

Revision ID: 20261110_0002
Revises: 20261109_0001
Create Date: 2026-11-10
"""

from alembic import op
import sqlalchemy as sa

revision = "20261110_0002"
down_revision = "20261109_0001"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _has_column("rfq_auctions", "closed_at"):
        op.add_column("rfq_auctions", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    if not _has_column("rfq_auctions", "close_reason"):
        op.add_column("rfq_auctions", sa.Column("close_reason", sa.String(length=40), nullable=True))
    if not _has_index("rfq_auctions", "ix_rfq_auctions_closed_at"):
        op.create_index("ix_rfq_auctions_closed_at", "rfq_auctions", ["closed_at"], unique=False)

    if not _has_column("activity_logs", "sequence_number"):
        op.add_column("activity_logs", sa.Column("sequence_number", sa.Integer(), nullable=True))
    if not _has_column("activity_logs", "previous_entry_hash"):
        op.add_column("activity_logs", sa.Column("previous_entry_hash", sa.String(length=64), nullable=True))
    if not _has_column("activity_logs", "entry_hash"):
        op.add_column("activity_logs", sa.Column("entry_hash", sa.String(length=64), nullable=True))
    if not _has_index("activity_logs", "ix_activity_logs_auction_sequence"):
        op.create_index(
            "ix_activity_logs_auction_sequence",
            "activity_logs",
            ["auction_id", "sequence_number"],
            unique=False,
        )
    if not _has_index("activity_logs", "ix_activity_logs_entry_hash"):
        op.create_index("ix_activity_logs_entry_hash", "activity_logs", ["entry_hash"], unique=False)


def downgrade() -> None:
    if _has_index("activity_logs", "ix_activity_logs_entry_hash"):
        op.drop_index("ix_activity_logs_entry_hash", table_name="activity_logs")
    if _has_index("activity_logs", "ix_activity_logs_auction_sequence"):
        op.drop_index("ix_activity_logs_auction_sequence", table_name="activity_logs")
    if _has_column("activity_logs", "entry_hash"):
        op.drop_column("activity_logs", "entry_hash")
    if _has_column("activity_logs", "previous_entry_hash"):
        op.drop_column("activity_logs", "previous_entry_hash")
    if _has_column("activity_logs", "sequence_number"):
        op.drop_column("activity_logs", "sequence_number")

    if _has_index("rfq_auctions", "ix_rfq_auctions_closed_at"):
        op.drop_index("ix_rfq_auctions_closed_at", table_name="rfq_auctions")
    if _has_column("rfq_auctions", "close_reason"):
        op.drop_column("rfq_auctions", "close_reason")
    if _has_column("rfq_auctions", "closed_at"):
        op.drop_column("rfq_auctions", "closed_at")
