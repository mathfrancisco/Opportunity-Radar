import os
import random

import pytest


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


@pytest.fixture(autouse=True)
def _isolate_from_operator_ai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith(_OPERATOR_ENV_PREFIXES):
            monkeypatch.delenv(name)
