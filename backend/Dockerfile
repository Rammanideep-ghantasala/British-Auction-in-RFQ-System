FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
RUN addgroup --system app && adduser --system --ingroup app app

COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
RUN chown -R app:app /app

USER app

CMD ["python", "-m", "app.run"]
