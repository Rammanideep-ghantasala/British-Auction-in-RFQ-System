from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "british_auction_rfq",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    beat_schedule={
        "close-expired-auctions": {
            "task": "app.tasks.close_expired_auctions",
            "schedule": settings.auction_close_scan_interval_seconds,
        }
    },
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
)
