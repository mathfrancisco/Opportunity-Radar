from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opportunity_radar.platform.ai.config import AIState, ai_status
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
    """Never makes a network call: healthy = AI on and a usable provider key present.

    Degraded when the AI is turned off or no provider has a key (detail: "ai disabled"
    or "no ai provider key"). A network probe here would spend quota on every health
    check, which is not what a liveness check is for.
    """
    state = ai_status(settings)
    if state is AIState.DISABLED:
        return DependencyHealth("degraded", "ai disabled")
    if state is AIState.BLOCKED_BY_CONFIGURATION:
        return DependencyHealth("degraded", "no ai provider key")
    return DependencyHealth("healthy")


def ready_health(
    settings: Settings,
    engine_factory: Callable[[str], Engine] = create_database_engine,
) -> DependencyHealth:
    return database_health(engine_factory(settings.database_url))
