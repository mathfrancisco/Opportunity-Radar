from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine


@dataclass(frozen=True)
class DependencyHealth:
    status: str
    detail: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def database_health(engine: Engine) -> DependencyHealth:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        candidates = (
            Path.cwd() / "alembic.ini",
            Path(__file__).resolve().parents[3] / "alembic.ini",
        )
        alembic_ini = next((path for path in candidates if path.is_file()), candidates[0])
        expected_revision = ScriptDirectory.from_config(Config(str(alembic_ini))).get_current_head()
        if revision != expected_revision:
            return DependencyHealth("unhealthy", "database migration is not at head")
    except Exception:
        return DependencyHealth("unhealthy", "database unavailable or migration missing")
    return DependencyHealth("healthy")


def ai_health(settings: Settings) -> DependencyHealth:
    """Never makes a network call: healthy = AI on and a key present.

    Degraded when the AI is turned off or no key is configured (detail: "ai disabled"
    or "groq api key missing"). A network probe here would spend Groq quota on every
    health check, which is not what a liveness check is for.
    """
    if not settings.ai_enabled:
        return DependencyHealth("degraded", "ai disabled")
    if not settings.groq_api_key.get_secret_value():
        return DependencyHealth("degraded", "groq api key missing")
    return DependencyHealth("healthy")


def ready_health(
    settings: Settings,
    engine_factory: Callable[[str], Engine] = create_database_engine,
) -> DependencyHealth:
    return database_health(engine_factory(settings.database_url))
