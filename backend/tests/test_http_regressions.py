import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update, delete
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.main import app
from app.db import get_db
from app.core.config import settings
from app.models import Base, User, RFQAuction, ActivityLog
from app.security import seed_demo_users, create_access_token, hash_password
from app.services.auction_closure import close_expired_auctions
from app.services.audit import verify_activity_log_chain

@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr(settings, 'seed_demo_users', True)
    monkeypatch.setattr(settings, 'rate_limit_redis_url', '')
    monkeypatch.setattr(settings, 'trusted_proxy_cidrs', [])
    monkeypatch.setattr(settings, 'api_rate_limit_per_minute', 0)
    monkeypatch.setattr(settings, 'auth_rate_limit_per_minute', 0)
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with Session() as db:
        seed_demo_users(db)
        users = {u.email: u for u in db.scalars(select(User))}
    def dep():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = dep
    app.middleware_stack = None
    client = TestClient(app, raise_server_exceptions=False)
    yield client, Session, users
    client.close()
    app.dependency_overrides.clear()
    app.middleware_stack = None
    engine.dispose()

def headers(user):
    return {'Authorization': 'Bearer ' + create_access_token(user)}

def create(ctx, suppliers=None):
    client, Session, users = ctx
    now = datetime.now(timezone.utc)
    payload = {'name': 'Review only', 'reference_id': 'LOCAL-REVIEW',
        'start_at': (now-timedelta(minutes=10)).isoformat(),
        'close_at': (now+timedelta(minutes=5)).isoformat(),
        'forced_close_at': (now+timedelta(minutes=30)).isoformat(),
        'pickup_at': (now+timedelta(days=1)).isoformat(),
        'config': {'trigger_window_minutes':10, 'extension_minutes':5, 'trigger_type':'bid-received'},
        'supplier_ids': suppliers or [users['apex@carrier.test'].id, users['swift@carrier.test'].id]}
    r = client.post('/api/rfqs', json=payload, headers=headers(users['buyer@gocomet.test']))
    assert r.status_code == 201, r.text
    return r.json()

def bid(client, auction, user, price='1000.00'):
    return client.post('/api/rfqs/'+auction['id']+'/bids', headers=headers(user), json={
        'freight_charges':price, 'origin_charges':'25.00', 'destination_charges':'50.00',
        'transit_time':'2 days', 'validity':'7 days'})

def test_http_unauthenticated_and_invalid_tokens(ctx):
    client, _, _ = ctx
    assert client.get('/api/rfqs').status_code == 401
    for token in ['bad', 'abc.def', 'abc.!', 'a.b.c']:
        assert client.get('/api/rfqs', headers={'Authorization':'Bearer '+token}).status_code == 401

def test_http_uninvited_supplier_and_foreign_buyer(ctx):
    client, Session, users = ctx
    auction = create(ctx, [users['apex@carrier.test'].id])
    assert client.get('/api/rfqs/'+auction['id'], headers=headers(users['swift@carrier.test'])).status_code == 403
    assert bid(client, auction, users['swift@carrier.test']).status_code == 403
    with Session() as db:
        ph, ps = hash_password('local-review-only')
        u = User(email='otherbuyer@example.test',name='Other',company_name='Other buyer',role='buyer',password_hash=ph,password_salt=ps)
        db.add(u); db.commit()
        assert client.get('/api/rfqs/'+auction['id'],headers=headers(u)).status_code == 403

def test_http_money_and_server_timestamp_validation(ctx):
    client, _, users = ctx
    auction = create(ctx)
    for price in ['-1','NaN','Infinity','1.001','10000000000.00']:
        assert bid(client,auction,users['apex@carrier.test'],price).status_code == 422
    payload={'freight_charges':'1','origin_charges':'0','destination_charges':'0','transit_time':'2 days','validity':'7 days','submitted_at':'2020-01-01T00:00:00Z'}
    assert client.post('/api/rfqs/'+auction['id']+'/bids',headers=headers(users['apex@carrier.test']),json=payload).status_code == 422

def test_forged_forwarded_ip_should_not_bypass_login_limit(ctx, monkeypatch):
    client, _, _ = ctx
    monkeypatch.setattr(settings,'auth_rate_limit_per_minute',2)
    codes=[client.post('/api/auth/login',json={'email':'none@example.test','password':'wrong'}, headers={'X-Forwarded-For':f'192.0.2.{i}'}).status_code for i in range(1,4)]
    assert codes == [401,401,429], codes

def test_rate_limit_errors_have_cors_headers(ctx, monkeypatch):
    client, _, _ = ctx
    monkeypatch.setattr(settings,'auth_rate_limit_per_minute',1)
    h={'Origin':'http://localhost:5173'}
    client.post('/api/auth/login',json={'email':'none@example.test','password':'wrong'},headers=h)
    r=client.post('/api/auth/login',json={'email':'none@example.test','password':'wrong'},headers=h)
    assert r.status_code == 429
    assert r.headers.get('access-control-allow-origin') == h['Origin'], dict(r.headers)

def test_content_length_body_limit(ctx, monkeypatch):
    client, _, _ = ctx
    monkeypatch.setattr(settings,'api_max_body_bytes',30)
    assert client.post('/api/auth/login',content=b'x'*31).status_code == 413

def test_streamed_body_limit_returns_413(ctx, monkeypatch):
    client, _, _ = ctx
    monkeypatch.setattr(settings,'api_max_body_bytes',30)
    r=client.post('/api/auth/login',content=iter([b'x'*20,b'x'*20]),headers={'Content-Type':'application/json'})
    assert r.status_code == 413, (r.status_code,r.text)

def test_delayed_closer_keeps_scheduled_close_reason(ctx):
    _, Session, _ = ctx
    created=create(ctx)
    with Session() as db:
        a=db.get(RFQAuction,created['id'])
        later=a.forced_close_at.replace(tzinfo=timezone.utc)+timedelta(hours=1)
        expected=a.close_at
        assert close_expired_auctions(db,now=later)==1
        assert (a.close_reason,a.closed_at.replace(tzinfo=None)) == ('scheduled-close',expected.replace(tzinfo=None)), (a.close_reason,a.closed_at,expected)

def same_name_supplier(ctx):
    _, Session, users=ctx
    with Session() as db:
        u=db.get(User,users['swift@carrier.test'].id)
        u.company_name=users['apex@carrier.test'].company_name
        db.commit()
        users['swift@carrier.test']=u

def test_same_company_name_does_not_disclose_competitor_charges(ctx):
    client, _, users=ctx
    same_name_supplier(ctx)
    a=create(ctx)
    assert bid(client,a,users['apex@carrier.test']).status_code==201
    r=client.get('/api/rfqs/'+a['id'],headers=headers(users['swift@carrier.test']))
    assert r.status_code==200
    assert r.json()['bids']==[]
    assert r.json()['rankings'][0]['transit_time']=='Hidden',r.json()['rankings']

def test_same_company_name_suppliers_have_separate_rankings(ctx):
    client, _, users=ctx
    same_name_supplier(ctx)
    a=create(ctx)
    assert bid(client,a,users['apex@carrier.test']).status_code==201
    assert bid(client,a,users['swift@carrier.test'],'900').status_code==201
    r=client.get('/api/rfqs/'+a['id'],headers=headers(users['buyer@gocomet.test']))
    assert len(r.json()['rankings'])==2,r.json()['rankings']

def test_audit_bulk_update_is_blocked(ctx):
    _,Session,_=ctx
    a=create(ctx)
    with Session() as db:
        with pytest.raises(DBAPIError, match='append-only'):
            db.execute(update(ActivityLog).where(ActivityLog.auction_id==a['id']).values(message='changed by bulk update'))
            db.commit()

def test_audit_tail_deletion_is_detected(ctx):
    client,Session,users=ctx
    a=create(ctx)
    assert bid(client,a,users['apex@carrier.test']).status_code==201
    with Session() as db:
        logs=list(db.scalars(select(ActivityLog).where(ActivityLog.auction_id==a['id']).order_by(ActivityLog.sequence_number)))
        assert verify_activity_log_chain(logs)
        with pytest.raises(DBAPIError, match='append-only'):
            db.execute(delete(ActivityLog).where(ActivityLog.id==logs[-1].id)); db.commit()
        db.rollback()
        remaining=list(db.scalars(select(ActivityLog).where(ActivityLog.auction_id==a['id']).order_by(ActivityLog.sequence_number)))
        assert verify_activity_log_chain(remaining)
        assert len(remaining) == len(logs)

def test_operator_can_deactivate_existing_demo_users(ctx,monkeypatch):
    _,Session,_=ctx
    from app import manage_users
    monkeypatch.setattr(manage_users, 'SessionLocal', Session)
    monkeypatch.setattr(sys, 'argv', ['manage_users', 'deactivate-demo'])
    manage_users.main()
    with Session() as db:
        assert not db.scalar(select(User.is_active).where(User.email=='buyer@gocomet.test'))

def test_normal_supplier_masking_and_audit_chain(ctx):
    client,Session,users=ctx
    a=create(ctx)
    assert bid(client,a,users['apex@carrier.test']).status_code==201
    data=client.get('/api/rfqs/'+a['id'],headers=headers(users['swift@carrier.test'])).json()
    assert data['rankings'][0]['transit_time']=='Hidden'
    assert data['bids']==[]
    assert all(log['type']!='bid' for log in data['activity_log'])
    with Session() as db:
        logs=db.scalars(select(ActivityLog).where(ActivityLog.auction_id==a['id']).order_by(ActivityLog.sequence_number))
        assert verify_activity_log_chain(logs)


def test_logout_revokes_only_the_current_token(ctx):
    client, _, users = ctx
    first = headers(users['buyer@gocomet.test'])
    other = headers(users['buyer@gocomet.test'])
    assert client.get('/api/auth/me', headers=first).status_code == 200
    assert client.post('/api/auth/logout', headers=first).status_code == 204
    assert client.get('/api/auth/me', headers=first).status_code == 401
    assert client.get('/api/auth/me', headers=other).status_code == 200


def test_legacy_password_is_upgraded_without_password_change(ctx):
    import hashlib
    client, Session, users = ctx
    with Session() as db:
        u = db.get(User, users['buyer@gocomet.test'].id)
        u.password_salt = 'legacy-test-salt'
        u.password_hash = hashlib.pbkdf2_hmac('sha256', b'legacy-test-password', u.password_salt.encode(), 120000).hex()
        db.commit()
    r = client.post('/api/auth/login', json={'email':'buyer@gocomet.test','password':'legacy-test-password'})
    assert r.status_code == 200
    with Session() as db:
        u = db.get(User, users['buyer@gocomet.test'].id)
        assert u.password_hash.startswith('pbkdf2_sha256$600000$')
        u.token_version += 1
        db.commit()
    assert client.get('/api/auth/me', headers={'Authorization':'Bearer '+r.json()['access_token']}).status_code == 401


def test_bid_history_is_paginated_and_scoped(ctx):
    client, _, users = ctx
    a = create(ctx)
    for price in range(100, 73, -1):
        assert bid(client, a, users['apex@carrier.test'], str(price)).status_code == 201
    base = '/api/rfqs/' + a['id']
    data = client.get(base, headers=headers(users['buyer@gocomet.test'])).json()
    assert data['bids_total'] == 27 and len(data['bids']) == 25
    assert len(data['rankings']) == 1
    second = client.get(base+'?bids_offset=25', headers=headers(users['buyer@gocomet.test'])).json()
    assert len(second['bids']) == 2
    assert not set(b['id'] for b in data['bids']) & set(b['id'] for b in second['bids'])
    other = client.get(base, headers=headers(users['swift@carrier.test'])).json()
    assert other['bids_total'] == 0 and other['bids'] == []
    assert client.get(base+'?history_limit=101', headers=headers(users['buyer@gocomet.test'])).status_code == 422


def test_job_heartbeat_detects_missing_and_stale_worker(ctx):
    from app.models import JobHeartbeat
    client, Session, users = ctx
    h = headers(users['buyer@gocomet.test'])
    assert client.get('/ready').status_code == 200
    assert client.get('/api/operations/jobs', headers=h).status_code == 503
    with Session() as db:
        db.add(JobHeartbeat(name='auction-close', succeeded_at=datetime.now(timezone.utc), processed_count=0))
        db.commit()
    assert client.get('/api/operations/jobs', headers=h).status_code == 200
    assert client.get('/api/operations/jobs', headers=headers(users['apex@carrier.test'])).status_code == 403
    with Session() as db:
        db.get(JobHeartbeat, 'auction-close').succeeded_at = datetime.now(timezone.utc)-timedelta(hours=1)
        db.commit()
    assert client.get('/api/operations/jobs', headers=h).status_code == 503


def test_proxy_chain_ignores_untrusted_prefix(monkeypatch):
    from app.middleware import RequestControlsMiddleware
    monkeypatch.setattr(settings, 'trusted_proxy_cidrs', ['10.0.0.0/8'])
    middleware = RequestControlsMiddleware(None)
    assert middleware._client_ip({'client':('10.1.2.3',5000),'headers':[(b'x-forwarded-for',b'198.51.100.99, 192.0.2.1')]}) == '192.0.2.1'
    assert middleware._client_ip({'client':('192.0.2.2',5000),'headers':[(b'x-forwarded-for',b'198.51.100.99')]}) == '192.0.2.2'


def test_production_rejects_default_secret(monkeypatch):
    from app.core.config import Settings
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.delenv('SECRET_KEY',raising=False)
    with pytest.raises(ValueError,match='SECRET_KEY'):
        Settings()


def test_full_buyer_supplier_review_flow(ctx):
    client, _, users = ctx
    a = create(ctx)
    assert bid(client,a,users['apex@carrier.test'],'1000').status_code == 201
    assert bid(client,a,users['swift@carrier.test'],'900').status_code == 201
    assert bid(client,a,users['apex@carrier.test'],'800').status_code == 201
    data = client.get('/api/rfqs/'+a['id'],headers=headers(users['buyer@gocomet.test'])).json()
    assert data['bids_total'] == 3 and len(data['rankings']) == 2
    assert [b['total'] for b in data['bids']] == ['875.00','975.00','1075.00']
    assert data['rankings'][0]['carrier_name'] == users['apex@carrier.test'].company_name
    assert datetime.fromisoformat(data['close_at']) > datetime.fromisoformat(a['close_at'])


def test_redis_outage_fails_closed_with_cors(ctx, monkeypatch):
    from unittest.mock import AsyncMock
    from redis.exceptions import ConnectionError
    from app.middleware import RequestControlsMiddleware
    monkeypatch.setattr(RequestControlsMiddleware, '_limit', AsyncMock(side_effect=ConnectionError('test outage')))
    r = ctx[0].get('/api/rfqs',headers={'Origin':'http://localhost:5173'})
    assert r.status_code == 503
    assert r.headers['access-control-allow-origin'] == 'http://localhost:5173'
