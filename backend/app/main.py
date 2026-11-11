from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from app.api.auth import router as auth_router
from app.api.rfqs import router as rfq_router
from app.core.config import settings
from app.db import init_db, get_db
from app.models import JobHeartbeat
from app.security import require_buyer
from app.services.auction import as_utc
from app.middleware import RequestControlsMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="British Auction RFQ API",
    description="FastAPI backend for RFQ creation, British auction bidding, rankings, and activity logs.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RequestControlsMiddleware)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, error):
    logging.getLogger(__name__).error("Database request failed (%s)", type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database is temporarily unavailable. Please retry."}, headers={"Retry-After": "5"})

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth_router)
app.include_router(rfq_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from None
    return {"status": "ready"}


@app.get("/api/operations/jobs", dependencies=[Depends(require_buyer)])
def jobs_health(db: Session = Depends(get_db)):
    heartbeat = db.get(JobHeartbeat, "auction-close")
    age = (datetime.now(timezone.utc) - as_utc(heartbeat.succeeded_at)).total_seconds() if heartbeat else None
    if age is None or age > max(180, settings.auction_close_scan_interval_seconds * 3):
        raise HTTPException(status_code=503, detail="Auction close worker heartbeat is stale or missing.")
    return {"status": "ok", "last_success": heartbeat.succeeded_at, "processed_count": heartbeat.processed_count}


app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type"], expose_headers=["Retry-After"])
