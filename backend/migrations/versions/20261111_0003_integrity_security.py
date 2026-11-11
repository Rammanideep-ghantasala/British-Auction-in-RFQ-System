"""Audit backfill/enforcement, token revocation and job health.

Revision ID: 20261111_0003
Revises: 20261110_0002
"""
import hashlib
import json
from datetime import timezone

from alembic import op
import sqlalchemy as sa

revision = "20261111_0003"
down_revision = "20261110_0002"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("revoked_tokens", sa.Column("token_hash", sa.String(64), primary_key=True),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])
    op.create_table("job_heartbeats", sa.Column("name", sa.String(80), primary_key=True),
                    sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("processed_count", sa.Integer(), nullable=False))

    # Preserve historical content; establish a documented chain at migration
    # time. A backfilled chain cannot certify events predating this migration.
    logs = sa.Table("activity_logs", sa.MetaData(), autoload_with=bind)
    auctions = list(bind.execute(sa.select(logs.c.auction_id).distinct()).scalars())
    for auction_id in auctions:
        previous = None
        rows = bind.execute(sa.select(logs).where(logs.c.auction_id == auction_id).order_by(
            logs.c.at, logs.c.sequence_number.asc().nullslast(), logs.c.id,
        )).mappings()
        for sequence, row in enumerate(list(rows), 1):
            at = row["at"]
            at = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)
            payload = {"actor_user_id": row["actor_user_id"], "at": at.isoformat(), "auction_id": auction_id,
                       "event_metadata": row["event_metadata"] or {}, "message": row["message"],
                       "previous_entry_hash": previous, "sequence_number": sequence, "type": row["type"]}
            digest = hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
            bind.execute(logs.update().where(logs.c.id == row["id"]).values(
                sequence_number=sequence, previous_entry_hash=previous, entry_hash=digest))
            previous = digest
    with op.batch_alter_table("activity_logs") as batch:
        batch.alter_column("sequence_number", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("entry_hash", existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint("uq_activity_auction_sequence", ["auction_id", "sequence_number"])
    # Freeze enforcement DDL in this migration rather than importing live models.
    if bind.dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Activity logs are append-only'; END; $$""")
        op.execute("CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON activity_logs FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_mutation()")
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER audit_no_{action.lower()} BEFORE {action} ON activity_logs BEGIN SELECT RAISE(ABORT, 'Activity logs are append-only'); END")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER audit_no_mutation ON activity_logs")
        op.execute("DROP FUNCTION reject_audit_mutation()")
    else:
        op.execute("DROP TRIGGER audit_no_update")
        op.execute("DROP TRIGGER audit_no_delete")
    with op.batch_alter_table("activity_logs") as batch:
        batch.drop_constraint("uq_activity_auction_sequence", type_="unique")
        batch.alter_column("sequence_number", existing_type=sa.Integer(), nullable=True)
        batch.alter_column("entry_hash", existing_type=sa.String(64), nullable=True)
    op.drop_table("job_heartbeats")
    op.drop_table("revoked_tokens")
    op.drop_column("users", "token_version")
