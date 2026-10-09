"""Card F50-10: the API cancels a statement past `API_STATEMENT_TIMEOUT_MS`; the worker does not."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import (
    create_api_engine,
    create_database_engine,
    open_session,
)
from opportunity_radar.presentation.http.app import create_development_app as create_app
from opportunity_radar.presentation.http.dependencies import get_session

integration = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _api_session(timeout_ms: int) -> Iterator[Session]:
    return open_session(os.environ["DATABASE_URL"], statement_timeout_ms=timeout_ms)


def test_setting_defaults_to_fifteen_seconds_and_rejects_a_negative_value() -> None:
    assert Settings(database_url="postgresql+psycopg://u:p@h/db").api_statement_timeout_ms == 15000
    assert Settings(database_url="postgresql+psycopg://u:p@h/db", api_statement_timeout_ms=0)
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://u:p@h/db", api_statement_timeout_ms=-1)


@pytest.mark.integration
@integration
def test_api_session_cancels_a_statement_past_the_timeout() -> None:
    (session,) = list(_api_session(200))
    try:
        assert session.scalar(text("SHOW statement_timeout")) == "200ms"
        with pytest.raises(OperationalError) as raised:
            session.execute(text("SELECT pg_sleep(5)"))
        assert getattr(raised.value.orig, "sqlstate", None) == "57014"
    finally:
        session.close()


@pytest.mark.integration
@integration
def test_zero_disables_the_timeout_and_the_worker_engine_never_has_one() -> None:
    url = os.environ["DATABASE_URL"]
    assert create_api_engine(url, 0) is create_database_engine(url)
    for engine in (create_api_engine(url, 0), create_database_engine(url)):
        with Session(engine) as session:
            assert session.scalar(text("SHOW statement_timeout")) == "0"
            # Longer than the API timeout used above: not cancelled.
            session.execute(text("SELECT pg_sleep(0.4)"))


@pytest.mark.integration
@integration
def test_http_answers_503_when_a_query_is_cancelled() -> None:
    settings = Settings(database_url=os.environ["DATABASE_URL"], api_statement_timeout_ms=200)
    app = create_app(settings)

    @app.get("/_slow")
    def slow(session: Session = Depends(get_session)) -> dict[str, bool]:
        session.execute(text("SELECT pg_sleep(5)"))
        return {"ok": True}

    response = TestClient(app, raise_server_exceptions=False).get("/_slow")

    assert response.status_code == 503
    assert "too long" in response.json()["detail"]
    assert response.headers["Retry-After"]


def test_other_database_errors_propagate_as_exceptions() -> None:
    """Non-timeout DBAPIErrors are not converted by the handler; they propagate untouched."""
    app = create_app(Settings(database_url="postgresql+psycopg://u:p@h/db"))

    @app.get("/_broken")
    def broken() -> None:
        raise DBAPIError("SELECT 1", {}, Exception("boom"))

    # With raise_server_exceptions=True, the original exception is raised.
    with pytest.raises(DBAPIError):
        TestClient(app, raise_server_exceptions=True).get("/_broken")

    # With raise_server_exceptions=False, Starlette's default exception handler
    # returns a 500 plain text response (not JSON).
    response = TestClient(app, raise_server_exceptions=False).get("/_broken")
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
