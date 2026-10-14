from __future__ import annotations

from fastapi.testclient import TestClient

from tests.backend.support.auth import (
    OWNER_SUB,
    auth_headers,
    authenticated_test_client,
    generate_keypair,
    shared_keypair,
)

UNREACHABLE_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:1/unreachable_test"


def session_client() -> TestClient:
    return authenticated_test_client(UNREACHABLE_DATABASE_URL)


def test_session_returns_only_owner_capability_without_opening_a_database_session() -> None:
    response = session_client().get("/session")

    assert response.status_code == 200
    assert response.json() == {"is_owner": True}
    assert response.headers["Cache-Control"] == "no-store"


def test_session_returns_false_for_an_authenticated_non_owner() -> None:
    private_key, _ = shared_keypair()
    response = session_client().get("/session", headers=auth_headers(private_key, "user_other"))

    assert response.status_code == 200
    assert response.json() == {"is_owner": False}


def test_session_rejects_missing_malformed_invalid_and_expired_tokens() -> None:
    client = session_client()
    no_token_client = session_client()
    no_token_client.headers.pop("Authorization")
    owner_key, _ = shared_keypair()
    different_key, _ = generate_keypair()

    responses = [
        no_token_client.get("/session"),
        client.get("/session", headers={"Authorization": "Bearer malformed"}),
        client.get("/session", headers=auth_headers(different_key)),
        client.get("/session", headers=auth_headers(owner_key, exp_seconds=-1)),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]


def test_session_ignores_request_values_that_claim_owner_access() -> None:
    private_key, _ = shared_keypair()
    response = session_client().request(
        "GET",
        f"/session?is_owner=true&sub={OWNER_SUB}",
        headers=auth_headers(private_key, "user_other"),
        json={"is_owner": True, "sub": OWNER_SUB},
    )

    assert response.status_code == 200
    assert response.json() == {"is_owner": False}
