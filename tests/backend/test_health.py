from fastapi.testclient import TestClient

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.health import DependencyHealth, ai_health
from opportunity_radar.presentation.http.app import create_app


def settings(**overrides: object) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://test:test@localhost/test", **overrides
    )


def test_live_health_does_not_require_dependencies() -> None:
    response = TestClient(create_app(settings())).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_is_healthy_when_database_is_current(monkeypatch) -> None:
    monkeypatch.setattr(
        "opportunity_radar.presentation.http.routes.ready_health",
        lambda _: DependencyHealth("healthy"),
    )

    response = TestClient(create_app(settings())).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "opportunity_radar.presentation.http.routes.ready_health",
        lambda _: DependencyHealth("unhealthy"),
    )

    response = TestClient(create_app(settings())).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_ai_degradation_does_not_make_api_unready(monkeypatch) -> None:
    monkeypatch.setattr(
        "opportunity_radar.presentation.http.routes.ready_health",
        lambda _: DependencyHealth("healthy"),
    )
    monkeypatch.setattr(
        "opportunity_radar.presentation.http.routes.ai_health",
        lambda _: DependencyHealth("degraded", "ai disabled"),
    )

    response = TestClient(create_app(settings())).get("/health")

    assert response.status_code == 200
    assert response.json()["ai"]["status"] == "degraded"


def test_ai_health_never_makes_a_network_call_and_is_degraded_when_off() -> None:
    result = ai_health(settings(ai_enabled=False))

    assert result == DependencyHealth("degraded", "ai disabled")


def test_ai_health_is_degraded_when_enabled_without_a_key() -> None:
    result = ai_health(settings(ai_enabled=True, groq_api_key=""))

    assert result == DependencyHealth("degraded", "groq api key missing")


def test_ai_health_is_healthy_when_enabled_with_a_key() -> None:
    result = ai_health(settings(ai_enabled=True, groq_api_key="a-real-key"))

    assert result == DependencyHealth("healthy")
