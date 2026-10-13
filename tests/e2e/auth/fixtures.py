"""Ephemeral offline authentication fixtures for the Compose CI stack.

Test-only. The production API verifies RS256 JWTs against a JWKS fetched over HTTPS; this
tool provides the pieces of that path for CI without any real identity provider:

* ``init``  generates, per run, an RSA-2048 JWT signing key (random ``kid``), the public
  ``jwks.json`` (no private fields) and a throwaway TLS CA plus a server certificate whose
  SANs are ``issuer.test`` and ``127.0.0.1``.
* ``mint``  writes an ``Authorization: Bearer`` header file (and an ``.exp`` sidecar with the
  epoch expiry) for a synthetic persona, or for one of the negative cases.

The issuer and the authorized party are fixed synthetic values; the tool refuses any other.
It prints file paths only, never key material or tokens. It runs in a container with no
network and the fixture directory mounted from outside the checkout.

Layout under DIR (the JWT private key is only ever read by this tool):

    jwt/private.pem      0600  JWT signing key
    public/jwks.json           public key set served by the TLS service
    public/ca.pem              CA certificate the API and clients trust
    tls/server.pem, server.key server certificate and key (TLS service only)
    tokens/NAME.header         Authorization header file; NAME.exp is its epoch expiry
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import ipaddress
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ISSUER = "https://issuer.test"
ORIGIN = "https://127.0.0.1:8443"
WRONG_ISSUER = "https://wrong-issuer.test"
WRONG_ORIGIN = "https://wrong-party.test"
ALLOWED_ISSUERS = frozenset({ISSUER, WRONG_ISSUER})
ALLOWED_ORIGINS = frozenset({ORIGIN, WRONG_ORIGIN})
SUBJECTS = {"owner": "ci-owner-sub", "non-owner": "ci-non-owner-sub"}
CASES = ("valid", "expired", "wrong-issuer", "wrong-azp", "unknown-kid")
LIFETIME_SECONDS = 600


class FixtureError(Exception):
    """A refused or invalid request; reported without a traceback."""


def _b64url(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _write(path: Path, data: bytes | str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode() if isinstance(data, str) else data
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    os.chmod(path, mode)


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _key_usage(**enabled: bool) -> x509.KeyUsage:
    flags = {
        "digital_signature": False,
        "content_commitment": False,
        "key_encipherment": False,
        "data_encipherment": False,
        "key_agreement": False,
        "key_cert_sign": False,
        "crl_sign": False,
        "encipher_only": False,
        "decipher_only": False,
    }
    flags.update(enabled)
    return x509.KeyUsage(**flags)


def _tls_material(now: dt.datetime) -> tuple[bytes, bytes, bytes]:
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = _name("opportunity-radar ci ephemeral ca")
    not_before = now - dt.timedelta(minutes=5)
    not_after = now + dt.timedelta(days=1)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(_key_usage(digital_signature=True, key_cert_sign=True, crl_sign=True), True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(_name("issuer.test"))
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("issuer.test"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(_key_usage(digital_signature=True, key_encipherment=True), True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
        )
        .sign(ca_key, hashes.SHA256())
    )
    server_key_pem = server_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return (
        ca_cert.public_bytes(serialization.Encoding.PEM),
        server_cert.public_bytes(serialization.Encoding.PEM),
        server_key_pem,
    )


def init(directory: Path) -> None:
    """Generate fresh signing and TLS material; refuses to overwrite an existing set."""
    if (directory / "jwt" / "private.pem").exists():
        raise FixtureError("fixtures already exist in this directory; use a fresh one per run")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    kid = f"ci-{secrets.token_hex(8)}"
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": kid,
                "n": _b64url(numbers.n),
                "e": _b64url(numbers.e),
            }
        ]
    }
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    ca_pem, server_pem, server_key_pem = _tls_material(dt.datetime.now(dt.timezone.utc))
    _write(directory / "jwt" / "private.pem", private_pem, 0o600)
    _write(directory / "jwt" / "kid", kid, 0o600)
    _write(directory / "public" / "jwks.json", json.dumps(jwks), 0o644)
    _write(directory / "public" / "ca.pem", ca_pem, 0o644)
    _write(directory / "tls" / "server.pem", server_pem, 0o644)
    _write(directory / "tls" / "server.key", server_key_pem, 0o600)
    (directory / "tokens").mkdir(parents=True, exist_ok=True)
    print(f"fixtures written under {directory}")


def _load_signer(directory: Path) -> tuple[Any, str]:
    try:
        private = serialization.load_pem_private_key(
            (directory / "jwt" / "private.pem").read_bytes(), password=None
        )
        kid = (directory / "jwt" / "kid").read_text(encoding="utf-8").strip()
    except OSError as error:
        raise FixtureError("run init first: signing material is missing") from error
    return private, kid


def build_claims(
    persona: str, case: str, *, issuer: str, azp: str, now: int | None = None
) -> dict[str, Any]:
    if persona not in SUBJECTS:
        raise FixtureError(f"unknown persona {persona!r}")
    if issuer not in ALLOWED_ISSUERS or azp not in ALLOWED_ORIGINS:
        raise FixtureError("refusing a non-synthetic issuer or authorized party")
    issued = int(time.time()) if now is None else now
    expires = issued + LIFETIME_SECONDS
    if case == "expired":
        issued -= 2 * LIFETIME_SECONDS
        expires = issued + 60
    if case == "wrong-issuer":
        issuer = WRONG_ISSUER
    if case == "wrong-azp":
        azp = WRONG_ORIGIN
    return {"iss": issuer, "sub": SUBJECTS[persona], "azp": azp, "iat": issued, "exp": expires}


def mint(
    directory: Path,
    persona: str,
    header_file: Path,
    *,
    case: str = "valid",
    issuer: str = ISSUER,
    azp: str = ORIGIN,
) -> None:
    if case not in CASES:
        raise FixtureError(f"unknown case {case!r}")
    claims = build_claims(persona, case, issuer=issuer, azp=azp)
    private, kid = _load_signer(directory)
    if case == "unknown-kid":
        kid = f"ci-unknown-{secrets.token_hex(4)}"
    target = header_file if header_file.is_absolute() else directory / header_file
    if (directory / "tokens").resolve() not in target.resolve().parents:
        raise FixtureError("header files must live under DIR/tokens")
    token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": kid})
    _write(target, f"Authorization: Bearer {token}\n", 0o644)
    _write(target.with_suffix(".exp"), f"{claims['exp']}\n", 0o644)
    print(f"minted {case} {persona} header at {target}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ephemeral offline CI auth fixtures")
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init")
    init_parser.add_argument("--directory", type=Path, required=True)
    mint_parser = commands.add_parser("mint")
    mint_parser.add_argument("--directory", type=Path, required=True)
    mint_parser.add_argument("--persona", choices=sorted(SUBJECTS), required=True)
    mint_parser.add_argument("--header-file", type=Path, required=True)
    mint_parser.add_argument("--case", choices=CASES, default="valid")
    mint_parser.add_argument("--issuer", default=ISSUER)
    mint_parser.add_argument("--azp", default=ORIGIN)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            init(args.directory)
        else:
            mint(
                args.directory,
                args.persona,
                args.header_file,
                case=args.case,
                issuer=args.issuer,
                azp=args.azp,
            )
    except FixtureError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
