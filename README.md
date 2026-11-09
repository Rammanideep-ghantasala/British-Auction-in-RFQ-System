# British Auction RFQ System

Full-stack RFQ application for British Auction-style bidding. The project is structured for the Full Stack Intern role requirements: FastAPI backend, React frontend, PostgreSQL-ready persistence, REST APIs, and test coverage for the auction rules.

## Tech Stack

- Backend: Python, FastAPI, SQLAlchemy 2, Pydantic
- Database: PostgreSQL in production, SQLite fallback for local development/tests
- Frontend: React + Vite
- Testing: pytest for backend domain and API route behavior
- Deployment target: Railway for backend/PostgreSQL, Vercel for frontend

## Project Structure

```text
backend/
  app/
    api/              FastAPI route handlers
    core/             environment/config handling
    services/         pure auction-domain rules
    db.py             SQLAlchemy session setup
    models.py         database models
    schemas.py        request/response schemas
  migrations/         Alembic migration baseline
  tests/              backend tests
frontend/
  src/
    components/       React UI components
    api.js            API client
    formatters.js     display/date helpers
docker-compose.yml    PostgreSQL + API local stack
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
- Reject supplier rebids that do not lower their current quote
- Record activity logs for RFQ creation, bid submissions, and time extensions
- Expose listing and details views through React
- Authenticate buyers and suppliers with signed bearer tokens
- Restrict RFQ creation to buyers and bidding to invited suppliers
- Mask competitor quote details from supplier users
- Paginate RFQ listing responses
- Store money using fixed-precision Decimal/Numeric values

## Demo Accounts

The backend seeds these accounts by default for local review:

```text
buyer@gocomet.test / password123
apex@carrier.test / password123
swift@carrier.test / password123
```

Set `SEED_DEMO_USERS=false` and provide real users/secrets before production deployment.

## Run Locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`.

Interactive docs:

```text
http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
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

Then run the frontend separately:

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
python -m pytest backend/tests
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
- duplicate reference rejection
- non-lowering supplier rebid rejection
- invalid/imported bid history protection
- API route persistence behavior

## Deployment Plan

### Backend on Railway

1. Create a Railway project.
2. Add a PostgreSQL service.
3. Deploy the `backend/` service from GitHub.
4. Set environment variables:

```text
DATABASE_URL=<Railway PostgreSQL DATABASE_URL>
CORS_ORIGINS=<Vercel frontend URL>
SECRET_KEY=<long random secret>
SEED_DEMO_USERS=false
```

Railway commonly provides `postgres://...`; the app automatically normalizes it to the psycopg SQLAlchemy URL.

### Frontend on Vercel

1. Import the repository in Vercel.
2. Set root directory to `frontend`.
3. Set environment variable:

```text
VITE_API_URL=<Railway backend URL>
```

4. Deploy.

## Architecture Notes

The important auction rules live in `backend/app/services/auction.py` as pure Python logic. This keeps business rules testable and prevents users from bypassing validation through the browser.

The FastAPI route layer handles HTTP concerns, authentication, authorization, database persistence, duplicate RFQ checks, row-level locking for bid writes, pagination, and response shaping. SQLAlchemy models use unique constraints for RFQ references and invitations, fixed-precision money columns, and relationship cascades for bids/logs.

The React app is intentionally API-driven. It does not calculate final auction state locally; it displays the state returned by the backend.

## Security Notes

- RFQ creation requires a buyer account.
- Quote submission requires an invited supplier account.
- Suppliers cannot spoof another carrier name; the backend uses the authenticated supplier company.
- Bid submission time is assigned by the server so suppliers cannot backdate quotes into closed auctions.
- Supplier users only see their own bid records. Competitor names and charge breakdowns are masked in rankings.
- The API uses bearer tokens, strict CORS headers, and basic security headers.
- Duplicate RFQ references are protected by both app-level validation and a database unique constraint.
- Bid writes use `SELECT ... FOR UPDATE` on supported databases to serialize close-time extension decisions.

## Remaining Production Hardening

For a full production rollout, I would still add:

- Managed user provisioning and password reset flows
- CI/CD with migration checks and frontend/backend builds
- immutable append-only audit logs
- Celery jobs for scheduled auction close transitions
- Redis caching for read-heavy listing pages
- rate limiting and request body size limits at the API gateway
