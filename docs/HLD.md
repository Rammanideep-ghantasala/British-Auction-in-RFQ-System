# High-Level Design: British Auction RFQ System

**Status (21 November 2026):** The hosted demo is retired. This design describes the application runnable locally from the [README](../README.md); see [deployment status](deployment-status.md) for the cloud shutdown record.

## Objective

Build a full-stack RFQ system where a buyer can create British Auction-enabled RFQs and invited suppliers can submit competing freight quotes. The system ranks quotes, extends bid close time based on configured triggers, and prevents bids after close or forced close.

## Scope

The implementation covers:

- Buyer login and supplier login
- Buyer-only RFQ creation
- Supplier-only bid submission
- Invited supplier access control
- British Auction configuration with trigger window and extension duration
- Supplier ranking by total quote
- Automatic extension when trigger conditions are met
- Forced close cap enforcement
- Append-only activity logs for RFQ creation, bids, extensions, and close transitions
- Scheduled auction close transitions through Celery Beat and Celery workers
- API rate limiting and request body size enforcement
- CI checks for migrations, backend tests, and frontend builds
- React UI for listing, details, RFQ creation, and bidding
- FastAPI REST backend with PostgreSQL-ready persistence

## Users and Roles

| Role | Permissions |
| --- | --- |
| Buyer | Create RFQs, invite suppliers, view full bid details, view activity logs |
| Supplier | View only invited RFQs, submit bids only for invited RFQs, view own bid details and masked competitor rankings |

## System Components

| Component | Responsibility |
| --- | --- |
| React Frontend | Login, RFQ listing, RFQ creation, auction details, bid submission |
| FastAPI Backend | REST APIs, authentication, authorization, auction validation, bid processing |
| Auction Domain Service | Pure business logic for ranking, extensions, close validation, and rebid rules |
| Audit Service | Appends tamper-evident activity log entries with sequence numbers and hashes |
| Celery Worker + Beat | Periodically closes expired auctions and writes close audit events |
| PostgreSQL Database | Stores users, auctions, invitations, bids, and activity logs |
| Redis | Celery broker/result backend and shared request rate counters |
| GitHub Actions | Runs migration check, backend tests, and frontend production build |
| Railway | Former backend, database and broker hosting; now stopped |
| Vercel | Former frontend hosting; now paused |

## Key Backend Flows

### RFQ Creation

1. Buyer logs in.
2. Buyer creates an RFQ with start time, close time, forced close time, pickup/service date, auction trigger window, extension duration, and invited suppliers.
3. Backend validates auction timing and British Auction configuration.
4. Backend stores RFQ and supplier invitations.
5. Backend writes an activity log entry.

### Bid Submission

1. Supplier logs in.
2. Supplier opens an invited RFQ.
3. Supplier submits quote charges, transit time, and validity.
4. Backend verifies:
   - supplier is invited
   - auction is active
   - supplier cannot spoof another carrier
   - rebid is lower than supplier's previous quote
   - bid timestamp is server-owned
5. Backend ranks quotes by total amount.
6. Backend applies extension logic if the bid is inside the configured trigger window.
7. Backend caps extension at forced close time.
8. Backend stores bid and activity logs.

### Scheduled Close Transition

1. Celery Beat triggers the close-expired-auctions task every configured interval.
2. Worker selects auctions with `close_at <= now` that have not already been marked closed.
3. Worker records `closed_at` and `close_reason`.
4. Worker appends a `closed` audit event.
5. Re-running the job is idempotent; already closed auctions are skipped.

## Auction Rules

- Quote total = freight charges + origin charges + destination charges.
- Lowest total quote is ranked L1.
- Each supplier's latest quote is used for current ranking.
- Supplier rebids must be lower than their current quote.
- Bid close can be extended only when:
  - bid is received inside the last X minutes, and
  - selected trigger condition matches.
- Extension never exceeds forced close time.
- Bids are rejected when auction is scheduled, closed, or force closed.

## Security Design

- Signed bearer token authentication.
- Passwords hashed with PBKDF2 and per-user salt.
- Buyer/supplier role-based access control.
- Supplier access restricted to invited RFQs.
- Supplier carrier name is derived from authenticated user, not trusted from client.
- Client cannot submit bid timestamp.
- Supplier users see masked competitor bid breakdowns.
- SQLAlchemy ORM is used for database queries.
- CORS is restricted to explicitly configured frontend origins.
- Security headers are set by the backend.
- API middleware enforces per-client request throttling and body size limits.
- Activity logs have ORM and database mutation guards, unique sequences and SHA-256 hash chains; database administrators can disable enforcement.

## Former Hosting Topology

All hosted compute is offline. The following is historical context; the local Compose topology uses separate API, worker and Beat services.

| Layer | Platform |
| --- | --- |
| Frontend | Vercel |
| Backend | Railway |
| Database | Railway PostgreSQL |
| Worker/Beat | Supervised inside the single Railway demo backend container; separate services recommended for production |
| Broker | Redis |

Former frontend (paused):

```text
https://frontend-one-jade-ojg8dffinq.vercel.app
```

Former backend (stopped):

```text
https://british-auction-rfq-system-production.up.railway.app
```

## Testing

Backend tests cover:

- auction lifecycle statuses
- extension triggers
- forced close cap
- ranking behavior
- authentication
- role-based access control
- invited supplier restrictions
- carrier spoofing prevention
- client timestamp rejection
- Decimal money precision
- duplicate RFQ reference handling
- late bid rejection
- non-lowering rebid rejection
- append-only audit log protection
- scheduled close transition idempotency
- API rate-limit and body-size guards

Current verified result:

```text
Run the backend and frontend suites; PostgreSQL and Redis integration cases require their test service URLs (see README).
```

## Reliability update

Supplier identity is the supplier user ID; company names are display values. SQL queries select only the latest quote per supplier for ranking. Bid/activity history has separate pagination (25 default, maximum 100), and the buyer UI displays every bid through those pages.

The browser uses session-generation and request-order guards, RFQ-specific drafts, explicit logout/token revocation, 20-second request timeouts, and 15-second polling while visible. It renders readable validation errors and connection state.

Versioned password hashes support legacy verification and rehashing at login. Production startup rejects unsafe keys/origins. Shared Redis counters enforce IP/account limits; forwarded headers require explicit proxy trust. CORS covers control errors.

Audit history has database mutation triggers, unique sequences and non-null hashes. Legacy logs are backfilled at migration time. This does not protect against a database administrator disabling the triggers or rewriting the entire chain.

`/ready` checks database readiness; `/api/operations/jobs` reports close-job freshness to buyers. The optional supervisor exits when a child service fails so a container restart policy can recover it. CI uses disposable PostgreSQL/Redis and checks schema drift, legacy upgrades, concurrent bids, HTTP regressions, UI races, audits and builds; it does not deploy.
