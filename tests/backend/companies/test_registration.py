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
