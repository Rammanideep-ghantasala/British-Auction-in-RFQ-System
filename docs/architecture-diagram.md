# Architecture Diagram

```mermaid
flowchart TB
    Recruiter[Reviewer / User Browser]

    subgraph Vercel["Vercel"]
        React[React + Vite Frontend]
    end

    subgraph Railway["Railway"]
      subgraph Demo["Single demo backend container: supervisor; one replica"]
        API[FastAPI Backend]
        Worker[Celery Worker]
        Beat[Celery Beat Scheduler]
      end
        Postgres[(PostgreSQL Database)]
        Redis[(Redis Broker)]
    end

    subgraph BackendModules["Backend Modules"]
        Auth[Auth + RBAC]
        Controls[Redis rate limits + bounded request body]
        RFQAPI[RFQ REST APIs]
        AuctionService[Auction Domain Service]
        AuditService[Append-only Audit Service]
        CloseService[Auction Close Service]
        Models[SQLAlchemy Models]
    end

    Recruiter -->|HTTPS| React
    React -->|HTTPS REST API + Bearer Token| API

    API --> Controls
    Controls --> Redis
    API --> Auth
    API --> RFQAPI
    RFQAPI --> AuctionService
    RFQAPI --> AuditService
    RFQAPI --> Models
    Models --> Postgres

    Beat --> Redis
    Redis --> Worker
    Worker --> CloseService
    CloseService --> AuditService
    CloseService --> Models
    Auth --> Models
    AuctionService --> RFQAPI
```

The diagram shows the actual demo deployment. Web and Celery processes share a supervised container because of the hosting plan limit. A child failure ends the container so Railway can restart it. `/ready` checks PostgreSQL; the authenticated operations endpoint checks worker freshness. For production, split the web, worker and single Beat scheduler into independent services.

## Request Flow

```mermaid
sequenceDiagram
    actor Buyer
    actor Supplier
    participant Frontend as React Frontend
    participant API as FastAPI Backend
    participant Service as Auction Service
    participant Audit as Audit Service
    participant Worker as Celery Worker
    participant DB as PostgreSQL

    Buyer->>Frontend: Sign in
    Frontend->>API: POST /api/auth/login
    API->>DB: Verify user credentials
    API-->>Frontend: Bearer token

    Buyer->>Frontend: Create RFQ
    Frontend->>API: POST /api/rfqs
    API->>Service: Validate auction window/config
    API->>DB: Store RFQ + invitations
    API->>Audit: Append created event
    Audit->>DB: Store hash-chained activity log
    API-->>Frontend: RFQ details

    Supplier->>Frontend: Sign in and open invited RFQ
    Frontend->>API: GET /api/rfqs/{id}
    API->>DB: Verify invitation
    API-->>Frontend: RFQ details with masked competitor data

    Supplier->>Frontend: Submit quote
    Frontend->>API: POST /api/rfqs/{id}/bids
    API->>Service: Validate bid, rank, apply extension rules
    API->>DB: Store bid + extension changes
    API->>Audit: Append bid/extension events
    API-->>Frontend: Updated RFQ details

    Worker->>DB: Find expired unclosed auctions
    Worker->>DB: Persist closed_at + close_reason
    Worker->>Audit: Append closed event
```

## Component Responsibilities

| Component | Responsibility |
| --- | --- |
| React Frontend | User interaction, forms, RFQ listing, details, ranking display |
| FastAPI Backend | API routing, validation, auth, RBAC, persistence, request safeguards |
| Auction Service | Business rules for ranking, rebids, status, and extension logic |
| Audit Service | Append-only activity logging with sequence and hash-chain verification |
| Celery Worker + Beat | Scheduled auction close transitions |
| PostgreSQL | Durable storage for users, RFQs, invitations, bids, and logs |
| Redis | Broker/result backend for Celery jobs |
| GitHub Actions | Migration check, backend tests, frontend build |
| Railway | Backend and database hosting |
| Vercel | Frontend hosting |
