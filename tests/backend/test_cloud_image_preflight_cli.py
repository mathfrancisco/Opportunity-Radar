import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "validate_cloud_images.py"


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


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PREFLIGHT), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
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
