from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from json import load
from pathlib import Path
from urllib.request import urlopen

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


def ollama_health(settings: Settings, opener: Callable = urlopen) -> DependencyHealth:
    try:
        with opener(
            f"{settings.ollama_base_url.rstrip('/')}/api/tags",
            timeout=settings.ollama_health_timeout_seconds,
        ) as response:
            if response.status != 200:
                return DependencyHealth("degraded", "ollama returned a non-success status")
            models = load(response).get("models", [])
            available_models = {model.get("name") for model in models if isinstance(model, dict)}
            if settings.ollama_model_analysis not in available_models:
                return DependencyHealth("degraded", "ollama analysis model is not installed")
    except Exception:
        return DependencyHealth("degraded", "ollama unavailable")
    return DependencyHealth("healthy")


def ready_health(
    settings: Settings,
    engine_factory: Callable[[str], Engine] = create_database_engine,
) -> DependencyHealth:
    return database_health(engine_factory(settings.database_url))
