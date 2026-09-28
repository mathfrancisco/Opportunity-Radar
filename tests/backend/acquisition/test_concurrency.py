from __future__ import annotations

import asyncio
import time

import pytest

from opportunity_radar.acquisition.concurrency import HostSerializer, source_host_key


def test_source_host_key_shared_provider_types_key_on_source_type_alone() -> None:
    for source_type in ("ashby", "lever", "greenhouse", "workable", "remotive"):
        assert source_host_key(source_type, {"anything": "x"}) == source_type


def test_source_host_key_tenant_types_key_on_their_own_tenant_config() -> None:
    assert source_host_key("teamtailor", {"company_identifier": "acme"}) == "teamtailor:acme"
    assert source_host_key("factorial", {"company_identifier": "acme"}) == "factorial:acme"
    assert (
        source_host_key("workday", {"tenant_identifier": "acme", "api_region": "us"})
        == "workday:acme:us"
    )


def test_source_host_key_distinguishes_two_tenants_of_the_same_provider() -> None:
    acme = source_host_key("teamtailor", {"company_identifier": "acme"})
    other = source_host_key("teamtailor", {"company_identifier": "other"})
    assert acme != other


def test_source_host_key_jobposting_keys_on_the_pages_own_hostname() -> None:
    key = source_host_key("jobposting", {"page_url": "https://acme.example.test/careers"})
    assert key == "jobposting:acme.example.test"


def test_source_host_key_never_raises_on_missing_configuration() -> None:
    assert source_host_key("teamtailor", {}) == "teamtailor:"
    assert source_host_key("teamtailor", None) == "teamtailor:"
    assert source_host_key("jobposting", {}) == "jobposting:"
    assert source_host_key("jobposting", None) == "jobposting:"
    assert source_host_key("unknown_type", {}) == "unknown_type"


def test_host_serializer_returns_the_same_lock_for_the_same_host() -> None:
    serializer = HostSerializer()
    assert serializer.lock_for("a.example.test") is serializer.lock_for("a.example.test")
    assert serializer.lock_for("a.example.test") is not serializer.lock_for("b.example.test")


def test_host_serializer_paces_consecutive_requests_on_the_same_host() -> None:
    serializer = HostSerializer(min_interval_seconds=0.05)

    async def scenario() -> float:
        await serializer.wait_turn("a.example.test")
        start = time.monotonic()
        await serializer.wait_turn("a.example.test")
        return time.monotonic() - start

    elapsed = asyncio.run(scenario())
    assert elapsed >= 0.04  # small slack for scheduler jitter


def test_host_serializer_does_not_pace_across_different_hosts() -> None:
    serializer = HostSerializer(min_interval_seconds=5.0)

    async def scenario() -> float:
        await serializer.wait_turn("a.example.test")
        start = time.monotonic()
        await serializer.wait_turn("b.example.test")
        return time.monotonic() - start

    elapsed = asyncio.run(scenario())
    assert elapsed < 1.0


def test_host_serializer_rejects_a_negative_interval() -> None:
    with pytest.raises(ValueError):
        HostSerializer(min_interval_seconds=-1.0)
