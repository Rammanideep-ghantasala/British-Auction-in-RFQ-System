# British Auction RFQ System

Full-stack RFQ application for British Auction-style bidding. The project is structured for the Full Stack Intern role requirements: FastAPI backend, React frontend, PostgreSQL-ready persistence, REST APIs, and test coverage for the auction rules.

## Live Demo

Frontend:

```text
https://frontend-one-jade-ojg8dffinq.vercel.app
```

Backend health:

```text
https://british-auction-rfq-system-production.up.railway.app/health
```

Current deployed backend setup:

- Railway backend service: FastAPI, Alembic migrations, and supervised in-container Celery runner
- Railway PostgreSQL service: production database
- Railway Redis service: Celery broker/result backend
- Vercel frontend service: React/Vite UI connected to the Railway API

For the live recruiter demo, `RUN_CELERY_IN_WEB=true` is enabled because Railway's free resource limit blocked separate Celery Worker and Celery Beat services. The scheduled auction close job runs every 60 seconds through Celery Beat inside the backend container. A supervisor terminates the container if the web or worker process exits, allowing Railway to restart it. Keep this deployment at one replica to avoid multiple schedulers. For production, upgrade Railway and split the worker and beat into separate services.

## Assignment Deliverables

| Deliverable | Location |
| --- | --- |
| Simple HLD | [docs/HLD.md](docs/HLD.md) |
| Architecture Diagram | [docs/architecture-diagram.md](docs/architecture-diagram.md) |
| Database Schema Design | [docs/database-schema.md](docs/database-schema.md) |
| Backend Code | [backend/](backend/) |
| Frontend Code | [frontend/](frontend/) |

## Tech Stack

- Backend: Python, FastAPI, SQLAlchemy 2, Pydantic, Alembic
- Database: PostgreSQL in production, SQLite fallback for local development/tests
- Async jobs: Celery with Redis broker for scheduled auction close transitions
- Frontend: React + Vite
- Testing: pytest for backend domain and API route behavior
- CI/CD: GitHub Actions for migrations, backend tests, and frontend builds
- Deployment target: Railway for backend/PostgreSQL, Vercel for frontend

## Project Structure

```text
backend/
  app/
    api/              FastAPI route handlers
    core/             environment/config handling
    services/         auction, audit, and close-transition services
    db.py             SQLAlchemy session setup
    models.py         database models
    schemas.py        request/response schemas
  migrations/         Alembic migrations
  tests/              backend tests
frontend/
  src/
    components/       React UI components
    api.js            API client
    formatters.js     display/date helpers
docker-compose.yml    PostgreSQL + Redis + API + Celery worker/beat local stack
.github/workflows/    CI migration, test, and build checks
docs/                 HLD, architecture diagram, and schema design
```

## Requirements Covered

- Create RFQs with British Auction enabled
- Capture bid start, bid close, forced bid close, and pickup/service dates
- Configure trigger window X, extension duration Y, and extension trigger type
- Submit supplier quote details: carrier, freight/origin/destination charges, transit time, validity
- Rank suppliers by total quote as L1, L2, L3
- Extend auction time for:
  - bid received in last X minutes
  - any supplier rank change in last X minutes
  - L1 rank change in last X minutes
- Never extend beyond forced bid close time
- Reject duplicate RFQ reference IDs
- Reject RFQs without at least one invited active supplier
- Reject pickup/service dates that are not after forced bid close
- Reject supplier rebids that do not lower their current quote
- Record activity logs for RFQ creation, bid submissions, and time extensions
- Preserve append-only activity logs with sequence numbers and hash-chain verification
- Close expired auctions through a scheduled Celery task
- Apply API rate limiting and request body size limits
- Expose listing and details views through React
- Authenticate buyers and suppliers with signed bearer tokens
- Restrict RFQ creation to buyers and bidding to invited suppliers
- Mask competitor quote details from supplier users
- Paginate RFQ listing responses
- Provide frontend pagination controls for RFQ listings
- Store money using fixed-precision Decimal/Numeric values

## Reviewer Demo Accounts

The deployed demo uses these reviewer accounts:

```text
Buyer:
buyer@gocomet.test / RfqReview9WJ4xM72QpZ6L

Supplier:
apex@carrier.test / RfqReview9WJ4xM72QpZ6L

Supplier:
swift@carrier.test / RfqReview9WJ4xM72QpZ6L
```

On the sign-in screen, demo account buttons fill both email and password for quick prototype review. The reviewer still clicks **Sign In** manually.

For local development, `backend/.env.example` uses `DEMO_USER_PASSWORD=password123`.

Before real production use, set `SEED_DEMO_USERS=false` and explicitly deactivate existing demo accounts with `python -m app.manage_users deactivate-demo`. The seeding flag only controls creation; changing `DEMO_USER_PASSWORD` does not change existing passwords. Use the operator commands below to provision accounts or reset a password.

## Run Locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt
python -m app.migrate
uvicorn app.main:app --reload --no-proxy-headers
```

On Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements-dev.txt
python -m app.migrate
uvicorn app.main:app --reload --no-proxy-headers
```

The API runs at `http://localhost:8000`.

Interactive docs:

```text
http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

The frontend runs at `http://localhost:5173`.

If the backend URL changes, create `frontend/.env`:

```text
VITE_API_URL=http://localhost:8000
```

## Run With PostgreSQL

```bash
docker compose up --build
```

This starts PostgreSQL, Redis, the FastAPI API, a Celery worker, and Celery Beat for scheduled close checks.

Then run the frontend separately:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

## Tests

```bash
python -m pytest backend/tests
cd frontend
pnpm run test
pnpm run build
```

Current backend coverage includes:

- auction lifecycle statuses
- extension trigger behavior
- forced-close caps
- ranking by total quote
- buyer/supplier authentication
- role-based access controls
- invited supplier visibility rules
- supplier carrier-name spoofing rejection
- client-submitted bid timestamp rejection
- supplier masking for competitor bid details
- Decimal money precision
- listing pagination behavior
- RFQ supplier invitation validation
- pickup/service date validation
- duplicate reference rejection
- non-lowering supplier rebid rejection
- invalid/imported bid history protection
- API route persistence behavior
- append-only audit log protection
- scheduled auction close transitions
- API rate-limit and body-size guard decisions

Current frontend coverage includes:

- demo account buttons fill email and password for quick prototype review
- rejected bid submissions preserve typed values
- successful bid submissions reset the quote form
- RFQ listing pagination controls
- quote money formatting keeps decimal precision visible

## Deployment

### Backend on Railway

1. Create a Railway project.
2. Add a PostgreSQL service.
3. Add a Redis service.
4. Deploy the `backend/` service from GitHub or with the Railway CLI using `backend/` as the service root.
5. Set environment variables:

```text
DATABASE_URL=<Railway PostgreSQL DATABASE_URL>
CORS_ORIGINS=<Vercel frontend URL>
SECRET_KEY=<long random secret>
APP_ENV=production
SEED_DEMO_USERS=false
API_RATE_LIMIT_PER_MINUTE=300
AUTH_RATE_LIMIT_PER_MINUTE=20
API_MAX_BODY_BYTES=1048576
CELERY_BROKER_URL=<Redis URL>
CELERY_RESULT_BACKEND=<Redis URL>
AUCTION_CLOSE_SCAN_INTERVAL_SECONDS=60
RUN_CELERY_IN_WEB=true
RATE_LIMIT_REDIS_URL=<Redis URL, or defaults to CELERY_BROKER_URL in production>
TRUSTED_PROXY_CIDRS=
```

Railway commonly provides `postgres://...`; the app automatically normalizes it to the psycopg SQLAlchemy URL.

For a free-plan demo, keep `RUN_CELERY_IN_WEB=true`. This starts a lightweight Celery worker and Celery Beat inside the backend container:

```bash
celery -A app.celery_app:celery_app worker -B -l info --pool=solo --concurrency=1
```

For production, set `RUN_CELERY_IN_WEB=false` and run Celery Worker and Celery Beat as separate Railway services using the same backend image:

```bash
celery -A app.celery_app:celery_app worker -l info
celery -A app.celery_app:celery_app beat -l info
```

Recommended production service layout:

```text
Backend Web Service
  command: python -m app.run

Celery Worker Service
  command: celery -A app.celery_app:celery_app worker -l info

Celery Beat Service
  command: celery -A app.celery_app:celery_app beat -l info

Redis Service
  used by: CELERY_BROKER_URL and CELERY_RESULT_BACKEND

PostgreSQL Service
  used by: DATABASE_URL
```

### Frontend on Vercel

1. Import the repository in Vercel.
2. Set root directory to `frontend`.
3. Set environment variable:

```text
VITE_API_URL=<Railway backend URL>
VITE_REVIEWER_PASSWORD=<public reviewer password, for the demo only>
```

`VITE_*` values are included in the public browser bundle. Update the `connect-src` origin in `frontend/vercel.json` if you change the API hostname. Login fields start empty; choosing a demo account fills them without submitting.

4. Deploy.

## Architecture Notes

The important auction rules live in `backend/app/services/auction.py` as pure Python logic. This keeps business rules testable and prevents users from bypassing validation through the browser.

The FastAPI route layer handles HTTP concerns, authentication, authorization, database persistence, duplicate RFQ checks, row-level locking for bid writes, pagination, and response shaping. Ranking and visibility use supplier user IDs; identical company display names remain independent. Current quotes are selected in SQL, while bid/activity history is paginated. SQLAlchemy models use unique constraints for RFQ references and invitations, fixed-precision money columns, and relationship cascades for bids/logs.

Operational safeguards include Alembic migrations at container startup, API rate/body limits, append-only audit logs with tamper-evident hashes, and Celery Beat-driven close transition jobs.

The React app is intentionally API-driven. It does not calculate final auction state locally; it displays the state returned by the backend.

## Current Demo Verification

The deployed demo has been verified with:

- backend health check returning `{"status":"ok"}`
- Railway backend deployment status `SUCCESS`
- Railway Redis deployment status `SUCCESS`
- Celery worker connected to Redis
- Celery Beat sending the scheduled `app.tasks.close_expired_auctions` task
- scheduled auction close task completing successfully
- backend test suite passing locally with PostgreSQL and Redis integration tests enabled
- frontend test suite passing locally including App-level race and polling regressions
- frontend production build passing locally

## Security Notes

- RFQ creation requires a buyer account.
- Quote submission requires an invited supplier account.
- Suppliers cannot spoof another carrier name; the backend uses the authenticated supplier company.
- Bid submission time is assigned by the server so suppliers cannot backdate quotes into closed auctions.
- Supplier users only see their own bid records. Competitor names and charge breakdowns are masked in rankings.
- The API uses bearer tokens, strict CORS headers, and basic security headers.
- The API enforces per-client request throttling and request body size limits.
- Activity logs reject UPDATE/DELETE at both ORM and database levels (PostgreSQL also rejects TRUNCATE), with unique sequence numbers and hash chaining. Database administrators can still disable triggers; this is not an externally immutable archive.
- Duplicate RFQ references are protected by both app-level validation and a database unique constraint.
- Bid writes use `SELECT ... FOR UPDATE` on supported databases to serialize close-time extension decisions.

## Remaining Production Hardening

For a full production rollout, I would still add:

- Self-service password recovery with verified email delivery (operator provisioning/password resets are implemented)
- Redis caching for read-heavy listing pages
- Distributed rate limiting at the external API gateway/CDN layer
- External dashboards/alerts and tested backups (readiness and worker-heartbeat endpoints are implemented)


## Reliability and Security Update (11 November 2026)

See the [release verification and resolved failure cases](docs/hardening-release-2026-11-11.md).

- Supplier identity uses account IDs throughout rankings, rebid rules and visibility.
- Logout cancels pending browser work and revokes that particular server token.
- Existing 120,000-round password hashes upgrade to versioned 600,000-round PBKDF2 hashes on successful login.
- RFQ-specific bid drafts, duplicate-submit guards, readable validation messages and session recovery.
- Buyer all-bids table and supplier own-history table, ordered by price with pagination.
- Visible pages refresh every 15 seconds; hidden pages skip polling and logout cancels it.
- Delayed jobs preserve the original effective closure reason and record processing time separately.
- Shared Redis rate limits have TTLs and fail closed with HTTP 503 if Redis is unavailable.
- Forwarded IP headers are ignored by default. Configure only verified proxy CIDRs, never a wildcard; Uvicorn proxy parsing is disabled. With no trusted proxy configured, clients behind a proxy share the peer-IP budget, plus per-account login limits.
- Early body buffering is bounded to 1 MiB by default and 15 seconds, including streamed requests.
- Vercel serves CSP, framing, MIME-sniffing, referrer and permissions headers.
- Runtime dependency versions and hashes are locked separately from development/test tools.

### Operator commands

Run from `backend/` with the intended database configured. Passwords are entered through hidden prompts rather than command arguments:

```bash
python -m app.manage_users create --email person@example.com --name "Person" --company "Carrier" --role supplier
python -m app.manage_users set-password --email person@example.com
python -m app.manage_users deactivate --email person@example.com
python -m app.manage_users deactivate-demo
```

Password changes and deactivation invalidate previously issued tokens for that user. Self-service email recovery is a separate future feature.

### Health and operations

- `GET /health`: process liveness.
- `GET /ready`: database readiness; Railway's deployment health check.
- `GET /api/operations/jobs`: authenticated buyer-only worker freshness; returns 503 when the last successful close scan is missing or stale.
- Each scheduled scan handles up to 50 batches of 100 auctions; remaining backlog is picked up by the next scan.
- Redis/worker failure does not permit late bids: the API still checks the deadline transactionally.
- Migrations run before supervised services and serialize using a PostgreSQL advisory lock.
- Migration `20261111_0003` backfills old audit hashes before enforcing non-null hashes/sequences and database triggers. This establishes integrity from migration time, not proof of historical authenticity.
- PostgreSQL connections check stale pooled connections and bound connect, query and lock waits.
- Preserve exactly one Beat scheduler. Use separate supervised web/worker/beat services when the hosting plan supports them.

### Integration tests and dependency locks

```bash
# Use disposable services; never point test variables at the production database.
TEST_DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/rfq_test TEST_REDIS_URL=redis://localhost:6379/15 python -m pytest backend/tests
cd frontend
pnpm run test
pnpm run build
```

Without test service URLs, PostgreSQL/Redis integration cases are explicitly skipped. GitHub Actions provides both services and checks legacy migrations, metadata consistency, concurrency, HTTP controls, dependency audits, backend Docker build and frontend tests/build.

Regenerate locks with Python 3.12 and uv:

```bash
uv pip compile backend/requirements.in --universal --generate-hashes -o backend/requirements.txt
uv pip compile backend/requirements-dev.in -c backend/requirements.txt --universal --generate-hashes -o backend/requirements-dev.txt
```

Current limitations: public demo accounts share demo data; browser bearer tokens remain accessible to JavaScript; database administrators can disable audit triggers; external immutable audit storage, email recovery, backup automation and paging/alerts are not provided by this demo.
