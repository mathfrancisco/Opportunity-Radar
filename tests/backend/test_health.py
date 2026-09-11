from io import BytesIO

from fastapi.testclient import TestClient

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.health import DependencyHealth, ollama_health
from opportunity_radar.presentation.http.app import create_app


def settings() -> Settings:
    return Settings(database_url="postgresql+psycopg://test:test@localhost/test")


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


def test_ollama_degradation_does_not_make_api_unready(monkeypatch) -> None:
    monkeypatch.setattr(
        "opportunity_radar.presentation.http.routes.ready_health",
        lambda _: DependencyHealth("healthy"),
    )
    monkeypatch.setattr(
        "opportunity_radar.presentation.http.routes.ollama_health",
        lambda _: DependencyHealth("degraded", "ollama unavailable"),
    )

    response = TestClient(create_app(settings())).get("/health")

    assert response.status_code == 200
    assert response.json()["ollama"]["status"] == "degraded"


def test_ollama_is_degraded_when_analysis_model_is_missing() -> None:
    response = BytesIO(b'{"models": []}')
    response.status = 200  # type: ignore[attr-defined]

    result = ollama_health(settings(), opener=lambda *_, **__: response)

    assert result == DependencyHealth("degraded", "ollama analysis model is not installed")
