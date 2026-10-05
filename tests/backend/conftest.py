import os
import random

import pytest
from sqlalchemy.engine import make_url


#: F20 sanity pass (docs/44-roadmap-fase-20/validacao-pendente.md §5): reproduce the
#: order-dependent failures with a seeded shuffle when neither pytest-randomly nor
#: pytest-random-order is installed. Temporary validation aid — set RANDOM_ORDER_SEED to
#: enable; unset (the default) leaves collection order untouched.
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    del config
    seed = os.environ.get("RANDOM_ORDER_SEED")
    if seed is None:
        return
    random.Random(int(seed)).shuffle(items)


#: compose passes the operator's AI and Tavily settings into every container, including the
#: one tests run in. Tests must see defaults, never the real key or AI_ENABLED=true.
_OPERATOR_ENV_PREFIXES = ("AI_", "GROQ_", "TAVILY_")
_DATABASE_INTEGRATION_MARKER = "DATABASE_INTEGRATION_ISOLATED"


def _validate_database_integration_environment() -> None:
    """Refuse destructive integration tests unless their database is explicit and dedicated."""
    if os.environ.get("RUN_DATABASE_INTEGRATION") != "1":
        return

    if os.environ.get(_DATABASE_INTEGRATION_MARKER) != "1":
        raise pytest.UsageError(
            "RUN_DATABASE_INTEGRATION=1 requires DATABASE_INTEGRATION_ISOLATED=1"
        )

    try:
        database = make_url(os.environ["DATABASE_URL"]).database
    except (KeyError, ValueError) as error:
        raise pytest.UsageError(
            "RUN_DATABASE_INTEGRATION=1 requires a valid DATABASE_URL"
        ) from error

    if not database or not database.endswith("_test"):
        raise pytest.UsageError(
            "RUN_DATABASE_INTEGRATION=1 requires a dedicated DATABASE_URL database ending in _test"
        )


def pytest_sessionstart(session: pytest.Session) -> None:
    del session
    _validate_database_integration_environment()


@pytest.fixture(autouse=True)
def _isolate_from_operator_ai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith(_OPERATOR_ENV_PREFIXES):
            monkeypatch.delenv(name)
