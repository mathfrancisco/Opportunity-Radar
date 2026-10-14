"""Offline RS256/JWKS helpers for production-app integration tests."""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from opportunity_radar.platform.config import Settings
from opportunity_radar.presentation.http import app as app_module
from opportunity_radar.presentation.http.app import create_app
from opportunity_radar.presentation.http.auth import JwksClient
from opportunity_radar.presentation.http.dependencies import get_session

ISSUER = "https://issuer.example.test"
PARTY = "https://app.example.test"
KID = "ci-offline-key"
OWNER_SUB = "user_owner_synthetic"


def _b64(value: int) -> str:
    return (
        base64.urlsafe_b64encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))
        .rstrip(b"=")
        .decode()
    )


def generate_keypair() -> tuple[object, dict[str, Any]]:
    """Return an RSA private key and a matching JWKS document."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": KID,
                "use": "sig",
                "n": _b64(public.n),
                "e": _b64(public.e),
            }
        ]
    }
    return private, jwks


def auth_headers(
    private_key: object,
    sub: str = OWNER_SUB,
    *,
    kid: str = KID,
    party: str = PARTY,
    issuer: str = ISSUER,
    exp_seconds: int = 300,
) -> dict[str, str]:
    """Build an Authorization bearer header for the given subject."""
    token = jwt.encode(
        {
            "iss": issuer,
            "sub": sub,
            "azp": party,
            "exp": int(time.time()) + exp_seconds,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    return {"Authorization": f"Bearer {token}"}


def auth_settings(
    database_url: str | None = None,
    *,
    owner_sub: str = OWNER_SUB,
    frontend_origin: str = PARTY,
) -> Settings:
    """Build production-app Settings with a synthetic Clerk configuration."""
    return Settings(
        database_url=database_url or os.environ["DATABASE_URL"],
        frontend_origin=frontend_origin,
        clerk_issuer=ISSUER,
        clerk_jwks_url=f"{ISSUER}/.well-known/jwks.json",
        clerk_authorized_parties=PARTY,
        clerk_owner_sub=owner_sub,
    )


_KEYPAIR: tuple[object, dict[str, Any]] | None = None


def shared_keypair() -> tuple[object, dict[str, Any]]:
    """Process-wide offline keypair; the signer never leaves the test tree."""
    global _KEYPAIR
    if _KEYPAIR is None:
        _KEYPAIR = generate_keypair()
    return _KEYPAIR


def authenticated_test_client(
    database_url: str | None = None,
    *,
    owner_sub: str = OWNER_SUB,
    session: Session | None = None,
) -> TestClient:
    """Build a TestClient over the production ``create_app`` factory.

    Tokens are RS256-signed by an in-process key and verified against an offline
    JWKS document; the bearer header for ``owner_sub`` is preset on the client.
    ``session`` optionally overrides the request-scoped database session.
    """
    private_key, jwks = shared_keypair()
    transport = lambda *_: json.dumps(jwks).encode()  # noqa: E731
    with patch.object(
        app_module, "JwksClient", lambda url: JwksClient(url, transport=transport)
    ):
        app = create_app(auth_settings(database_url, owner_sub=owner_sub))
    if session is not None:
        app.dependency_overrides[get_session] = lambda: session
    return TestClient(app, headers=auth_headers(private_key, owner_sub))
