from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from opportunity_radar.acquisition import models as acquisition_models  # noqa: F401
from opportunity_radar.companies import models as company_models  # noqa: F401
from opportunity_radar.dashboard import models as dashboard_models  # noqa: F401
from opportunity_radar.matching import models as matching_models  # noqa: F401
from opportunity_radar.operations import models as operation_models  # noqa: F401
from opportunity_radar.opportunities import embedding_models  # noqa: F401
from opportunity_radar.opportunities import models as opportunity_models  # noqa: F401
from opportunity_radar.opportunities import suggestions as suggestion_models  # noqa: F401
from opportunity_radar.pipeline import models as pipeline_models  # noqa: F401
from opportunity_radar.platform.database import Base
from opportunity_radar.profile import models as profile_models  # noqa: F401

config = context.config
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

#: `platform.ai_quota_usage` and `platform.ai_call_record` are plain `sa.Table` objects on
#: their own private `MetaData`, not on `Base.metadata` (see
#: `opportunity_radar.platform.ai.quota` / `.telemetry`) — a deliberate choice to keep this
#: hot-path counter/telemetry storage out of the ORM. Autogenerate only ever sees
#: `Base.metadata`, so without this filter it reads their absence there as "table removed"
#: and proposes dropping tables that were never meant to be ORM-managed.
_UNMANAGED_TABLES = {
    ("platform", "ai_quota_usage"),
    ("platform", "ai_call_record"),
    ("platform", "ai_operation_record"),
}

#: `ix_opportunity_embedding_hnsw` is raw `op.execute("CREATE INDEX ... USING hnsw ...")`
#: (migration 20260925_0024): pgvector's HNSW access method and operator class
#: (`vector_cosine_ops`) have no portable `sa.Index(...)` form, and the custom `Vector`
#: column type it indexes can't be reflected and compared by autogenerate anyway ("Couldn't
#: determine database type for column 'opportunity_embedding.embedding'"). Declaring it on
#: the model would not make the comparison work; excluding it is what a raw-SQL-managed
#: index means.
_UNMANAGED_INDEXES = {"ix_opportunity_embedding_hnsw"}


def include_object(
    object_: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    del compare_to
    if not reflected:
        return True
    if type_ == "table" and (getattr(object_, "schema", None), name) in _UNMANAGED_TABLES:
        return False
    if type_ == "index" and name in _UNMANAGED_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Every app table lives in a dedicated schema (acquisition, matching, ...), never
        # `public`. Without this, autogenerate (and `alembic check`) only reflects `public`
        # — which is empty — so it reports the whole schema as "added" on an already
        # fully-migrated database (F20 sanity pass, docs/44-roadmap-fase-20 §5).
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
