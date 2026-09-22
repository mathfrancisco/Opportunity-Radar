FROM python:3.12.8-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# pg_dump and pg_restore back `make backup` and `make restore-check`. The client has to
# match the server major version, so it comes from PGDG rather than from Debian's older
# default package.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install --no-install-recommends -y postgresql-client-17 \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
COPY apps ./apps
COPY scripts ./scripts
# The catalog importer defaults to these two audited inputs at runtime.
COPY docs/pesquisas/auditoria-186-empresas.md docs/pesquisas/empresas-adicionais.md ./docs/pesquisas/
COPY prompts ./prompts
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps .
RUN mkdir -p /app/data/backups && chown -R app:app /app/data

FROM base AS test

COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests

USER app

CMD ["uvicorn", "opportunity_radar.presentation.http.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS runtime

USER app

CMD ["uvicorn", "opportunity_radar.presentation.http.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
