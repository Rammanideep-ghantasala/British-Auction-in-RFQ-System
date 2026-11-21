# Architecture and Request Flow

The hosted demo was retired on **21 November 2026**. These diagrams describe the current local setup. See the [README](../README.md) for commands and the [deployment record](deployment-status.md) for hosting status.

## Component diagram

```mermaid
flowchart LR
    User["Buyer / supplier"] --> Frontend["React + Vite<br/>localhost:5173"]
    subgraph Compose["Docker Compose"]
        API["FastAPI<br/>localhost:8000"]
        Auth["Authentication and access policies"]
        Domain["Auction rules"]
        ReadModel["Latest quotes and paginated history"]
        Audit["Audit append service"]
        DB[("PostgreSQL")]
        Redis[("Redis")]
        Beat["Celery Beat<br/>one scheduler"]
        Worker["Celery worker"]
        Close["Closure service"]
        API --> Auth
        Auth --> DB
        API --> Domain
        API --> ReadModel
        ReadModel --> DB
        API --> Audit
        Audit --> DB
        API -->|"Rate limits"| Redis
        Beat -->|"Scheduled task"| Redis
        Redis --> Worker
        Worker --> Close
        Close --> DB
        Close --> Audit
        Worker -->|"Heartbeat"| DB
    end
    Frontend -->|"HTTP JSON + bearer token"| API
```

The backend boxes are modules in one Python application, not separately deployed microservices. Route handlers coordinate transactions; the auction service calculates rules without owning HTTP or database connections.

## Bid transaction

```mermaid
sequenceDiagram
    actor Supplier
    participant UI as React
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Rules as Auction service
    participant Audit as Audit service

    Supplier->>UI: Submit quote for selected RFQ
    UI->>API: POST /api/rfqs/{id}/bids + token
    API->>DB: Resolve active user and session
    API->>DB: Lock auction row FOR UPDATE
    API->>API: Verify role, invitation and server time
    API->>DB: Read latest supplier quotes
    API->>Rules: Validate quote and compare rankings
    Rules-->>API: Accept/reject and extension decision
    alt Bid accepted
        API->>DB: Add bid and update deadline
        API->>Audit: Append bid / extension events
        Audit->>DB: Serialize sequence and add hash-chain entries
        API->>DB: Commit
        API-->>UI: Role-filtered detail and history page
    else Bid rejected
        API-->>UI: Validation / authorization error
        UI->>UI: Retain draft for this RFQ
    end
```

Acquiring the row lock before reading the current bidding state ensures that concurrent requests evaluate the preceding committed extension. A failed transaction rolls back its writes. Monetary values use Decimal/Numeric instead of binary floating-point arithmetic.

## Scheduled closure

```mermaid
sequenceDiagram
    participant Beat as Celery Beat
    participant Redis
    participant Worker as Celery worker
    participant DB as PostgreSQL

    Beat->>Redis: Enqueue close scan every configured interval
    Redis->>Worker: Deliver task
    Worker->>DB: Select expired, unclosed auctions with row locks
    Worker->>DB: Persist effective close reason and append event
    Note over Worker,DB: Repeated or competing scans do not add a second close event
    Worker->>DB: Record successful scan heartbeat
```

Each run processes up to 50 batches of 100 auctions. Request-time deadline validation remains authoritative even if the worker is delayed. A stale or missing heartbeat produces 503 from the buyer-only operations endpoint.

## Boundaries and recovery

| Concern | Design |
| --- | --- |
| Supplier isolation | Account IDs, invitations and buyer ownership are checked on the backend. |
| Read growth | SQL window query selects latest supplier quotes; bid/activity histories are paginated. |
| Browser races | Session generations, cancellation and request ordering prevent stale writes; drafts are keyed by RFQ. |
| Database recovery | Connection pre-ping, timeouts and serialized migrations; readiness checks the database. |
| Request protection | Redis counters with TTLs; body size/time bounds; explicit trusted proxy ranges. |
| Audit history | Hash chaining plus database mutation guards; privileged administrators remain outside this trust boundary. |
| Process recovery | Compose separates API/worker/Beat. Optional combined supervisor mode exits if a web or worker child dies. |

## Historical hosted topology

The retired Vercel frontend called a Railway API. Railway also held PostgreSQL and Redis. Due to the demo plan's service limit, the API container supervised the web process and a combined Celery worker/Beat process with one replica. That arrangement must not be scaled to multiple web replicas while each replica starts a scheduler.

The local Compose setup uses separate services and exactly one Beat scheduler. GitHub Actions runs verification only; it has no deployment step.
