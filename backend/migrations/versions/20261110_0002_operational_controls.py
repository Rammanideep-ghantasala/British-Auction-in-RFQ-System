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


def upgrade() -> None:
    op.add_column("rfq_auctions", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rfq_auctions", sa.Column("close_reason", sa.String(length=40), nullable=True))
    op.create_index("ix_rfq_auctions_closed_at", "rfq_auctions", ["closed_at"], unique=False)

    op.add_column("activity_logs", sa.Column("sequence_number", sa.Integer(), nullable=True))
    op.add_column("activity_logs", sa.Column("previous_entry_hash", sa.String(length=64), nullable=True))
    op.add_column("activity_logs", sa.Column("entry_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_activity_logs_auction_sequence",
        "activity_logs",
        ["auction_id", "sequence_number"],
        unique=False,
    )
    op.create_index("ix_activity_logs_entry_hash", "activity_logs", ["entry_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_activity_logs_entry_hash", table_name="activity_logs")
    op.drop_index("ix_activity_logs_auction_sequence", table_name="activity_logs")
    op.drop_column("activity_logs", "entry_hash")
    op.drop_column("activity_logs", "previous_entry_hash")
    op.drop_column("activity_logs", "sequence_number")

    op.drop_index("ix_rfq_auctions_closed_at", table_name="rfq_auctions")
    op.drop_column("rfq_auctions", "close_reason")
    op.drop_column("rfq_auctions", "closed_at")
