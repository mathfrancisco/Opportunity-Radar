"""Contract for the Compose CI authentication assets (tests/e2e/auth, compose.ci.yaml)."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from opportunity_radar.presentation.http.auth import (
    AuthConfig,
    AuthenticationError,
    JwksClient,
    JwtVerifier,
)

ROOT = Path(__file__).resolve().parents[2]


def _load_fixtures() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "ci_auth_fixtures", ROOT / "tests" / "e2e" / "auth" / "fixtures.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = _load_fixtures()


@pytest.fixture(scope="module")
def auth_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("ci-auth")
    assert fixtures.main(["init", "--directory", str(directory)]) == 0
    return directory


def _verifier(directory: Path) -> JwtVerifier:
    jwks = (directory / "public" / "jwks.json").read_bytes()
    config = AuthConfig(
        issuer=fixtures.ISSUER,
        jwks_url=f"{fixtures.ISSUER}/.well-known/jwks.json",
        authorized_parties=frozenset({fixtures.ORIGIN}),
        owner_sub="ci-owner-sub",
    )
    return JwtVerifier(config, JwksClient(config.jwks_url, transport=lambda *_: jwks))


def _token(directory: Path, persona: str, case: str = "valid") -> str:
    header = directory / "tokens" / f"{persona}-{case}.header"
    assert fixtures.main(
        [
            "mint",
            "--directory",
            str(directory),
            "--persona",
            persona,
            "--case",
            case,
            "--header-file",
            str(header),
        ]
    ) == 0
    return header.read_text(encoding="utf-8").strip().removeprefix("Authorization: Bearer ")


def test_jwks_is_public_only_and_key_material_stays_out_of_served_dirs(auth_dir: Path) -> None:
    jwks = json.loads((auth_dir / "public" / "jwks.json").read_text(encoding="utf-8"))
    assert len(jwks["keys"]) == 1
    assert not {"d", "p", "q", "dp", "dq", "qi"} & set(jwks["keys"][0])
    served = [path.name for folder in ("public", "tls") for path in (auth_dir / folder).iterdir()]
    assert "private.pem" not in served
    if os.name != "nt":  # POSIX permission bits are not meaningful on Windows
        assert (auth_dir / "jwt" / "private.pem").stat().st_mode & 0o077 == 0


def test_minted_tokens_verify_with_the_production_verifier(auth_dir: Path) -> None:
    verifier = _verifier(auth_dir)

    owner = verifier.verify(_token(auth_dir, "owner"))
    other = verifier.verify(_token(auth_dir, "non-owner"))

    assert (owner.sub, owner.is_owner) == ("ci-owner-sub", True)
    assert (other.sub, other.is_owner) == ("ci-non-owner-sub", False)


@pytest.mark.parametrize("case", ["expired", "wrong-issuer", "wrong-azp", "unknown-kid"])
def test_negative_tokens_are_rejected_by_the_production_verifier(
    auth_dir: Path, case: str
) -> None:
    with pytest.raises(AuthenticationError):
        _verifier(auth_dir).verify(_token(auth_dir, "owner", case))


def test_tool_refuses_non_synthetic_issuer_or_party(auth_dir: Path) -> None:
    header = auth_dir / "tokens" / "refused.header"
    base = [
        "mint",
        "--directory",
        str(auth_dir),
        "--persona",
        "owner",
        "--header-file",
        str(header),
    ]

    assert fixtures.main([*base, "--issuer", "https://clerk.example.com"]) == 2
    assert fixtures.main([*base, "--azp", "https://app.example.com"]) == 2
    assert not header.exists()


def test_tool_refuses_header_files_outside_the_token_directory(auth_dir: Path) -> None:
    outside = auth_dir.parent / "escape.header"
    code = fixtures.main(
        [
            "mint",
            "--directory",
            str(auth_dir),
            "--persona",
            "owner",
            "--header-file",
            str(outside),
        ]
    )
    assert code == 2 and not outside.exists()


def test_each_run_gets_a_fresh_key_and_init_never_overwrites(
    auth_dir: Path, tmp_path: Path
) -> None:
    assert fixtures.main(["init", "--directory", str(auth_dir)]) == 2
    assert fixtures.main(["init", "--directory", str(tmp_path)]) == 0
    first = json.loads((auth_dir / "public" / "jwks.json").read_text(encoding="utf-8"))
    second = json.loads((tmp_path / "public" / "jwks.json").read_text(encoding="utf-8"))
    assert first["keys"][0]["kid"] != second["keys"][0]["kid"]
    assert first["keys"][0]["n"] != second["keys"][0]["n"]


def test_ci_overlay_runs_the_production_factory_with_offline_jwks() -> None:
    text = (ROOT / "compose.ci.yaml").read_text(encoding="utf-8")
    overlay = yaml.safe_load(text)
    api = overlay["services"]["api"]
    worker = overlay["services"]["worker"]

    assert "dev.local_app" not in text
    assert api["command"][:2] == [
        "uvicorn",
        "opportunity_radar.presentation.http.app:create_app",
    ]
    assert "--factory" in api["command"]
    env = api["environment"]
    assert env["CLERK_ISSUER"] == "https://issuer.test"
    assert env["CLERK_JWKS_URL"] == "https://issuer.test/.well-known/jwks.json"
    assert env["CLERK_AUTHORIZED_PARTIES"] == env["FRONTEND_ORIGIN"] == "https://127.0.0.1:8443"
    assert env["CLERK_OWNER_SUB"] == "ci-owner-sub"
    assert env["SSL_CERT_FILE"] == "/auth/public/ca.pem"
    assert worker["environment"]["WORKER_OWNER_SUB"] == "ci-owner-sub"
    assert overlay["services"]["migrate"]["environment"]["OWNER_SUB_BACKFILL"] == "ci-owner-sub"


def test_ci_overlay_never_gives_the_api_the_signing_key_and_binds_loopback_only() -> None:
    services = yaml.safe_load((ROOT / "compose.ci.yaml").read_text(encoding="utf-8"))["services"]
    api_mounts = " ".join(services["api"]["volumes"])
    tls_mounts = " ".join(services["ci-tls"]["volumes"])

    assert "/jwt" not in api_mounts and "private" not in api_mounts
    assert api_mounts.endswith("/public/ca.pem:/auth/public/ca.pem:ro")
    assert "/jwt" not in tls_mounts and "private" not in tls_mounts
    assert services["ci-tls"]["ports"] == ["127.0.0.1:8443:443"]
    assert services["ci-tls"]["networks"]["app_net"]["aliases"] == ["issuer.test"]
    assert services["auth-tools"]["network_mode"] == "none"
    assert "build" not in str(services["ci-tls"])


def test_cloud_and_operational_compose_files_carry_no_ci_auth_assets() -> None:
    for name in ("compose.cloud.yaml", "compose.yaml"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for forbidden in (
            "issuer.test",
            "ci-tls",
            "auth-tools",
            "CI_AUTH_DIR",
            "SSL_CERT_FILE",
            "tests/e2e",
            "fixtures.py",
            "ca.pem",
            "dev.local_app",
        ):
            assert forbidden not in text, (name, forbidden)


def test_workflow_routes_private_requests_through_the_wrapper_and_cleans_up() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["e2e"]["steps"]
    names = [step["name"] for step in steps]

    assert names.index("Generate the run's ephemeral JWT key, JWKS and TLS CA") < names.index(
        "Start application"
    )
    assert names.index("Verify the authentication boundary before seeding") < names.index(
        "Import and expose the researched company catalog"
    )
    for step in steps:
        run = step.get("run", "")
        assert "127.0.0.1:3000/api" not in run, step["name"]
    cleanup = next(step for step in steps if step["name"].startswith("Remove the ephemeral"))
    assert cleanup["if"] == "always()"
    uploads = [step for step in steps if "upload-artifact" in step.get("uses", "")]
    for upload in uploads:
        assert "ci-auth" not in upload["with"]["path"]
        assert "tokens" not in upload["with"]["path"]
    browser = next(step for step in steps if step["name"].startswith("Run the offline browser"))
    assert browser["env"]["E2E_BASE_URL"] == "https://127.0.0.1:8443"
    assert "--project=offline-no-clerk-config" in browser["run"]
    assert "requires-real-clerk" not in browser["run"]
