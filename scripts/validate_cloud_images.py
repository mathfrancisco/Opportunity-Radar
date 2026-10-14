"""Validate immutable cloud image inputs against saved OCI manifest JSON.

This is deliberately offline: CI or a release operator supplies manifests obtained
from the published digests, and this command checks them before Compose can run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

_DIGEST_REFERENCE = re.compile(r"^[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}$")
_ROLES = ("api", "worker", "proxy")


def _manifest_path(value: str) -> tuple[str, Path]:
    role, separator, path = value.partition("=")
    if separator != "=" or role not in _ROLES or not path:
        raise argparse.ArgumentTypeError("--manifest must be ROLE=PATH for api, worker, or proxy")
    return role, Path(path)


def _has_linux_arm64(document: Any) -> bool:
    manifests = document.get("manifests", []) if isinstance(document, dict) else []
    return any(
        entry.get("platform", {}).get("os") == "linux"
        and entry.get("platform", {}).get("architecture") == "arm64"
        for entry in manifests
        if isinstance(entry, dict)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-image")
    parser.add_argument("--worker-image")
    parser.add_argument("--proxy-image")
    parser.add_argument("--role", choices=_ROLES)
    parser.add_argument("--image")
    parser.add_argument("--manifest", action="append", default=[])
    args = parser.parse_args(argv)

    if args.role:
        if not args.image:
            parser.error("--role requires --image")
        if len(args.manifest) != 1:
            parser.error("--role requires exactly one --manifest PATH")
        images = {args.role: args.image}
        manifests = {args.role: Path(args.manifest[0])}
    else:
        images = {
            "api": args.api_image,
            "worker": args.worker_image,
            "proxy": args.proxy_image,
        }
        missing = [role for role, image in images.items() if not image]
        if missing:
            parser.error("legacy mode requires --api-image, --worker-image, and --proxy-image")
        try:
            manifest_pairs = [_manifest_path(value) for value in args.manifest]
        except argparse.ArgumentTypeError as error:
            parser.error(str(error))
        manifests = dict(manifest_pairs)
    errors: list[str] = []
    for role, image in images.items():
        if not _DIGEST_REFERENCE.fullmatch(image):
            errors.append(
                f"{role} image must be a lowercase immutable "
                "image@sha256:<64 hex> reference"
            )
        path = manifests.get(role)
        if path is None:
            errors.append(f"{role} requires an offline --manifest {role}=PATH")
            continue
        try:
            raw_manifest = path.read_bytes()
        except OSError as error:
            errors.append(f"{role} manifest cannot be read: {error}")
            continue
        digest = image.partition("@sha256:")[2]
        actual_digest = hashlib.sha256(raw_manifest).hexdigest()
        if actual_digest != digest:
            errors.append(f"{role} manifest sha256 does not match its image digest")
            continue
        try:
            document = json.loads(raw_manifest)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"{role} manifest is not valid JSON: {error}")
            continue
        if not _has_linux_arm64(document):
            errors.append(f"{role} manifest lacks a linux/arm64 platform")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("cloud image preflight passed: immutable digests with linux/arm64 manifests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
