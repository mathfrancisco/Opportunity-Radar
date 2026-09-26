"""Unit coverage for `_source_values`, independent of the database.

F20-29 adds `teamtailor` to `SUPPORTED_ATS`; this only exercises the validation path (no
DB session needed), leaving the full `add_source`/`update_source` round trip to the
integration suite that already covers `greenhouse` in `tests/backend/test_phase14_integration.py`.
"""

import pytest

from opportunity_radar.companies.registration import (
    SUPPORTED_ATS,
    CompanyRegistrationError,
    _source_values,
)


def test_registration_accepts_teamtailor_source_type() -> None:
    assert "teamtailor" in SUPPORTED_ATS
    values = _source_values(
        "teamtailor",
        "https://jobs.acme-careers.test/jobs.json",
        "jobs.acme-careers.test",
        "found in careers footer",
    )
    assert values["source_type"] == "teamtailor"
    assert values["external_key"] == "jobs.acme-careers.test"
    assert values["endpoint"] == "https://jobs.acme-careers.test/jobs.json"


def test_registration_rejects_invalid_teamtailor_identifier() -> None:
    with pytest.raises(CompanyRegistrationError) as error:
        _source_values(
            "teamtailor",
            "https://jobs.acme-careers.test/jobs.json",
            "https://jobs.acme-careers.test/jobs.json",
            "found in careers footer",
        )
    assert error.value.field == "external_key"
