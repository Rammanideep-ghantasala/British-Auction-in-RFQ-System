# Deployment status

**Retired on 21 November 2026.** The repository is maintained as a locally runnable GitHub portfolio project. Follow the [README quick start](../README.md#quick-start); no hosting account is required.

## Shutdown record

| Component | Final state | Verification |
| --- | --- | --- |
| Vercel frontend project (`frontend`) | Paused | Former public URL responds with HTTP 503 and `DEPLOYMENT_PAUSED`. |
| Railway FastAPI backend | Stopped | Project inventory shows no active deployment; former `/health` URL responds with Railway's application-not-found 404. |
| Celery worker and Beat | Stopped with their backend container | The hosted demo ran both under the backend supervisor. The unused standalone `Celery-Worker` service has no deployed instance. |
| Railway PostgreSQL | Stopped | No active deployment remains. |
| Railway Redis | Stopped | No active deployment remains. |

The existing GitHub repository remains public. Vercel has no connected Git repository, and the Railway web service has no repository source. GitHub Actions runs tests, audits and builds only; pushing documentation does not restart hosted services.

## What was retained

- Source, commit history, CI and hosting configuration remain available for review.
- Railway PostgreSQL and Redis volumes were retained rather than erased. Stopping compute is not a request to destroy stored data or cancel an account/subscription.
- Vercel's project and deployment artifacts remain available for an intentional future resume.
- Historical review/release records remain dated evidence, not claims that a live demo is currently available.

This shutdown does not establish a zero cloud balance or cancel subscription/storage charges. Review provider billing separately if the retained storage is no longer needed.

## Local builds and future hosting

`frontend/.env.production` now points to `http://localhost:8000`, so a default local production build no longer calls the retired Railway API. Vite's development server also defaults to the local API.

Before hosting again, explicitly configure `VITE_API_URL`, the frontend Content-Security-Policy in `frontend/vercel.json`, backend CORS origins and production secrets. Start the database and Redis before the API and workers, apply migrations, and keep exactly one Beat scheduler. A hosting restart is a separate deliberate action; none is automated by this repository.

Provider references: [Railway deployment removal](https://docs.railway.com/cli/down), [Vercel project pausing](https://vercel.com/docs/projects/managing-projects#pausing-a-project).
