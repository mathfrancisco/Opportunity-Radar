FROM python:3.12.8-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
COPY apps ./apps
COPY scripts ./scripts
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps .

FROM base AS test

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests

USER app

CMD ["uvicorn", "opportunity_radar.presentation.http.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS runtime

USER app

CMD ["uvicorn", "opportunity_radar.presentation.http.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
