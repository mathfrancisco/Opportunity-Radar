import os

import pytest

#: compose passes the operator's AI and Tavily settings into every container, including the
#: one tests run in. Tests must see defaults, never the real key or AI_ENABLED=true.
_OPERATOR_ENV_PREFIXES = ("AI_", "GROQ_", "TAVILY_")


@pytest.fixture(autouse=True)
def _isolate_from_operator_ai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith(_OPERATOR_ENV_PREFIXES):
            monkeypatch.delenv(name)
