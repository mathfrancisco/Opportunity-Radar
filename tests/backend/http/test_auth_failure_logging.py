"""Auth failures log a reason and correlation id, and never the bearer token."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from tests.backend.support.auth import (
    ISSUER,
    KID,
    OWNER_SUB,
    PARTY,
    auth_headers,
    authenticated_test_client,
    shared_keypair,
)

AUTH_LOGGER = "opportunity_radar.http.auth"
DATABASE_URL = "postgresql+psycopg://test:test@localhost/test"
CORRELATION_HEADER = "X-Correlation-ID"


@pytest.fixture
def client(caplog: pytest.LogCaptureFixture) -> Iterator[TestClient]:
    # create_app() reconfigures the root handlers; pytest re-installs caplog's for the call
    # phase, so records only need the level pinned here.
    test_client = authenticated_test_client(DATABASE_URL)
    caplog.set_level(logging.WARNING, logger=AUTH_LOGGER)
    yield test_client


def _denials(caplog: pytest.LogCaptureFixture, message: str) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == AUTH_LOGGER and record.getMessage() == message
    ]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _claims(**overrides: object) -> dict[str, object]:
    return {
        "iss": ISSUER,
        "sub": OWNER_SUB,
        "azp": PARTY,
        "nbf": int(time.time()) - 5,
        "exp": int(time.time()) + 300,
        **overrides,
    }


def _bad_tokens() -> dict[str, str]:
    private, _ = shared_keypair()
    foreign = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    marker = "distinctive-marker-claim"
    return {
        "malformed": "distinctivemalformedheader.distinctivemalformedbody.distinctivemalformedsig",
        "wrong_key": jwt.encode(
            _claims(marker=marker), foreign, algorithm="RS256", headers={"kid": KID}
        ),
        "expired": jwt.encode(
            _claims(exp=int(time.time()) - 60, marker=marker),
            private,
            algorithm="RS256",
            headers={"kid": KID},
        ),
    }


def _assert_token_absent(
    token: str, caplog: pytest.LogCaptureFixture, records: list[logging.LogRecord]
) -> None:
    signature = token.split(".")[2]
    assert signature
    haystacks = [caplog.text]
    for record in records:
        haystacks.append(record.getMessage())
        haystacks.extend(str(value) for value in record.__dict__.values())
    for haystack in haystacks:
        assert token not in haystack
        assert signature not in haystack


def test_missing_bearer_logs_one_denial_with_a_reason(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = TestClient(client.app).get("/health")

    assert response.status_code == 401
    (record,) = _denials(caplog, "authentication denied")
    assert record.auth_reason == "missing_authorization"


def test_denial_carries_the_caller_correlation_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    sent = "corr-auth-failure-0123"

    response = TestClient(client.app).get("/health", headers={CORRELATION_HEADER: sent})

    assert response.status_code == 401
    assert response.headers[CORRELATION_HEADER] == sent
    (record,) = _denials(caplog, "authentication denied")
    assert record.correlation_id == sent


@pytest.mark.parametrize("kind", ["malformed", "wrong_key", "expired"])
def test_rejected_token_never_reaches_the_log(
    client: TestClient, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    token = _bad_tokens()[kind]

    response = TestClient(client.app).get("/health", headers=_bearer(token))

    assert response.status_code == 401
    records = _denials(caplog, "authentication denied")
    assert len(records) == 1
    assert records[0].auth_reason
    _assert_token_absent(token, caplog, caplog.records)


def test_non_owner_denial_logs_a_reason_and_no_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    private, _ = shared_keypair()
    headers = auth_headers(private, sub="user_normal_synthetic")
    token = headers["Authorization"].removeprefix("Bearer ")

    response = TestClient(client.app).get(
        "/sources", headers={**headers, CORRELATION_HEADER: "corr-non-owner-42"}
    )

    assert response.status_code == 403
    (record,) = _denials(caplog, "authorization denied")
    assert record.auth_reason == "owner_required"
    assert record.correlation_id == "corr-non-owner-42"
    _assert_token_absent(token, caplog, caplog.records)
