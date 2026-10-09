from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from opportunity_radar.platform.config import Settings
from opportunity_radar.presentation.http.app import create_development_app

ROOT = Path(__file__).resolve().parents[2]


def _settings(**overrides: object) -> Settings:
    return Settings(database_url="postgresql+psycopg://test:test@localhost/test", **overrides)


def test_cloud_compose_only_exposes_proxy_and_uses_finite_worker() -> None:
    cloud = yaml.safe_load((ROOT / "compose.cloud.yaml").read_text(encoding="utf-8"))
    services = cloud["services"]

    assert set(services) == {"migrate", "api", "worker", "proxy"}
    assert "ports" not in services["api"]
    assert services["api"]["healthcheck"]["test"][-1].endswith("/health/live', timeout=2)")
    assert services["worker"]["restart"] == "no"
    assert services["worker"]["command"][:3] == [
        "python",
        "scripts/run_pipeline_once.py",
        "--deadline-seconds",
    ]
    assert services["proxy"]["ports"] == ["80:80", "443:443"]
    assert "volumes" not in cloud


def test_cors_allows_only_the_configured_origin_and_headers() -> None:
    client = TestClient(create_development_app(_settings(frontend_origin="https://app.example.test")))

    allowed = client.options(
        "/health/live",
        headers={
            "Origin": "https://app.example.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, X-Correlation-ID",
        },
    )
    denied = client.options(
        "/health/live",
        headers={
            "Origin": "https://hostile.example.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://app.example.test"
    assert "authorization" in allowed.headers["access-control-allow-headers"].lower()
    assert "*" not in allowed.headers["access-control-allow-methods"]
    assert "access-control-allow-origin" not in denied.headers


def test_cors_rejects_wildcard_and_url_path() -> None:
    for origin in ("*", "https://app.example.test/path"):
        try:
            create_development_app(_settings(frontend_origin=origin))
        except RuntimeError as error:
            assert "FRONTEND_ORIGIN" in str(error)
        else:
            raise AssertionError("invalid frontend origin was accepted")
