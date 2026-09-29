"""Unit tests for the ATS vocabulary `CompanyRegistration` enforces.

`_source_values` is the one place that checks a proposed source's type and key against
the collectors the radar actually runs (`SUPPORTED_ATS`). It needs no database, so it is
exercised directly rather than through `CompanyRegistration.add_source`, which requires a
session and a persisted company.
"""

from __future__ import annotations

import pytest

from opportunity_radar.acquisition.domain import AcquisitionError
from opportunity_radar.companies.registration import (
    SUPPORTED_ATS,
    CompanyRegistrationError,
    _source_values,
)


def test_registration_accepts_workday_source_type() -> None:
    assert "workday" in SUPPORTED_ATS

    values = _source_values(
        "workday",
        "https://acme.wd5.myworkdayjobs.com/ExternalCareerSite",
        "acme/ExternalCareerSite",
        "found via careers page discovery",
    )

    assert values["source_type"] == "workday"
    assert values["external_key"] == "acme/ExternalCareerSite"


def test_registration_rejects_malformed_workday_tenant_identifier() -> None:
    with pytest.raises(CompanyRegistrationError) as error:
        _source_values(
            "workday",
            "https://acme.wd5.myworkdayjobs.com/ExternalCareerSite",
            "acme-without-site",
            "found via careers page discovery",
        )
    assert error.value.field == "external_key"


def test_workday_validator_raises_acquisition_error_for_bad_identifier() -> None:
    from opportunity_radar.acquisition.workday import WorkdayCollector

    with pytest.raises(AcquisitionError):
        WorkdayCollector.validate_tenant_identifier("acme-without-site")


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


def test_registration_accepts_workable_source_type() -> None:
    assert "workable" in SUPPORTED_ATS

    values = _source_values(
        "workable",
        "https://apply.workable.com/acme",
        "acme",
        "found via careers page discovery",
    )

    assert values["source_type"] == "workable"
    assert values["external_key"] == "acme"


def test_registration_rejects_malformed_workable_account_identifier() -> None:
    with pytest.raises(CompanyRegistrationError) as error:
        _source_values(
            "workable",
            "https://apply.workable.com/acme",
            "-not valid-",
            "found via careers page discovery",
        )
    assert error.value.field == "external_key"


def test_workable_validator_raises_acquisition_error_for_bad_identifier() -> None:
    from opportunity_radar.acquisition.workable import WorkableCollector

    with pytest.raises(AcquisitionError):
        WorkableCollector.validate_account_identifier("-not valid-")


def test_registration_accepts_factorial_source_type() -> None:
    assert "factorial" in SUPPORTED_ATS
    values = _source_values(
        "factorial",
        "https://acme.factorialhr.com/",
        "acme",
        "found in careers footer",
    )
    assert values["source_type"] == "factorial"
    assert values["external_key"] == "acme"
    assert values["endpoint"] == "https://acme.factorialhr.com/"


def test_registration_rejects_invalid_factorial_identifier() -> None:
    with pytest.raises(CompanyRegistrationError) as error:
        _source_values(
            "factorial",
            "https://acme.factorialhr.com/",
            "https://acme.factorialhr.com/",
            "found in careers footer",
        )
    assert error.value.field == "external_key"
