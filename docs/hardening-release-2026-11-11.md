# Security and reliability release — 11 November 2026

This release addresses the confirmed defects in the [original review](architecture-security-review-2026-11-10.md). The architecture remains a modular FastAPI application with PostgreSQL, Redis/Celery and a React client.

| Original failure | Implemented correction |
| --- | --- |
| Suppliers with identical company names share ranking/privacy identity | Stable account IDs drive quote selection, ranking, rebid checks and visibility. |
| Pending requests restore a logged-out session | Session generations, cancellation and response ordering; server-side token revocation on logout. |
| Quote drafts carry into a different RFQ | RFQ-specific form state and submission guards. |
| Spoofable, process-local throttling | Explicit proxy trust, shared Redis counters with TTLs, account login limits and bounded development fallback. |
| Bulk changes bypass audit guards | Database triggers reject updates/deletes and PostgreSQL truncation; unique sequences and backfilled hash chains. |
| A delayed job mislabels the closing deadline | Effective deadlines determine the closure reason; processing time is recorded separately. |
| Buyer cannot review all bids | Paginated price-sorted bid history, with suppliers restricted to their own history. |
| Middleware errors lose CORS or return misleading status | CORS surrounds request controls; streamed overflow returns 413, limits return 429 with Retry-After. |
| Corrupt sessions and structured errors break recovery | Saved-session validation, readable validation errors, request timeouts, 401 handling and visible-page polling. |
| Disabling demo seeding leaves old demo users active | Explicit operator deactivation/password reset commands invalidate existing user sessions; documentation describes the actual switch behavior. |
| Migration and model schemas disagree | Aligned indexes/constraints and automated PostgreSQL metadata comparison. |

Additional safeguards include versioned password hashes with login-time upgrades, production configuration validation, frontend security headers, bounded history queries, database timeouts, readiness and job-heartbeat endpoints, migration serialization, supervised web/worker processes, and separate hash-locked runtime/development dependencies.

## Verification

Checks use isolated local test data and disposable PostgreSQL 17/Redis 7 services. They do not perform failure injection against the public deployment.

- Backend: **79 tests passed**, including regression, HTTP, boundary, migration, PostgreSQL concurrency and Redis integration tests.
- Frontend: **13 tests passed**, covering logout races, stale responses, malformed sessions, history, validation, polling and RFQ-specific drafts.
- Frontend production build and backend Docker build.
- Runtime Python and locked frontend dependency audits: no known advisories reported at verification time.
- Container smoke checks: database readiness, login, worker heartbeat, logout and rejection of a revoked token.
- Worker failure injection: terminating the worker makes the supervisor exit with status 1, allowing the host restart policy to recover the service.

Test counts and successful builds are evidence for these scenarios, not a coverage percentage, a sustained load test or a guarantee that all defects are eliminated.

## Deployment and operating limits

Vercel hosts the frontend. Railway hosts PostgreSQL, Redis and the web/Celery container. The current trial deployment retains one combined worker/Beat process under supervision; use separate services and exactly one scheduler before scaling web replicas. Schema migration `20261111_0003` runs before the web process starts and backfills historical audit hashes without deleting log content. The backfill establishes integrity from migration time, not proof of historical authenticity.

The public accounts intentionally share demo data. Browser bearer tokens remain readable by JavaScript. Database administrators can disable audit triggers, so these logs are not an external immutable archive. Self-service email recovery, external audit checkpoints, backup/restore drills and external alerting remain outside this demo release. Railway rejected the optional native pre-deployment snapshot because it requires a Pro workspace; no subscription was changed.
