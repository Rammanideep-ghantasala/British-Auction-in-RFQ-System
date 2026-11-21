# British Auction RFQ System

[![CI](https://github.com/Rammanideep-ghantasala/British-Auction-in-RFQ-System/actions/workflows/ci.yml/badge.svg)](https://github.com/Rammanideep-ghantasala/British-Auction-in-RFQ-System/actions/workflows/ci.yml)

A full-stack freight procurement application where buyers create requests for quotation (RFQs), invite suppliers, and compare competing quotes. Suppliers lower their bids, rankings update, and qualifying late bids extend the auction without crossing a fixed deadline.

Built as a recruitment assignment using **FastAPI, React, PostgreSQL, Redis, and Celery**. The implementation follows the British Auction rules in the assignment and includes authentication, transactional bidding, scheduled closure, and regression tests.

> **Project status — 21 November 2026:** Maintained as a GitHub portfolio project that runs locally. The former Vercel and Railway demo has been taken offline. No cloud account or API key is needed for the local setup.

[Quick start](#quick-start) · [Features](#features) · [Architecture](#architecture) · [Auction rules](#auction-rules) · [Edge cases](#edge-cases-handled) · [Tests](#testing-and-ci) · [Security](#security-and-access-control)

## Deliverables at a glance

| Deliverable | Where to review |
| --- | --- |
| High-level design | [HLD](docs/HLD.md) |
| Architecture and request sequence | [Architecture diagrams](docs/architecture-diagram.md) |
| Database tables, constraints and ER diagram | [Schema design](docs/database-schema.md) |
| FastAPI backend | [Application](backend/app/) · [Migrations](backend/migrations/) |
| React frontend | [Frontend source](frontend/src/) |
| Regression and integration tests | [Backend tests](backend/tests/) · [Frontend reliability tests](frontend/src/reliability.test.jsx) |
| Previous review and fixes | [Hardening release](docs/hardening-release-2026-11-11.md) |
| Hosting retirement record | [Deployment status](docs/deployment-status.md) |

## Features

| Area | Implemented behavior |
| --- | --- |
| Buyer workspace | Create RFQs, set bidding dates, configure extension rules, invite active suppliers, and review rankings, every submitted bid, and activity history. |
| Supplier workspace | View invited RFQs, submit freight/origin/destination charges, transit time and quote validity, and improve an existing quote. |
| Auction engine | Rank current supplier quotes as L1, L2, L3; support three extension triggers; enforce the forced-close deadline. |
| Access control | Authenticate buyers and suppliers; enforce ownership, roles and invitations on the server; mask competitor identities and charge breakdowns for suppliers. |
| History and integrity | Preserve bid history and sequence/hash-chained activity logs with database mutation guards. Paginate listing, bid and activity views. |
| Background processing | Use Celery Beat and Redis to schedule close scans; persist closure once and expose job freshness. |
| Frontend reliability | Start with empty login fields, autofill demo credentials on request, refresh visible pages every 15 seconds, isolate bid drafts per RFQ, and reject stale responses. |
| Operations | Provide migrations, readiness checks, operator account commands, dependency locks, Docker Compose and GitHub Actions checks. |

## Architecture

The backend is a **modular monolith**: HTTP routes coordinate transactions, domain services evaluate auction rules, and SQLAlchemy handles persistence. Celery reuses the same closure and audit services. This keeps bid acceptance, deadline changes and audit writes inside one database transaction without introducing distributed transactions.

The diagram shows the recommended local Docker Compose setup; the React development server runs separately.

```mermaid
flowchart TB
    Browser["Buyer / supplier browser"] --> UI["React + Vite"]
    UI -->|"REST + signed bearer token"| API["FastAPI routes"]
    API --> Guard["Request limits, authentication and authorization"]
    Guard --> Rules["Auction rules and response visibility"]
    Rules --> Queries["SQLAlchemy queries and transactions"]
    Rules --> Audit["Audit append service"]
    Queries --> DB[("PostgreSQL")]
    Audit --> DB
    Guard -->|"Shared rate counters"| Redis[("Redis")]
    Beat["Celery Beat: one scheduler"] -->|"Enqueue close scan"| Redis
    Redis --> Worker["Celery worker"]
    Worker --> Closure["Closure service"]
    Closure --> DB
    Closure --> Audit
    Worker -->|"Job heartbeat"| DB
```

| Layer | Technology | Why it is used |
| --- | --- | --- |
| Frontend | React 19, Vite, JavaScript | Forms, role-aware views, request cancellation and client state. |
| API and validation | Python 3.12, FastAPI, Pydantic | Typed request/response models and interactive API documentation. |
| Persistence | SQLAlchemy 2, PostgreSQL, Alembic | Decimal money, constraints, row locks and versioned schema changes. |
| Background jobs | Celery, Redis | Periodic closure tasks and shared rate-limit counters. |
| Testing | pytest, HTTP test client, Vitest, Testing Library | Domain, HTTP, database concurrency and browser-state regressions. |
| Delivery checks | GitHub Actions, Docker | Repeatable migrations, tests, dependency audits and builds. |

### What happens when a supplier bids?

1. The API authenticates the supplier and locks the RFQ row using PostgreSQL `SELECT ... FOR UPDATE`.
2. It verifies the invitation and checks the auction deadline using a server-generated submission timestamp.
3. It loads each supplier's latest quote and validates that the new total is lower than this supplier's current total.
4. The auction service computes rankings and decides whether the configured extension applies.
5. The bid, updated deadline and audit entries commit together. Any failed transaction rolls back its writes.
6. The API returns a view filtered for the requesting user.

Concurrent bids for the same RFQ therefore evaluate the deadline in sequence. SQLite is available for lightweight development, but the PostgreSQL tests verify the locking behavior.

### Database model

| Table | Purpose and key constraints |
| --- | --- |
| `users` | Buyer/supplier identity, unique email, salted password hash, active flag and token version. |
| `rfq_auctions` | Buyer ownership, unique normalized reference, schedule, extension configuration and persisted closure. |
| `auction_invitations` | Supplier access; unique auction/supplier pair. |
| `bids` | Supplier account ID, quote components stored as `NUMERIC(12,2)`, and server timestamp. |
| `activity_logs` | Per-auction sequence, previous/current hash, event metadata and actor; unique auction/sequence pair. |
| `revoked_tokens` | SHA-256 digest and expiry of a revoked session token. |
| `job_heartbeats` | Most recent successful close scan and processed count. |

See the [full schema and ER diagram](docs/database-schema.md). Company names are display values; supplier account IDs determine ownership and ranking identity.

## Auction rules

- Quote total is **freight + origin + destination charges**. Components may be zero; the total must be positive.
- Ranking uses the latest accepted quote from each supplier account. Lowest total wins L1; equal totals use submission time, then company name and supplier ID as deterministic tie-breakers.
- A supplier's next quote must be strictly lower than its own current quote.
- Bidding is accepted from the start time, inclusive, until the current close time, exclusive.
- RFQ creation requires `start < close < forced close < pickup/service`.
- A qualifying bid inside the final **X minutes**, including the window boundary, extends the **current** close by **Y minutes**.
- The resulting deadline is `min(current close + Y, forced close)`.

| Extension trigger | When it applies inside the trigger window |
| --- | --- |
| `bid-received` | Any valid new bid. |
| `any-rank-change` | A supplier enters the ranking or any supplier's rank changes. |
| `l1-rank-change` | The leading supplier changes. Establishing the first L1 does not count as replacing a leader. |

**Example:** With close at 10:00, forced close at 10:08, X = 10 minutes and Y = 5 minutes, a qualifying bid at 09:55 moves close to 10:05. Another qualifying bid at 10:04 moves it to 10:08. A bid at 10:08 is rejected.

A delayed worker does not reopen bidding: the API checks the effective deadline during submission. The worker records the deadline's closure reason separately from when processing occurs.

## Quick start

**Prerequisites:** Git, Docker with Compose v2, Node.js 22 and pnpm. Python 3.12 is needed for the optional direct-backend setup and backend tests.

### 1. Clone the repository

```bash
git clone https://github.com/Rammanideep-ghantasala/British-Auction-in-RFQ-System.git
cd British-Auction-in-RFQ-System
```

### 2. Start the API, database and background jobs

```bash
docker compose up --build -d
docker compose ps
```

Compose starts PostgreSQL, Redis, FastAPI, a Celery worker and one Beat scheduler. The API applies migrations before starting; workers wait for API readiness. PostgreSQL and Redis ports bind to localhost.

### 3. Start the frontend in another terminal

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

| Local service | Address |
| --- | --- |
| Application | [localhost:5173](http://localhost:5173) |
| Interactive API docs | [localhost:8000/docs](http://localhost:8000/docs) |
| Database readiness | [localhost:8000/ready](http://localhost:8000/ready) |

### 4. Try the reviewer workflow

All **fresh local demo accounts** use `password123`:

| Role | Email |
| --- | --- |
| Buyer — GoComet | `buyer@gocomet.test` |
| Supplier — Apex Roadways | `apex@carrier.test` |
| Supplier — Swift Freight | `swift@carrier.test` |

1. Select the buyer demo account, then click **Sign In**. The form is empty until you select an account or type.
2. Create an RFQ with a unique reference, a currently active bidding window, later forced-close/pickup times, and both suppliers invited.
3. Sign out and sign in as a supplier. Open the RFQ and submit a quote.
4. Switch supplier accounts to compete, then return to the buyer to inspect rankings, bid history and activity.
5. To see an extension, place a valid bid within X minutes of close under a matching trigger.

Only demo users are seeded; a fresh database starts without auctions. These accounts and passwords are for local evaluation.

### Stop your local stack

```bash
docker compose stop
```

This stops the containers and retains the PostgreSQL volume. Restart with `docker compose start`.

<details>
<summary><strong>Optional: run the backend directly with SQLite</strong></summary>

This route supports API/UI exploration without Docker. Scheduled closure persistence requires a running Redis/Celery setup; use Compose to review the complete system.

From the repository root:

**macOS / Linux**

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.txt
python -m app.migrate
python -m uvicorn app.main:app --reload --no-proxy-headers
```

**Windows PowerShell**

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-dev.txt
python -m app.migrate
python -m uvicorn app.main:app --reload --no-proxy-headers
```

With no environment overrides, the backend uses `backend/dev.db`, local CORS origins and demo users. It reads process environment variables; it does **not** automatically load `backend/.env`. The example file is a reference for exported variables or a container environment file.

</details>

## Edge cases handled

These are implemented behaviors with targeted regression tests. They are not a claim that every possible failure has been eliminated.

| Scenario | Expected behavior | Evidence |
| --- | --- | --- |
| Bid before start, exactly at close, or after forced close | Rejected; start itself is inclusive. | [Boundary tests](backend/tests/test_boundaries.py) |
| Bid exactly X minutes before close | Eligible for extension when its trigger matches. | [Boundary tests](backend/tests/test_boundaries.py) |
| Extension would exceed the forced deadline | Capped at forced close. | [Auction tests](backend/tests/test_auction_service.py) |
| Lower rebid leaves ranks unchanged | No extension under a rank-change trigger. | [Boundary tests](backend/tests/test_boundaries.py) |
| Equal prices, names or timestamps | Deterministic ordering; separate supplier IDs remain separate quotes. | [Boundary tests](backend/tests/test_boundaries.py) |
| Two suppliers share the same company name | No merged ranking, rebid confusion or access to the other account's charge breakdown. | [HTTP regressions](backend/tests/test_http_regressions.py) |
| Identical concurrent bids from one supplier | One accepted; the others fail the lower-rebid rule. | [PostgreSQL concurrency tests](backend/tests/test_postgres.py) |
| Concurrent valid bids from different suppliers | Both accepted extensions are retained; audit chain remains valid. | [PostgreSQL concurrency tests](backend/tests/test_postgres.py) |
| Two workers close the same expired RFQ | One persisted close event. | [PostgreSQL concurrency tests](backend/tests/test_postgres.py) |
| Close task runs after both deadlines | Preserves the effective scheduled/forced close reason. | [HTTP regressions](backend/tests/test_http_regressions.py) |
| Negative, non-finite or over-precision charges | Validation rejects the request. | [HTTP regressions](backend/tests/test_http_regressions.py) |
| Duplicate reference, missing invitations or invalid pickup date | RFQ creation rejected; database uniqueness backs up reference validation. | [API tests](backend/tests/test_api.py) |
| Uninvited supplier or another buyer requests an RFQ | Access denied; supplier lists contain only invited auctions. | [HTTP regressions](backend/tests/test_http_regressions.py) |
| Client forges a carrier name or bid timestamp | Carrier is checked against identity; client-owned timestamps are rejected. | [API tests](backend/tests/test_api.py) |
| Logout while an earlier request is pending | Late response cannot restore the session; the logged-out token is revoked server-side. | [Frontend tests](frontend/src/reliability.test.jsx) · [HTTP tests](backend/tests/test_http_regressions.py) |
| Switch RFQs while typing or awaiting a response | Drafts stay scoped to an RFQ; stale responses cannot replace the selection. | [Frontend tests](frontend/src/reliability.test.jsx) |
| Corrupt saved session or structured validation error | Recover to login or render a readable message. | [Frontend tests](frontend/src/reliability.test.jsx) |
| Quote submission fails | Keep the current RFQ's entered values for correction/retry. | [UI behavior tests](frontend/src/components/ui-behavior.test.jsx) |
| Forged forwarded IP or another API instance | Only configured proxies are trusted; Redis shares limits between instances. | [HTTP tests](backend/tests/test_http_regressions.py) · [Redis tests](backend/tests/test_redis.py) |
| Oversized streamed body, rate limit or Redis outage | Return 413, 429 or fail-closed 503, with CORS-readable errors. | [HTTP regressions](backend/tests/test_http_regressions.py) |
| Bulk audit edit, tail deletion or PostgreSQL truncation | Database guards reject the mutation. | [HTTP tests](backend/tests/test_http_regressions.py) · [PostgreSQL tests](backend/tests/test_postgres.py) |
| Legacy password hash or audit schema | Upgrade password hash on login; migrate legacy logs and check model/schema consistency. | [HTTP tests](backend/tests/test_http_regressions.py) · [Migration tests](backend/tests/test_postgres.py) |
| Missing/stale close-job heartbeat | Buyer operations endpoint returns 503. | [HTTP regressions](backend/tests/test_http_regressions.py) |

## Testing and CI

The [11 November hardening release](docs/hardening-release-2026-11-11.md) recorded **79 backend tests + 13 frontend tests passing**, including PostgreSQL/Redis integration tests. This is a test count, not a coverage percentage. The CI badge above links to the latest run.

With backend development dependencies installed in an activated Python environment, run from the repository root:

```bash
python -m pytest backend/tests
pnpm --dir frontend run test
pnpm --dir frontend run build
```

Without `TEST_DATABASE_URL` and `TEST_REDIS_URL`, five infrastructure integration tests are explicitly skipped.

<details>
<summary><strong>Run the complete suite with disposable PostgreSQL and Redis</strong></summary>

Use a **fresh disposable database** named `rfq_test`. The PostgreSQL fixture exercises a legacy-schema upgrade; never point it at the application database or retained hosted data.

```bash
docker run --rm -d --name rfq-tests-postgres -e POSTGRES_DB=rfq_test -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=test-only -p 127.0.0.1:15432:5432 postgres:17-alpine
docker run --rm -d --name rfq-tests-redis -p 127.0.0.1:16379:6379 redis:7-alpine
docker exec rfq-tests-postgres pg_isready -U postgres -d rfq_test
docker exec rfq-tests-redis redis-cli ping
```

Run the tests once PostgreSQL accepts connections and Redis responds `PONG`.

**macOS / Linux**

```bash
export TEST_DATABASE_URL='postgresql+psycopg://postgres:test-only@127.0.0.1:15432/rfq_test'
export TEST_REDIS_URL='redis://127.0.0.1:16379/15'
python -m pytest backend/tests
```

**Windows PowerShell**

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://postgres:test-only@127.0.0.1:15432/rfq_test'
$env:TEST_REDIS_URL = 'redis://127.0.0.1:16379/15'
python -m pytest backend/tests
```

Afterward, stop the two disposable test containers:

```bash
docker stop rfq-tests-postgres rfq-tests-redis
```

</details>

[GitHub Actions](.github/workflows/ci.yml) installs hash-locked Python dependencies, checks SQLite migrations, runs the complete backend suite with PostgreSQL 17/Redis 7, audits dependencies, builds the backend Docker image, and runs the locked frontend install, tests and build. It **does not deploy** the application.

## Security and access control

- **Authentication:** salted PBKDF2-HMAC-SHA256 hashes with 600,000 iterations; legacy hash verification and upgrade on successful login. HMAC-signed bearer tokens expire after 60 minutes by default.
- **Session lifecycle:** logout revokes the specific token. Operator password resets/deactivation increment the user's token version, invalidating earlier sessions.
- **Authorization:** the server checks buyer ownership and supplier invitations. Competitor totals/ranks remain visible to suppliers; identities and charge breakdowns are masked.
- **Request protection:** shared Redis limits, account-based login throttling, explicit proxy trust, bounded body buffering and database timeouts. Allowed cross-origin clients can read control errors.
- **Audit integrity:** hash chains, unique sequences and database guards against updates/deletes; PostgreSQL also guards truncation. Database administrators can disable these controls, so this is not an externally immutable archive.
- **Configuration:** production mode rejects unsafe signing keys and non-HTTPS CORS origins. Response headers and the retained Vercel configuration add browser protections.
- **Dependencies:** separate hash-locked runtime and development requirements; frontend lockfile and CI audits.

Browser tokens currently live in localStorage and are readable by JavaScript. The demo uses a custom signed-token format, not an OAuth/OIDC identity provider. Public demo credentials must not be used for real business data.

## API overview

Interactive request/response schemas are available at [`/docs`](http://localhost:8000/docs) while the API runs locally.

| Method | Endpoint | Access / purpose |
| --- | --- | --- |
| POST | `/api/auth/login` | Validate credentials and issue a token. |
| POST | `/api/auth/logout` | Revoke the current authenticated token. |
| GET | `/api/auth/me` | Current authenticated user. |
| GET | `/api/auth/suppliers` | Buyer: list active suppliers for invitations. |
| GET | `/api/rfqs` | Authenticated: scoped list with `limit` and `offset`. |
| POST | `/api/rfqs` | Buyer: create RFQ and invitations. |
| GET | `/api/rfqs/{id}` | Authorized user: detail, rankings and paginated history. |
| POST | `/api/rfqs/{id}/bids` | Invited supplier: submit a quote. |
| GET | `/health` | Process liveness. |
| GET | `/ready` | Database readiness. |
| GET | `/api/operations/jobs` | Buyer: close-job freshness; 503 if stale or missing. |

Listings and histories default to 25 rows and allow up to 100. Details accept `history_limit`, `bids_offset` and `activity_offset`.

## Configuration and operator commands

Compose contains development settings. For custom environments, use [backend/.env.example](backend/.env.example) and [frontend/.env.example](frontend/.env.example) as references.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLite or PostgreSQL connection. |
| `APP_ENV`, `SECRET_KEY`, `CORS_ORIGINS` | Environment, signing secret and explicit frontend origins. |
| `SEED_DEMO_USERS`, `DEMO_USER_PASSWORD` | Create missing demo accounts and choose their initial password. |
| `ACCESS_TOKEN_MINUTES` | Session lifetime; default 60. |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Redis connections for background jobs. |
| `RATE_LIMIT_REDIS_URL`, `TRUSTED_PROXY_CIDRS` | Shared request limits and verified forwarding proxies. |
| `API_RATE_LIMIT_PER_MINUTE`, `AUTH_RATE_LIMIT_PER_MINUTE`, `API_MAX_BODY_BYTES` | Request protection thresholds. |
| `AUCTION_CLOSE_SCAN_INTERVAL_SECONDS` | Close scan interval; default 60 seconds. |
| `RUN_CELERY_IN_WEB` | Optional combined supervisor mode; keep false with separate Compose workers. |
| `VITE_API_URL` | Frontend API URL at development/build time; defaults to localhost. |
| `VITE_REVIEWER_PASSWORD` | Intentionally public demo autofill value; never a private secret. |

Vite loads frontend environment files. The backend reads exported process variables. Changing the seed flag or demo password does **not** deactivate or reset existing accounts.

Run account commands from `backend/` with the intended database configured. Password entry uses a hidden prompt:

```bash
python -m app.manage_users create --email person@example.com --name "Person" --company "Carrier" --role supplier
python -m app.manage_users set-password --email person@example.com
python -m app.manage_users deactivate --email person@example.com
python -m app.manage_users deactivate-demo
```

## Repository layout

```text
backend/
  app/
    api/                 Auth and RFQ HTTP routes
    core/                Environment settings
    services/            Auction rules, bounded queries, audit and closure
    models.py            Database models and constraints
    schemas.py           Request/response models
    middleware.py        Request size, rate and proxy controls
    security.py          Passwords, tokens and identity checks
    tasks.py             Close scans and job heartbeat
    manage_users.py      Operator account management
    migrate.py           Serialized migration startup
    run.py               Optional web/worker supervisor
  migrations/            Alembic schema revisions
  tests/                 Unit, HTTP and infrastructure integration tests
frontend/
  src/
    components/          Login, listing, RFQ forms, rankings and history
    App.jsx              Session lifecycle and request coordination
    api.js               API client, timeouts and error handling
docs/                    HLD, diagrams, schema and engineering records
.github/workflows/ci.yml Verification pipeline; no automatic deployment
docker-compose.yml       Local PostgreSQL, Redis, API, worker and Beat
```

## Tradeoffs and next steps

This is a recruitment/portfolio implementation with explicit boundaries:

- Each supplier account is one bidding identity; multi-user supplier organizations are not modeled.
- UI freshness uses polling, not WebSockets. Redis is a broker and rate-limit store, not a listing cache.
- Scheduled close scans are bounded to 5,000 closures per run; a larger backlog carries over.
- Exactly one Beat scheduler should run. The former hosted demo combined web/worker/Beat because of plan limits; Compose separates them.
- Self-service email recovery, external immutable audit checkpoints, backup/restore drills, alert delivery and sustained load benchmarks remain future work.
- Dependencies and security controls require ongoing maintenance; passing tests are not a production certification.

The repository retains Docker and hosting configuration for reference. A future deployment needs new environment configuration, matching frontend API/CSP and backend CORS settings, and a deliberate restart of the cloud services. See the [hosting retirement record](docs/deployment-status.md).
