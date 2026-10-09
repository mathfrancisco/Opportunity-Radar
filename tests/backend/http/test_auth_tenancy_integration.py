"""Production HTTP tenancy checks with offline RS256/JWKS identities."""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.models import SavedSearchModel
from opportunity_radar.matching.models import CurrentAssessmentModel, MatchAssessmentModel
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.pipeline.models import ApplicationProcessModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http import app as app_module
from opportunity_radar.presentation.http.app import create_app
from opportunity_radar.presentation.http.auth import JwksClient
from opportunity_radar.presentation.http.dependencies import get_session
from opportunity_radar.profile.models import CareerProfileModel

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="HTTP tenancy checks require the isolated database suite",
    ),
]

ISSUER = "https://issuer.example.test"
PARTY = "https://app.example.test"
KID = "f53-http-tenancy-key"


def _b64(value: int) -> str:
    return (
        base64.urlsafe_b64encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))
        .rstrip(b"=")
        .decode()
    )


@pytest.fixture
def identities() -> tuple[object, dict[str, object], str, str]:
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
    return private, jwks, f"f53-http-a-{uuid4().hex}", f"f53-http-b-{uuid4().hex}"


def _headers(private: object, sub: str) -> dict[str, str]:
    token = jwt.encode(
        {"iss": ISSUER, "sub": sub, "azp": PARTY, "exp": int(time.time()) + 60},
        private,
        algorithm="RS256",
        headers={"kid": KID},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(
    identities: tuple[object, dict[str, object], str, str], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    _, jwks, owner_a, _ = identities
    monkeypatch.setattr(
        app_module,
        "JwksClient",
        lambda url: JwksClient(url, transport=lambda *_: json.dumps(jwks).encode()),
    )
    engine = create_database_engine(os.environ["DATABASE_URL"])
    app = create_app(
        Settings(
            database_url=os.environ["DATABASE_URL"],
            clerk_issuer=ISSUER,
            clerk_jwks_url=f"{ISSUER}/.well-known/jwks.json",
            clerk_authorized_parties=PARTY,
            clerk_owner_sub=owner_a,
        )
    )

    def sessions() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        with Session(engine) as session:
            owners = (owner_a, identities[3])
            session.execute(text("SELECT set_config('matching.allow_prune', 'on', true)"))
            session.execute(
                delete(CurrentAssessmentModel).where(
                    CurrentAssessmentModel.assessment_id.in_(
                        select(MatchAssessmentModel.id).where(
                            MatchAssessmentModel.owner_sub.in_(owners)
                        )
                    )
                )
            )
            session.execute(
                delete(MatchAssessmentModel).where(MatchAssessmentModel.owner_sub.in_(owners))
            )
            session.execute(
                delete(ApplicationProcessModel).where(ApplicationProcessModel.owner_sub.in_(owners))
            )
            session.execute(
                delete(SavedSearchModel).where(SavedSearchModel.owner_sub.in_(owners))
            )
            session.execute(
                delete(CareerProfileModel).where(CareerProfileModel.owner_sub.in_(owners))
            )
            session.commit()
        engine.dispose()


def test_authenticated_identities_cannot_read_or_mutate_each_others_saved_searches(
    client: TestClient, identities: tuple[object, dict[str, object], str, str]
) -> None:
    private, _, owner_a, owner_b = identities
    b_headers = _headers(private, owner_b)
    created = client.post(
        "/saved-searches", json={"name": "B private search", "filters": {}}, headers=b_headers
    )
    assert created.status_code == 201
    search_id = created.json()["id"]

    assert client.get("/saved-searches", headers=_headers(private, owner_a)).json() == []
    b_searches = client.get("/saved-searches", headers=b_headers).json()
    assert [item["id"] for item in b_searches] == [search_id]
    for method, path, body in (
        ("PATCH", f"/saved-searches/{search_id}", {"name": "A attempt"}),
        ("DELETE", f"/saved-searches/{search_id}", None),
        ("GET", f"/saved-searches/{search_id}/new-count", None),
    ):
        response = client.request(method, path, headers=_headers(private, owner_a), json=body)
        assert response.status_code == 404

    listed = client.get("/saved-searches", headers=b_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "B private search"


def test_profile_version_id_of_another_identity_is_not_publishable_or_activatable(
    client: TestClient, identities: tuple[object, dict[str, object], str, str]
) -> None:
    private, _, owner_a, owner_b = identities
    created = client.post(
        "/profile/versions",
        json={"expected_profile_version": 0},
        headers=_headers(private, owner_a),
    )
    assert created.status_code == 201
    version_id = created.json()["id"]

    for action in ("publish", "activate"):
        response = client.post(
            f"/profile/versions/{version_id}/{action}",
            json={"expected_profile_version": 1},
            headers=_headers(private, owner_b),
        )
        assert response.status_code == 404


def test_private_http_routes_fail_closed_without_a_valid_bearer_token(
    client: TestClient,
) -> None:
    assert client.get("/saved-searches").status_code == 401
    invalid = client.get("/saved-searches", headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401


def test_foreign_profile_version_is_rejected_by_pipeline_and_matching(
    client: TestClient, identities: tuple[object, dict[str, object], str, str]
) -> None:
    private, _, owner_a, owner_b = identities
    profile = client.post(
        "/profile/versions",
        json={"expected_profile_version": 0},
        headers=_headers(private, owner_a),
    )
    assert profile.status_code == 201
    engine = create_database_engine(os.environ["DATABASE_URL"])
    opportunity = OpportunityModel(
        id=uuid4(),
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="F53 tenancy role",
        normalized_title="f53 tenancy role",
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        version=1,
    )
    opportunity_id = opportunity.id
    try:
        with Session(engine) as session:
            session.add(opportunity)
            session.commit()
        body = {"opportunity_id": str(opportunity_id), "profile_version_id": profile.json()["id"]}
        headers = _headers(private, owner_b)
        assert client.post("/applications", json=body, headers=headers).status_code == 404
        assert client.post("/matches/evaluate", json=body, headers=headers).status_code == 404
    finally:
        with Session(engine) as session:
            session.execute(
                delete(ApplicationProcessModel).where(
                    ApplicationProcessModel.opportunity_id == opportunity_id
                )
            )
            session.execute(delete(OpportunityModel).where(OpportunityModel.id == opportunity_id))
            session.commit()
        engine.dispose()


def test_member_cannot_execute_a_shared_source(
    client: TestClient, identities: tuple[object, dict[str, object], str, str]
) -> None:
    private, _, _, owner_b = identities
    response = client.post(
        f"/sources/{uuid4()}/runs", json={}, headers=_headers(private, owner_b)
    )
    assert response.status_code == 403


def test_application_history_and_follow_up_remain_private_in_the_overview(
    client: TestClient, identities: tuple[object, dict[str, object], str, str]
) -> None:
    private, _, owner_a, owner_b = identities
    profile = client.post(
        "/profile/versions",
        json={"expected_profile_version": 0, "activate": True},
        headers=_headers(private, owner_a),
    )
    assert profile.status_code == 201
    engine = create_database_engine(os.environ["DATABASE_URL"])
    opportunity = OpportunityModel(
        id=uuid4(),
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="F53 private application role",
        normalized_title="f53 private application role",
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        version=1,
    )
    opportunity_id = opportunity.id
    try:
        with Session(engine) as session:
            session.add(opportunity)
            session.commit()
        created = client.post(
            "/applications",
            json={
                "opportunity_id": str(opportunity_id),
                "profile_version_id": profile.json()["id"],
                "next_action": "Private follow-up",
            },
            headers=_headers(private, owner_a),
        )
        assert created.status_code == 201
        application_id = created.json()["id"]
        b_headers = _headers(private, owner_b)
        assert client.get("/applications", headers=b_headers).json()["items"] == []
        assert client.get(f"/applications/{application_id}", headers=b_headers).status_code == 404
        assert client.post(
            f"/applications/{application_id}/transitions",
            json={"stage": "APPLIED", "expected_version": 1},
            headers=b_headers,
        ).status_code == 404
        assert client.patch(
            f"/applications/{application_id}/next-action",
            json={"expected_version": 1, "next_action": "Attempt"},
            headers=b_headers,
        ).status_code == 404

        member_overview = client.get("/overview", headers=b_headers)
        owner_overview = client.get("/overview", headers=_headers(private, owner_a))
        assert member_overview.status_code == owner_overview.status_code == 200
        assert member_overview.json()["applications_active"] == 0
        assert owner_overview.json()["applications_active"] == 1
        assert "sources_total" not in member_overview.json()
        assert "sources_total" in owner_overview.json()
    finally:
        with Session(engine) as session:
            session.execute(
                delete(ApplicationProcessModel).where(
                    ApplicationProcessModel.opportunity_id == opportunity_id
                )
            )
            session.execute(delete(OpportunityModel).where(OpportunityModel.id == opportunity_id))
            session.commit()
        engine.dispose()


def test_match_list_and_detail_hide_another_identity_assessment(
    client: TestClient, identities: tuple[object, dict[str, object], str, str]
) -> None:
    private, _, owner_a, owner_b = identities
    profile = client.post(
        "/profile/versions",
        json={"expected_profile_version": 0},
        headers=_headers(private, owner_a),
    )
    assert profile.status_code == 201
    engine = create_database_engine(os.environ["DATABASE_URL"])
    opportunity = OpportunityModel(
        id=uuid4(),
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="F53 private match role",
        normalized_title="f53 private match role",
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        version=1,
    )
    assessment_id = uuid4()
    opportunity_id = opportunity.id
    try:
        with Session(engine) as session:
            session.add(opportunity)
            session.flush()
            session.add(
                MatchAssessmentModel(
                    id=assessment_id,
                    owner_sub=owner_a,
                    opportunity_id=opportunity_id,
                    opportunity_version=1,
                    profile_version_id=UUID(profile.json()["id"]),
                    input_hash=uuid4().hex + uuid4().hex,
                    rules_version="matching-v5",
                    taxonomy_version="skills-v5",
                    opportunity_snapshot={},
                    profile_snapshot={},
                    eligibility="ELIGIBLE",
                    verdict="RECOMMENDED",
                    score=Decimal("50"),
                    confidence=Decimal("0.9"),
                    assessed_at=datetime.now(UTC),
                )
            )
            session.commit()
        b_headers = _headers(private, owner_b)
        assert client.get("/matches", headers=b_headers).json()["items"] == []
        assert client.get(f"/matches/{assessment_id}", headers=b_headers).status_code == 404
    finally:
        with Session(engine) as session:
            session.execute(text("SELECT set_config('matching.allow_prune', 'on', true)"))
            session.execute(
                delete(CurrentAssessmentModel).where(
                    CurrentAssessmentModel.assessment_id == assessment_id
                )
            )
            session.execute(
                delete(MatchAssessmentModel).where(MatchAssessmentModel.id == assessment_id)
            )
            session.execute(delete(OpportunityModel).where(OpportunityModel.id == opportunity_id))
            session.commit()
        engine.dispose()
