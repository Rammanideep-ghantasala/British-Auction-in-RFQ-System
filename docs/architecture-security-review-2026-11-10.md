# Architecture, security, and reliability review

Review date: 10 November 2026. Source revision: `3243cc3`.

This is a historical review of that revision. The confirmed defects below were addressed in the [11 November hardening release](hardening-release-2026-11-11.md); retain this report as the original evidence, not as a description of the current implementation.

The project is a credible recruitment demo with a sensible modular monolith, but it has confirmed correctness and security defects. It should not yet be described as production-ready or as having immutable audit storage. The existing design can be improved without a rewrite or microservices.

| Area | Assessment / 10 | Basis |
| --- | --- | --- |
| Architecture | 7 | Pure auction rules, clear API/data boundaries, transactional writes, appropriate technology choices; supplier identity and transaction orchestration need improvement. |
| Auction correctness | 7 | Boundary and PostgreSQL concurrency checks passed; same-name suppliers and delayed closure classification fail. |
| Security | 5 | Useful RBAC, invitation checks, password hashing and token verification; rate limiting, session lifecycle, safe configuration and audit integrity remain incomplete. |
| Frontend reliability | 5 | Basic forms and pagination work; session races, cross-auction draft retention, missing history and error handling need fixes. |
| Automated testing | 5 | Existing tests pass, but miss HTTP middleware, session races, PostgreSQL concurrency and migration drift. |
| Operations and scale | 4 | Demo deployment is reachable; worker supervision, dependency readiness, bounded queries and reproducible backend builds need work. |
| Assignment/demo overall | 7 | Most requested behavior exists; the buyer bid-history view is missing and the confirmed defects should be fixed. |
| Readiness for real business data | 4 | Material identity, session, integrity and operational gaps remain. |

Scores are engineering judgments, not vulnerability percentages, certifications, or guarantees.

## Scope and evidence

Reviewed backend routes, domain services, schemas, models, migrations, middleware, authentication, Celery, frontend components and API client, Docker/Compose/Railway/Vercel configuration, GitHub Actions, README and design documents. Requirements comparison used only pages 1-4 of the supplied assignment PDF; page 5 was excluded.

Existing test suites were rerun. Additional probes used in-memory SQLite, mocked frontend APIs, and an isolated PostgreSQL 17 container on localhost. Public checks were limited to read-only availability and response headers. Application source and live data were not changed by this review.

| Check | Result |
| --- | --- |
| Existing backend suite | 28 passed |
| Existing frontend suite | 5 passed |
| Frontend production build | Passed; JS bundle approximately 241 KB / 74 KB gzip |
| Additional auction boundaries/rank behavior | 23 passed |
| Additional backend HTTP/security/integrity expectations | 5 passed, 9 failed |
| Additional frontend reliability/requirements expectations | 5 failed |
| PostgreSQL concurrency scenarios | 3 passed |
| Fresh PostgreSQL migrations | Both revisions applied successfully |
| Migration/model consistency | 3 index differences detected |
| Locked frontend dependency audit | 0 advisories reported across 172 dependencies |
| Local installed backend dependency graph via OSV | 49 distributions checked; one unique advisory for local pytest 8.3.3, described below |
| Live frontend | HTTP 200 |
| Live backend `/health` | HTTP 200, `{"status":"ok"}` |
| Live unauthenticated `/api/rfqs` | HTTP 401 |

The 14 failed targeted expectations are grouped below; they are not 14 independent externally exploitable vulnerabilities. One expectation specifically tests the README's claim that turning off demo seeding disables existing users. The implementation does not do that.

Local probe sources are retained under the ignored `.pytest_cache/architecture-review/` directory: `test_review.py`, `test_boundaries.py`, `postgres_review.py`, `frontend-review.test.jsx`, and `dependency_review.py`. The frontend probe was removed from Vitest's normal discovery path after execution. The PostgreSQL probe uses a disposable localhost database and is not intended to target a deployed database.

## Confirmed defects and priority fixes

### 1. High: company names are used as supplier identity

Evidence: `backend/app/services/auction.py:173`, `backend/app/services/auction.py:298`, `backend/app/api/rfqs.py:83`, `backend/app/api/rfqs.py:112`. `User.company_name` has no uniqueness constraint.

Two separate invited supplier accounts were given the same company name. The second account, with no own bid, received the first account's unmasked freight/origin/destination charges and transit/validity information. After both accounts bid, their two quotes collapsed into one ranking. Rebid validation also compares against the other account's quote. Case and whitespace normalization make additional name variants collide.

Use a stable supplier identity in domain candidates, ranking keys, rebid checks, visibility filters and audit records. For this assignment, `supplier_user_id` is sufficient. If a business supplier may have several users, model an explicit supplier organization and its memberships; do not infer membership from a display name.

### 2. High: a response arriving after logout restores the session

Evidence: `frontend/src/App.jsx:41`, `frontend/src/App.jsx:119`.

Reproduction: start with a stored session, delay `/auth/me`, click Sign Out, then let the request finish. `bootstrapSession` writes the old token and user back into state and localStorage. The login screen disappears and the user becomes signed in again.

Invalidate outstanding work when the session changes. Use cancellation and a session generation/token check before every asynchronous state or storage write. Add an integration regression test for logout during bootstrap and account changes during requests.

### 3. High business correctness: quote drafts carry across RFQs

Evidence: `frontend/src/components/AuctionDetail.jsx:61`, `frontend/src/components/BidForm.jsx:4`.

Reproduction: type a quote for RFQ A, then select RFQ B. The reused form keeps A's values, while the parent submits against B's ID. The component probe preserved `999` after the auction ID changed. This creates a risk of an unintended quote on a different auction.

Key the form by auction ID, or explicitly retain drafts in a map keyed by auction ID. Scope in-flight submissions to the auction they started on. Preserve failed-submission drafts for the same auction only.

### 4. High, dependent on proxy behavior: login throttling trusts client headers

Evidence: `backend/app/middleware.py:69`, `backend/app/middleware.py:90`.

With the login limit set to two, three invalid login requests with different `X-Forwarded-For` values all reached authentication and returned 401; the third should have been throttled. The middleware trusts the first header value without establishing that the sender is a trusted proxy. Railway's actual header sanitization was not attack-tested, so this is a confirmed application-level weakness with deployment-dependent external exploitability.

The limiter is also per process, and its dictionary never removes old client keys. Multiple replicas have independent limits, and many unique client identifiers can grow memory usage.

Use a verified proxy trust boundary, limits keyed by client and account where appropriate, and a shared limiter with TTLs or a trusted gateway. Bound local state if a local fallback remains.

### 5. Medium: audit storage is not immutable

Evidence: `backend/app/models.py:139`, `backend/app/services/audit.py:107`, `backend/migrations/versions/20261110_0002_operational_controls.py:35`.

The ORM event hooks block normal instance updates/deletes, but `Session.execute(update(ActivityLog)...)` succeeded. A bulk delete of the final audit entry also succeeded, and verification of the remaining chain still returned true. A hash chain without a trusted external head cannot prove that its tail was not removed. This requires database/write access; no public arbitrary-SQL endpoint was found.

The operational migration adds nullable hash/sequence columns without backfilling historical rows. The schema also lacks a unique `(auction_id, sequence_number)` constraint.

Separate the migration role from the runtime database role; restrict audit UPDATE/DELETE privileges and use database enforcement. Define an explicit legacy-log migration policy. Use a trusted checkpoint or external append-only sink if stronger tamper detection is required. Until then, describe the feature as an application-guarded, hash-chained activity log.

### 6. Medium: a delayed close job changes auction history

Evidence: `backend/app/services/auction_closure.py:23`, `backend/app/services/auction.py:212`.

An auction whose ordinary deadline was earlier than its forced deadline was scanned after both deadlines. The job recorded `forced-close` and the later forced deadline instead of the actual ordinary close deadline. The computed status also changes to Force Closed after the forced time if the worker has not persisted the earlier close yet.

Derive the reason from the auction's effective deadline, not the worker's observation time. Record processing time separately. Late bidding is still rejected by the request path; this defect affects historical state and audit accuracy, not acceptance of late bids in the tested cases.

### 7. Medium / assignment gap: buyer bid history is not displayed

Evidence: `frontend/src/components/AuctionDetail.jsx:53`, `backend/app/api/rfqs.py:163`.

Page 4 requires all supplier bids sorted by price. The API supplies `bids`, but the UI only renders current rankings. A component probe containing an older bid and a newer lower bid could not find the older quote amount anywhere in the view.

Add a buyer bid-history table showing the supplied bid records sorted by price, with supplier, charges, total, transit, validity and submitted time. Keep supplier visibility restrictions intact.

### 8. Medium: middleware errors are not usable by the cross-origin frontend

Evidence: `backend/app/main.py:26`, `backend/app/middleware.py:53`.

The rate/body middleware sits outside CORS. Its 429 response had no `Access-Control-Allow-Origin` for an allowed frontend origin, so the browser cannot read the JSON explanation. A streamed request over the body limit returned 400 with a generic parsing message instead of 413. The body was rejected; this test did not demonstrate bypass of the size limit.

Ensure CORS wraps error responses as well as successful responses. Handle streaming overflow at a layer where it cannot be converted into an unrelated parser error. Verify status, CORS, Retry-After and security headers through the full ASGI app.

### 9. Medium: frontend recovery and validation messages fail

Evidence: `frontend/src/App.jsx:11`, `frontend/src/App.jsx:199`, `frontend/src/api.js:20`.

A valid JSON object in localStorage containing a token but no user crashed rendering with a `company_name` TypeError. A normal Pydantic 422 error array became `[object Object]` in the UI.

Validate stored session shape and fall back to login safely. Normalize validation objects using their `msg` and field location. Handle 401 centrally, preserve structured error status, and add request timeouts/cancellation. The UI currently labels itself `API connected` whenever it is not loading, including after network failures, and only refreshes auction state manually.

### 10. Medium: the documented production switch leaves public accounts active

Evidence: `README.md:118`, `backend/app/security.py:135`.

Setting `SEED_DEMO_USERS=false` only skips creation; it does not deactivate users that already exist. Changing `DEMO_USER_PASSWORD` also does not rotate existing passwords because existing users are skipped. The additional test confirmed that the existing buyer remains active after seeding is disabled.

The public demo accounts and password autofill are intentional and appropriate to the requested prototype. They are not secret credentials. For production, explicitly deactivate/reset those stored accounts and remove demo UI/configuration. Keep demo and real business data separate. Document the actual switch behavior accurately.

### 11. Medium: migrations and model metadata disagree

Fresh PostgreSQL migrations succeed, but Alembic comparison proposes removing these indexes because they are absent from ORM metadata:

- `ix_activity_logs_auction_sequence`
- `ix_activity_logs_entry_hash`
- `ix_rfq_auctions_closed_at`

This also means `Base.metadata.create_all()` and Alembic do not construct equivalent schemas. Declare the indexes consistently and add a migration-drift check. Use migrations as the schema authority outside isolated tests. Run legacy-upgrade checks as well as fresh installs.

## Security hardening that remains

- **Unsafe configuration fallback:** `backend/app/core/config.py:12` accepts a publicly known signing key when `SECRET_KEY` is absent. A deployment using that fallback would allow token forgery for known user IDs. The deployed secret was not inspected, and no live forgery was attempted. Add an explicit environment mode and reject missing/default/weak secrets in production. Keep convenient defaults confined to local development.
- **Password hash work factor:** `backend/app/security.py:21` uses PBKDF2-HMAC-SHA256 with 120,000 iterations. OWASP currently recommends 600,000 for that algorithm and prefers Argon2id where applicable. Use versioned hash parameters and a rehash-on-login migration; simply changing the global constant would break verification of existing hashes. [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
- **Session lifecycle:** tokens default to eight hours, live in localStorage, and lack per-session revocation or refresh rotation. Logout only changes browser state. There are no managed user-provisioning, password-reset or password-change routes in this checkout. Consider maintained authentication/session libraries, shorter access sessions and server-side revocation. If moving to HttpOnly cookies, include the appropriate CSRF protection and cross-origin deployment design. [OWASP browser storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html).
- **Frontend response headers:** the live HTML had HSTS, but no CSP, X-Frame-Options, X-Content-Type-Options or Referrer-Policy. Backend security headers do not protect the separately hosted frontend. Configure the frontend host, particularly CSP with a suitable `frame-ancestors` policy. No exploitable XSS was demonstrated; React uses normal escaped rendering in the reviewed components.
- **Local Compose exposure:** PostgreSQL and Redis publish ports on all host interfaces, with development credentials/no Redis authentication. Bind them to localhost or keep them internal for local development. Do not use this Compose configuration unchanged for a public deployment.

## Architecture and operational assessment

The modular monolith is suitable for this assignment. Keep it. The pure domain service, Decimal amounts, unique RFQ references, explicit invitation table and database transactions are good foundations. PostgreSQL row locks genuinely serialized the tested bid writes:

- Eight simultaneous identical bids from one supplier: one 201, seven 400 responses.
- Two simultaneous bids from different suppliers: both 201, both five-minute extensions retained, valid audit chain.
- Two simultaneous close workers: one close event for the target auction.

These are bounded scenarios, not a sustained load benchmark or proof of every interleaving.

The next structural improvements should be stable supplier identity, an application-service layer for transactional create/bid workflows, and explicit response/view models for buyer versus supplier data. No generic repository layer or microservice split is necessary merely for architectural appearance.

Operational limitations:

- The Docker command backgrounds a combined worker/beat process and then runs Uvicorn. A worker death can leave the web process healthy. More web replicas would also start more schedulers. Preserve exactly one scheduler; Celery documents that duplicate schedulers produce duplicate tasks. The close operation passed its tested idempotency scenario, but duplicate scheduling still wastes work. [Celery periodic task guidance](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html).
- `/health` always returns success and checks neither the database nor job progress. Add database readiness and separate worker/beat heartbeats or last-success/job-lag monitoring. A healthy web response alone does not verify scheduled closing.
- One close task handles at most 100 rows per 60-second interval by default. A single scheduler therefore drains at most 100 expired rows per interval unless the task is changed to continue through batches. Backlogs can make persisted closure lag even though request-time bid rejection remains effective.
- Listing pagination limits auctions, but loads every historical bid for those auctions. Details and bid submission load all bids and activity logs, including while holding the auction row lock. Work and response size grow with history. Query current supplier quotes in SQL, paginate history, and keep the locked transaction small.
- Database connections have no explicit `pool_pre_ping`, statement/lock timeout or transient-failure policy. These are recovery/latency risks, not failures reproduced against Railway.
- The repository does not demonstrate restore testing, backup policy, alerting, deployment rollback or migration serialization. Railway-side configuration for those was not inspected.
- Redis is used as the Celery broker/result backend, not as a listing cache. Do not add caching before fixing query shape and defining freshness/invalidation requirements.

## Testing, dependency and documentation gaps

The existing `test_api.py` mostly calls Python route functions directly. Its body-size test checks the size comparison, and its rate-limit test calls a private limiter helper. These tests are useful units but do not exercise routing, middleware order, request parsing, dependency resolution or response serialization. That explains why all 28 passed while full HTTP probes failed.

CI checks migrations against SQLite, not PostgreSQL. Add PostgreSQL integration/concurrency checks, full HTTP authorization/middleware tests, frontend App-level session/request tests, and an end-to-end buyer-create/supplier-bid/buyer-review flow. Measure coverage before publishing a coverage percentage; test counts are not coverage percentages.

Backend requirements are lower bounds without a lock, and test tools are installed in the runtime image. A new deployment may resolve different versions from the local test environment. Split runtime/development dependencies, lock the resolved versions, scan the lock/image and build the same artifact that is tested. Frontend already has a lock and CI uses frozen installs.

The local backend dependency scan identified pytest 8.3.3 as affected by CVE-2025-71176 / GHSA-6w46-j5rx-g56g. The two OSV records refer to the same issue. It concerns test temporary-directory handling, not a demonstrated remote API exploit. The maintainers list a fix in pytest 9.0.3. The Railway image's installed versions were not collected, so its vulnerability status cannot be inferred from this local runtime. [pytest fix release](https://github.com/pytest-dev/pytest/releases/tag/9.0.3).

Documentation corrections:

- HLD still reports 26 backend tests; the actual existing suite has 28.
- HLD deployment table describes separate worker services, while README describes the combined-container demo arrangement. Label logical components versus actual deployed processes clearly.
- README local setup uses npm while CI uses pnpm and the repository's lock is pnpm. Standardize the documented install command.
- The Vercel instructions omit `VITE_REVIEWER_PASSWORD`, although the component uses it and otherwise falls back to the local demo password. Document it as public demo configuration, not a secret.
- State that user provisioning/reset are unimplemented, seeding does not disable existing users, and hash chaining is not database immutability.

## Assignment comparison: pages 1-4 only

RFQ fields, quote fields, X/Y configuration, the three extension modes, forced-close cap, listing fields, current ranking and extension activity are implemented. The added boundary probes covered exact auction start, trigger-window boundaries, close/forced close, rank changes, stable rebids and tie ordering.

The main UI omission is the all-bids table. Manual refresh also limits visibility of other suppliers' bids and extensions; bounded polling or a push mechanism would improve the demo. Supplier masking and RBAC are additional product choices from the project history. The shared demo accounts intentionally let reviewers try both roles and do not provide isolation between different recruiters using the same account.

## Recommended order of work

1. Fix supplier identity, logout/request races and per-auction quote drafts. Add regression tests for each.
2. Add the buyer bid-history table and correct delayed-close classification.
3. Fix proxy trust/rate limits, cross-origin error handling, production secret validation and demo-account shutdown instructions.
4. Strengthen audit enforcement and migration consistency; implement managed account/reset flows if they remain in scope.
5. Improve worker monitoring, bounded queries, dependency locking and PostgreSQL CI; then consider separate worker services and caching as load requires.

This review did not modify application behavior, deploy changes, rotate credentials or write to live auction data. It provides a prioritized implementation backlog with reproducible local evidence.
