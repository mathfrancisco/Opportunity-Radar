import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from opportunity_radar.platform.config import Settings
from opportunity_radar.presentation.http.app import create_app
from opportunity_radar.presentation.http.auth import (
    AuthConfig,
    AuthenticationError,
    JwksClient,
    JwtVerifier,
    RequireAuthenticated,
    RequireOwner,
)

ISSUER = "https://issuer.example.test"
PARTY = "https://app.example.test"
OWNER = "user_owner_synthetic"
KID = "test-key-1"


def _b64(value: int) -> str:
    return (
        base64.urlsafe_b64encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))
        .rstrip(b"=")
        .decode()
    )


@pytest.fixture
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_numbers()
    return private, {
        "keys": [{"kty": "RSA", "kid": KID, "use": "sig", "n": _b64(public.n), "e": _b64(public.e)}]
    }


def _verifier(keypair) -> JwtVerifier:
    _, jwks = keypair
    config = AuthConfig(
        issuer=ISSUER,
        jwks_url=f"{ISSUER}/.well-known/jwks.json",
        authorized_parties=frozenset({PARTY}),
        owner_sub=OWNER,
    )
    return JwtVerifier(
        config, JwksClient(config.jwks_url, transport=lambda *_: json.dumps(jwks).encode())
    )


def _token(private, **claims: object) -> str:
    payload = {"iss": ISSUER, "sub": OWNER, "azp": PARTY, "exp": int(time.time()) + 60, **claims}
    return jwt.encode(payload, private, algorithm="RS256", headers={"kid": KID})


def _client(verifier: JwtVerifier) -> TestClient:
    app = FastAPI()

    @app.get("/private")
    def private(identity=Depends(RequireAuthenticated(verifier))):
        return {"sub": identity.sub}

    @app.get("/owner")
    def owner(identity=Depends(RequireOwner(RequireAuthenticated(verifier)))):
        return {"owner": identity.is_owner}

    return TestClient(app)


def test_missing_or_malformed_bearer_is_unauthorized(keypair) -> None:
    client = _client(_verifier(keypair))

    assert client.get("/private").status_code == 401
    assert client.get("/private", headers={"Authorization": "Basic nope"}).status_code == 401
    assert client.get("/private", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        ({"exp": int(time.time()) - 1}, 401),
        ({"iss": "https://other.example.test"}, 401),
        ({"azp": None}, 401),
        ({"azp": "https://other-app.example.test"}, 401),
    ],
)
def test_invalid_claims_are_unauthorized(keypair, claims: dict[str, object], expected: int) -> None:
    private, _ = keypair
    response = _client(_verifier(keypair)).get(
        "/private", headers={"Authorization": f"Bearer {_token(private, **claims)}"}
    )

    assert response.status_code == expected


def test_unknown_kid_and_jwks_outage_are_unauthorized(keypair) -> None:
    private, _ = keypair
    verifier = _verifier(keypair)
    unknown = jwt.encode(
        {"iss": ISSUER, "sub": OWNER, "azp": PARTY, "exp": int(time.time()) + 60},
        private,
        algorithm="RS256",
        headers={"kid": "unknown"},
    )
    assert (
        _client(verifier)
        .get("/private", headers={"Authorization": f"Bearer {unknown}"})
        .status_code
        == 401
    )

    config = verifier.config
    unavailable = JwtVerifier(
        config, JwksClient(config.jwks_url, transport=lambda *_: (_ for _ in ()).throw(OSError()))
    )
    assert (
        _client(unavailable)
        .get("/private", headers={"Authorization": f"Bearer {_token(private)}"})
        .status_code
        == 401
    )


def test_unknown_kid_refreshes_a_valid_jwks_cache_once(keypair) -> None:
    private, jwks = keypair
    requests = 0

    def transport(*_: object) -> bytes:
        nonlocal requests
        requests += 1
        return json.dumps(jwks).encode()

    config = AuthConfig(
        issuer=ISSUER,
        jwks_url=f"{ISSUER}/.well-known/jwks.json",
        authorized_parties=frozenset({PARTY}),
        owner_sub=OWNER,
    )
    verifier = JwtVerifier(config, JwksClient(config.jwks_url, transport=transport))
    assert verifier.verify(_token(private)).sub == OWNER

    unknown = jwt.encode(
        {"iss": ISSUER, "sub": OWNER, "azp": PARTY, "exp": int(time.time()) + 60},
        private,
        algorithm="RS256",
        headers={"kid": "rotated-key"},
    )
    with pytest.raises(AuthenticationError, match="jwks_unknown_kid"):
        verifier.verify(unknown)

    assert requests == 2


def test_valid_token_returns_identity_and_non_owner_is_forbidden(keypair) -> None:
    private, _ = keypair
    client = _client(_verifier(keypair))
    owner = {"Authorization": f"Bearer {_token(private)}"}
    normal = {"Authorization": f"Bearer {_token(private, sub='user_normal_synthetic')}"}

    assert client.get("/private", headers=owner).json() == {"sub": OWNER}
    assert client.get("/owner", headers=owner).json() == {"owner": True}
    assert client.get("/owner", headers=normal).status_code == 403


def test_auth_settings_are_required_and_jwks_must_belong_to_https_issuer() -> None:
    with pytest.raises(ValueError):
        AuthConfig(
            issuer="http://issuer.example.test",
            jwks_url="http://issuer.example.test/keys",
            authorized_parties=frozenset({PARTY}),
            owner_sub=OWNER,
        )
    with pytest.raises(ValueError):
        AuthConfig(
            issuer=ISSUER,
            jwks_url="https://elsewhere.example.test/keys",
            authorized_parties=frozenset({PARTY}),
            owner_sub=OWNER,
        )

    settings = Settings(database_url="postgresql+psycopg://test:test@localhost/test")
    assert settings.clerk_issuer is None


def test_production_factory_leaves_only_liveness_public(keypair, monkeypatch) -> None:
    _, jwks = keypair
    from opportunity_radar.presentation.http import app as app_module

    monkeypatch.setattr(
        app_module,
        "JwksClient",
        lambda url: JwksClient(url, transport=lambda *_: json.dumps(jwks).encode()),
    )
    app = create_app(
        Settings(
            database_url="postgresql+psycopg://test:test@localhost/test",
            clerk_issuer=ISSUER,
            clerk_jwks_url=f"{ISSUER}/.well-known/jwks.json",
            clerk_authorized_parties=PARTY,
            clerk_owner_sub=OWNER,
        )
    )
    client = TestClient(app)

    assert client.get("/health/live").status_code == 200
    assert client.get("/health").status_code == 401
    assert client.get("/docs").status_code == 404
    assert (
        client.get("/health/live", headers={"X-Correlation-ID": "unsafe\r\nvalue"}).headers[
            "X-Correlation-ID"
        ]
        != "unsafe\r\nvalue"
    )


def test_production_factory_rejects_missing_clerk_configuration() -> None:
    with pytest.raises(RuntimeError, match="requires Clerk"):
        create_app(Settings(database_url="postgresql+psycopg://test:test@localhost/test"))
