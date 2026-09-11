from opportunity_radar.companies.domain import (
    CompanyCandidate,
    normalize_domain,
    normalize_name,
)


def test_normalizes_unicode_names_and_domains() -> None:
    assert normalize_name("  Açúcar   S.A. ") == "acucar s.a."
    assert normalize_domain("HTTPS://WWW.Example.COM/jobs") == "example.com"


def test_candidate_drops_canonical_name_from_aliases() -> None:
    candidate = CompanyCandidate(name="Acme", aliases=("ACME", "Acme Ltd"))

    assert candidate.normalized_aliases == ("acme ltd",)
