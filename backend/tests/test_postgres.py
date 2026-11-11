"""Run only against an explicitly supplied disposable *_test database."""
import os
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, func, inspect, text, MetaData, Table
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError
from alembic.config import Config
from alembic import command
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from fastapi import HTTPException
from app.core.config import settings
from app.models import Base, User, RFQAuction, ActivityLog
from app.api import rfqs
from app.schemas import AuctionCreate, BidCreate
from app.security import seed_demo_users
from app.services.audit import verify_activity_log_chain
from app.services.auction_closure import close_expired_auctions

pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL to a disposable PostgreSQL database")

@pytest.fixture(scope="module")
def pg():
    url = os.environ["TEST_DATABASE_URL"]
    assert make_url(url).database.endswith("_test"), "Refusing a database not named *_test"
    engine = create_engine(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "database_url", url)
        # Exercise a real legacy upgrade in a clean database, including logs
        # predating hash chaining. Never downgrade or erase an existing schema.
        if not inspect(engine).get_table_names():
            command.upgrade(config, "20261110_0002")
            with engine.begin() as con:
                meta = MetaData()
                users = Table("users", meta, autoload_with=con)
                auctions = Table("rfq_auctions", meta, autoload_with=con)
                logs = Table("activity_logs", meta, autoload_with=con)
                now = datetime.now(timezone.utc)
                con.execute(users.insert().values(id="legacy-buyer", email="legacy@example.test", name="Legacy", company_name="Legacy", role="buyer", password_hash="unused", password_salt="unused", is_active=False, created_at=now))
                con.execute(auctions.insert().values(id="legacy-auction", name="Legacy", reference_id="LEGACY-MIGRATION", british_auction_enabled=True, created_by_user_id="legacy-buyer", start_at=now-timedelta(hours=1), original_close_at=now, close_at=now, forced_close_at=now+timedelta(hours=1), pickup_at=now+timedelta(days=1), trigger_window_minutes=10, extension_minutes=5, trigger_type="bid-received", created_at=now))
                con.execute(logs.insert().values(id="legacy-log", auction_id="legacy-auction", type="created", message="Legacy event", at=now))
        command.upgrade(config, "head")
    Session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with Session() as db:
        seed_demo_users(db)
        users = {u.email: u for u in db.scalars(select(User))}
    yield engine, Session, users
    engine.dispose()

def create(pg):
    _, Session, users = pg
    now = datetime.now(timezone.utc)
    p = AuctionCreate(name="Concurrency test", reference_id=str(uuid4()), start_at=now-timedelta(minutes=5), close_at=now+timedelta(minutes=5), forced_close_at=now+timedelta(minutes=30), pickup_at=now+timedelta(days=1), supplier_ids=[users['apex@carrier.test'].id,users['swift@carrier.test'].id], config={'trigger_window_minutes':60,'extension_minutes':5,'trigger_type':'bid-received'})
    with Session() as db:
        return rfqs.create_auction(p, db=db, current_user=users['buyer@gocomet.test'])

def submit(pg, auction, user, price, barrier):
    with pg[1]() as db:
        barrier.wait(timeout=10)
        try:
            rfqs.submit_bid(auction['id'], BidCreate(freight_charges=str(price),origin_charges='0',destination_charges='0',transit_time='1 day',validity='7 days'), db=db,current_user=user)
            return 201
        except HTTPException as e:
            return e.status_code

def test_migration_matches_models_and_backfills_legacy_logs(pg):
    engine, Session, _ = pg
    with engine.connect() as con:
        assert compare_metadata(MigrationContext.configure(con), Base.metadata) == []
    with Session() as db:
        logs=list(db.scalars(select(ActivityLog).where(ActivityLog.auction_id=='legacy-auction').order_by(ActivityLog.sequence_number)))
        assert logs and verify_activity_log_chain(logs)
        with pytest.raises(DBAPIError,match='append-only'):
            db.execute(text("UPDATE activity_logs SET message='tampered' WHERE id='legacy-log'"))
        db.rollback()
        with pytest.raises(DBAPIError,match='append-only'):
            db.execute(text("TRUNCATE activity_logs"))

def test_concurrent_identical_rebids_accept_once(pg):
    a=create(pg); barrier=Barrier(8)
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes=list(pool.map(lambda _:submit(pg,a,pg[2]['apex@carrier.test'],100,barrier),range(8)))
    assert codes.count(201)==1 and codes.count(400)==7

def test_concurrent_suppliers_preserve_extensions_and_audit(pg):
    a=create(pg); barrier=Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(submit,pg,a,pg[2][email],100+i,barrier) for i,email in enumerate(['apex@carrier.test','swift@carrier.test'])]
        assert [f.result(timeout=20) for f in futures]==[201,201]
    with pg[1]() as db:
        row=db.get(RFQAuction,a['id'])
        assert (row.close_at-row.original_close_at).total_seconds()==600
        logs=list(db.scalars(select(ActivityLog).where(ActivityLog.auction_id==a['id']).order_by(ActivityLog.sequence_number)))
        assert verify_activity_log_chain(logs)

def test_competing_close_workers_create_one_event(pg):
    a=create(pg); barrier=Barrier(2)
    def close():
        with pg[1]() as db:
            barrier.wait(timeout=10)
            return close_expired_auctions(db, now=a['close_at']+timedelta(seconds=1))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(close) for _ in range(2)]
        for f in futures: f.result(timeout=20)
    with pg[1]() as db:
        assert db.scalar(select(func.count()).select_from(ActivityLog).where(ActivityLog.auction_id==a['id'],ActivityLog.type=='closed'))==1
