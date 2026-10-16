import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "validate_cloud_images.py"
FIXTURES = ROOT / "tests" / "fixtures" / "cloud_images"
MULTIARCH_FIXTURE = FIXTURES / "multiarch-index.json"
AMD64_FIXTURE = FIXTURES / "amd64-only-index.json"


def _image_ref(role: str, fixture_path: Path) -> str:
    digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    return f"registry.example.test/opportunity-radar-{role}@sha256:{digest}"


def _manifest(tmp_path: Path, architecture: str = "arm64") -> tuple[Path, str]:
    path = tmp_path / "manifest.json"
    raw = json.dumps(
        {
            "manifests": [
                {"platform": {"os": "linux", "architecture": architecture}},
            ]
        },
        separators=(",", ":"),
    ).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _run(*arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PREFLIGHT), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=dict(os.environ) if env is None else env,
    )


def test_single_role_preflight_accepts_matching_arm64_manifest(tmp_path: Path) -> None:
    manifest, digest = _manifest(tmp_path)

    result = _run(
        "--role",
        "api",
        "--image",
        f"registry.example.test/opportunity-radar-api@sha256:{digest}",
        "--manifest",
        str(manifest),
    )

    assert result.returncode == 0, result.stderr


def test_single_role_preflight_rejects_missing_arm64(tmp_path: Path) -> None:
    manifest, digest = _manifest(tmp_path, architecture="amd64")

    result = _run(
        "--role",
        "worker",
        "--image",
        f"registry.example.test/opportunity-radar-worker@sha256:{digest}",
        "--manifest",
        str(manifest),
    )

    assert result.returncode != 0
    assert "lacks a linux/arm64 platform" in result.stderr


def test_single_role_preflight_accepts_requested_amd64_platform() -> None:
    result = _run(
        "--platform",
        "linux/amd64",
        "--role",
        "worker",
        "--image",
        _image_ref("worker", AMD64_FIXTURE),
        "--manifest",
        str(AMD64_FIXTURE),
    )

    assert result.returncode == 0, result.stderr
    assert "linux/amd64 manifests" in result.stdout


def test_preflight_rejects_unsupported_platform() -> None:
    result = _run("--platform", "linux/s390x")

    assert result.returncode != 0
    assert "invalid choice" in result.stderr


def test_single_role_preflight_rejects_digest_mismatch(tmp_path: Path) -> None:
    manifest, _ = _manifest(tmp_path)

    result = _run(
        "--role",
        "proxy",
        "--image",
        "registry.example.test/opportunity-radar-proxy@sha256:" + "0" * 64,
        "--manifest",
        str(manifest),
    )

    assert result.returncode != 0
    assert "manifest sha256 does not match its image digest" in result.stderr


def test_single_role_preflight_rejects_mutable_tag(tmp_path: Path) -> None:
    manifest, _ = _manifest(tmp_path)

    result = _run(
        "--role",
        "api",
        "--image",
        "registry.example.test/opportunity-radar-api:latest",
        "--manifest",
        str(manifest),
    )

    assert result.returncode != 0
    assert "immutable" in result.stderr


def test_single_role_preflight_rejects_unknown_role(tmp_path: Path) -> None:
    manifest, digest = _manifest(tmp_path)

    result = _run(
        "--role",
        "frontend",
        "--image",
        f"registry.example.test/opportunity-radar-frontend@sha256:{digest}",
        "--manifest",
        str(manifest),
    )

    assert result.returncode != 0
    assert "invalid choice" in result.stderr


@pytest.mark.parametrize("role", ["api", "worker", "proxy"])
def test_role_mode_accepts_multiarch_fixture(role: str) -> None:
    result = _run(
        "--role",
        role,
        "--image",
        _image_ref(role, MULTIARCH_FIXTURE),
        "--manifest",
        str(MULTIARCH_FIXTURE),
    )

    assert result.returncode == 0, result.stderr
    assert "cloud image preflight passed" in result.stdout


@pytest.mark.parametrize("role", ["api", "worker", "proxy"])
def test_role_mode_rejects_amd64_only_fixture(role: str) -> None:
    result = _run(
        "--role",
        role,
        "--image",
        _image_ref(role, AMD64_FIXTURE),
        "--manifest",
        str(AMD64_FIXTURE),
    )

    assert result.returncode == 1
    assert f"{role} manifest lacks a linux/arm64 platform" in result.stderr


def test_legacy_mode_accepts_all_multiarch_fixtures() -> None:
    result = _run(
        "--api-image",
        _image_ref("api", MULTIARCH_FIXTURE),
        "--worker-image",
        _image_ref("worker", MULTIARCH_FIXTURE),
        "--proxy-image",
        _image_ref("proxy", MULTIARCH_FIXTURE),
        "--manifest",
        f"api={MULTIARCH_FIXTURE}",
        "--manifest",
        f"worker={MULTIARCH_FIXTURE}",
        "--manifest",
        f"proxy={MULTIARCH_FIXTURE}",
    )

    assert result.returncode == 0, result.stderr
    assert "cloud image preflight passed" in result.stdout


def test_legacy_mode_accepts_all_amd64_fixtures_when_requested() -> None:
    result = _run(
        "--platform",
        "linux/amd64",
        "--api-image",
        _image_ref("api", AMD64_FIXTURE),
        "--worker-image",
        _image_ref("worker", AMD64_FIXTURE),
        "--proxy-image",
        _image_ref("proxy", AMD64_FIXTURE),
        "--manifest",
        f"api={AMD64_FIXTURE}",
        "--manifest",
        f"worker={AMD64_FIXTURE}",
        "--manifest",
        f"proxy={AMD64_FIXTURE}",
    )

    assert result.returncode == 0, result.stderr
    assert "linux/amd64 manifests" in result.stdout


@pytest.mark.parametrize("failing_role", ["api", "worker", "proxy"])
def test_legacy_mode_rejects_single_amd64_only_role(failing_role: str) -> None:
    args: list[str] = []
    for role in ("api", "worker", "proxy"):
        fixture = AMD64_FIXTURE if role == failing_role else MULTIARCH_FIXTURE
        args.extend([f"--{role}-image", _image_ref(role, fixture)])
        args.extend(["--manifest", f"{role}={fixture}"])

    result = _run(*args)

    assert result.returncode == 1
    assert f"{failing_role} manifest lacks a linux/arm64 platform" in result.stderr
    for role in ("api", "worker", "proxy"):
        if role != failing_role:
            assert f"{role} manifest lacks a linux/arm64 platform" not in result.stderr


def test_legacy_mode_rejects_missing_manifest() -> None:
    result = _run(
        "--api-image",
        _image_ref("api", MULTIARCH_FIXTURE),
        "--worker-image",
        _image_ref("worker", MULTIARCH_FIXTURE),
        "--proxy-image",
        _image_ref("proxy", MULTIARCH_FIXTURE),
        "--manifest",
        f"api={MULTIARCH_FIXTURE}",
        "--manifest",
        f"worker={MULTIARCH_FIXTURE}",
    )

    assert result.returncode == 1
    assert "proxy requires an offline --manifest proxy=PATH" in result.stderr


def test_preflight_rejects_bytes_mutated_after_digest_computed(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "mutated-index.json"
    fixture_copy.write_bytes(MULTIARCH_FIXTURE.read_bytes())
    image = _image_ref("api", fixture_copy)
    fixture_copy.write_bytes(fixture_copy.read_bytes() + b"\n")

    result = _run(
        "--role",
        "api",
        "--image",
        image,
        "--manifest",
        str(fixture_copy),
    )

    assert result.returncode == 1
    assert "api manifest sha256 does not match its image digest" in result.stderr


def test_preflight_rejects_windows_arm64_platform(tmp_path: Path) -> None:
    path = tmp_path / "windows-arm64-index.json"
    raw = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": "sha256:" + "0" * 64,
                    "size": 1024,
                    "platform": {"os": "windows", "architecture": "arm64"},
                }
            ],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    path.write_bytes(raw)
    image = _image_ref("api", path)

    result = _run(
        "--role",
        "api",
        "--image",
        image,
        "--manifest",
        str(path),
    )

    assert result.returncode == 1
    assert "api manifest lacks a linux/arm64 platform" in result.stderr


def test_preflight_results_identical_with_tenancy_ready_unset_and_false() -> None:
    base_env = {k: v for k, v in os.environ.items() if k != "TENANCY_OWNER_API_READY"}
    env_unset = dict(base_env)
    env_false = {**base_env, "TENANCY_OWNER_API_READY": "false"}

    pos_unset = _run(
        "--role",
        "api",
        "--image",
        _image_ref("api", MULTIARCH_FIXTURE),
        "--manifest",
        str(MULTIARCH_FIXTURE),
        env=env_unset,
    )
    pos_false = _run(
        "--role",
        "api",
        "--image",
        _image_ref("api", MULTIARCH_FIXTURE),
        "--manifest",
        str(MULTIARCH_FIXTURE),
        env=env_false,
    )

    assert pos_unset.returncode == pos_false.returncode == 0
    assert pos_unset.stdout == pos_false.stdout
    assert pos_unset.stderr == pos_false.stderr

    neg_unset = _run(
        "--role",
        "worker",
        "--image",
        _image_ref("worker", AMD64_FIXTURE),
        "--manifest",
        str(AMD64_FIXTURE),
        env=env_unset,
    )
    neg_false = _run(
        "--role",
        "worker",
        "--image",
        _image_ref("worker", AMD64_FIXTURE),
        "--manifest",
        str(AMD64_FIXTURE),
        env=env_false,
    )

    assert neg_unset.returncode == neg_false.returncode == 1
    assert neg_unset.stdout == neg_false.stdout
    assert neg_unset.stderr == neg_false.stderr
