FROM python:3.12.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
COPY apps ./apps
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps .
RUN mkdir -p /app/data/exports /app/data/backups && chown -R app:app /app/data

USER app

CMD ["python", "-m", "opportunity_radar.worker"]
