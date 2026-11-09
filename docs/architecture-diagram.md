# Architecture Diagram

```mermaid
flowchart TB
    Recruiter[Reviewer / User Browser]

    subgraph Vercel["Vercel"]
        React[React + Vite Frontend]
    end

    subgraph Railway["Railway"]
        API[FastAPI Backend]
        Postgres[(PostgreSQL Database)]
    end

    subgraph BackendModules["Backend Modules"]
        Auth[Auth + RBAC]
        RFQAPI[RFQ REST APIs]
        AuctionService[Auction Domain Service]
        Models[SQLAlchemy Models]
    end

    Recruiter -->|HTTPS| React
    React -->|HTTPS REST API + Bearer Token| API

    API --> Auth
    API --> RFQAPI
    RFQAPI --> AuctionService
    RFQAPI --> Models
    Models --> Postgres

    Auth --> Models
    AuctionService --> RFQAPI
```

## Request Flow

```mermaid
sequenceDiagram
    actor Buyer
    actor Supplier
    participant Frontend as React Frontend
    participant API as FastAPI Backend
    participant Service as Auction Service
    participant DB as PostgreSQL

    Buyer->>Frontend: Sign in
    Frontend->>API: POST /api/auth/login
    API->>DB: Verify user credentials
    API-->>Frontend: Bearer token

    Buyer->>Frontend: Create RFQ
    Frontend->>API: POST /api/rfqs
    API->>Service: Validate auction window/config
    API->>DB: Store RFQ + invitations + activity log
    API-->>Frontend: RFQ details

    Supplier->>Frontend: Sign in and open invited RFQ
    Frontend->>API: GET /api/rfqs/{id}
    API->>DB: Verify invitation
    API-->>Frontend: RFQ details with masked competitor data

    Supplier->>Frontend: Submit quote
    Frontend->>API: POST /api/rfqs/{id}/bids
    API->>Service: Validate bid, rank, apply extension rules
    API->>DB: Store bid + extension/activity logs
    API-->>Frontend: Updated RFQ details
```

## Component Responsibilities

| Component | Responsibility |
| --- | --- |
| React Frontend | User interaction, forms, RFQ listing, details, ranking display |
| FastAPI Backend | API routing, validation, auth, RBAC, persistence |
| Auction Service | Business rules for ranking, rebids, status, and extension logic |
| PostgreSQL | Durable storage for users, RFQs, invitations, bids, and logs |
| Railway | Backend and database hosting |
| Vercel | Frontend hosting |
