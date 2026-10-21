import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from opportunity_radar.platform.config import Settings
from opportunity_radar.presentation.http.app import create_app, create_development_app

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "validate_cloud_images.py"


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
    assert "PUBLIC_HOSTNAME" in services["proxy"]["environment"]
    for service in services.values():
        assert "@sha256:" in service["image"]
    assert "volumes" not in cloud


def test_cloud_proxy_template_rejects_foreign_host_and_never_redirects_it() -> None:
    proxy = (ROOT / "docker" / "proxy" / "nginx.conf.template").read_text(encoding="utf-8")

    assert "listen 80 default_server" in proxy
    assert "listen 443 ssl default_server" in proxy
    assert proxy.count("return 444;") == 2
    assert "server_name ${PUBLIC_HOSTNAME};" in proxy
    assert "https://${PUBLIC_HOSTNAME}$request_uri" in proxy
    assert "https://$host" not in proxy
    assert "proxy_set_header Host ${PUBLIC_HOSTNAME};" in proxy


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


def test_production_cors_requires_https_but_development_allows_local_http() -> None:
    development = create_development_app(_settings(frontend_origin="http://localhost:3000"))
    assert development is not None

    try:
        create_app(
            _settings(
                frontend_origin="http://localhost:3000",
                clerk_issuer="https://issuer.example.test",
                clerk_jwks_url="https://issuer.example.test/jwks",
                clerk_authorized_parties="https://app.example.test",
                clerk_owner_sub="owner_synthetic",
            )
        )
    except RuntimeError as error:
        assert "https" in str(error)
    else:
        raise AssertionError("production accepted an HTTP FRONTEND_ORIGIN")


def test_image_preflight_requires_digests_and_arm64_manifests(tmp_path: Path) -> None:
    images: dict[str, str] = {}
    manifests: dict[str, Path] = {}
    for role in ("api", "worker", "proxy"):
        manifest = tmp_path / f"{role}.json"
        raw_manifest = json.dumps(
            {
                "manifests": [
                    {
                        "digest": f"sha256:{role}",
                        "platform": {"os": "linux", "architecture": "arm64"},
                    }
                ]
            },
            separators=(",", ":"),
        ).encode()
        manifest.write_bytes(raw_manifest)
        digest = hashlib.sha256(raw_manifest).hexdigest()
        images[role] = f"registry.example.test/opportunity-radar/{role}@sha256:{digest}"
        manifests[role] = manifest
    command = [
        sys.executable,
        str(PREFLIGHT),
        "--api-image",
        images["api"],
        "--worker-image",
        images["worker"],
        "--proxy-image",
        images["proxy"],
        "--manifest",
        f"api={manifests['api']}",
        "--manifest",
        f"worker={manifests['worker']}",
        "--manifest",
        f"proxy={manifests['proxy']}",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr

    cross_image = subprocess.run(
        [
            *command[:11],
            f"worker={manifests['api']}",
            *command[12:],
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert cross_image.returncode != 0
    assert "manifest sha256 does not match its image digest" in cross_image.stderr

    reused_manifest = subprocess.run(
        [
            *command[:11],
            f"worker={manifests['api']}",
            "--manifest",
            f"proxy={manifests['api']}",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert reused_manifest.returncode != 0
    assert reused_manifest.stderr.count("manifest sha256 does not match its image digest") == 2

    rejected = subprocess.run(
        [*command[:3], "registry.example.test/opportunity-radar/api:mutable", *command[4:]],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "@sha256" in rejected.stderr
