FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations

CMD ["sh", "-c", "python -m app.migrate && if [ \"$RUN_CELERY_IN_WEB\" = \"true\" ]; then celery -A app.celery_app:celery_app worker -B -l info & fi && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
