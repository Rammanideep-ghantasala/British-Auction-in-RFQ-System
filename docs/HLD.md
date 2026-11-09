# High-Level Design: British Auction RFQ System

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
- Activity logs for RFQ creation, bids, and extensions
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
| PostgreSQL Database | Stores users, auctions, invitations, bids, and activity logs |
| Railway | Hosts FastAPI backend and PostgreSQL |
| Vercel | Hosts React frontend |

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
- CORS is restricted to the deployed frontend origin.
- Security headers are set by the backend.

## Deployment

| Layer | Platform |
| --- | --- |
| Frontend | Vercel |
| Backend | Railway |
| Database | Railway PostgreSQL |

Live frontend:

```text
https://frontend-one-jade-ojg8dffinq.vercel.app
```

Live backend:

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

Current verified result:

```text
22 backend tests passing
```
