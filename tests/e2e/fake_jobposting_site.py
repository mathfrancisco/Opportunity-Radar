"""Static pages with schema.org `JobPosting` JSON-LD for F20-37's collector tests.

Every page is served in-process through `httpx.MockTransport`; no socket is opened. Each
function returns the raw HTML for one scenario named after what it proves: object/list/
`@graph` forms, pt/en, missing fields, a divergent schema, a soft-404 with HTTP 200, and a
page with no markup at all.
"""

from __future__ import annotations

PAGE_URL = "https://careers.example.test/jobs/senior-engineer"


def _wrap(jsonld: str) -> str:
    return (
        "<html><head>"
        f'<script type="application/ld+json">{jsonld}</script>'
        "</head><body><h1>Senior Engineer</h1></body></html>"
    )


def single_object_en() -> str:
    return _wrap(
        """
        {
          "@context": "https://schema.org/",
          "@type": "JobPosting",
          "identifier": "ACME-1001",
          "title": "Senior Backend Engineer",
          "description": "<p>Build the platform.</p>",
          "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
          "url": "https://careers.example.test/jobs/senior-engineer",
          "datePosted": "2026-09-01T00:00:00Z",
          "validThrough": "2026-12-01T00:00:00Z",
          "employmentType": "FULL_TIME",
          "jobLocation": {
            "@type": "Place",
            "address": {
              "@type": "PostalAddress",
              "addressLocality": "Remote",
              "addressCountry": "BR"
            }
          },
          "jobLocationType": "TELECOMMUTE",
          "baseSalary": {
            "@type": "MonetaryAmount",
            "currency": "USD",
            "value": {
              "@type": "QuantitativeValue",
              "minValue": 120000,
              "maxValue": 160000,
              "unitText": "YEAR"
            }
          }
        }
        """
    )


def single_object_pt() -> str:
    return _wrap(
        """
        {
          "@context": "https://schema.org/",
          "@type": "JobPosting",
          "identifier": "ACME-2002",
          "title": "Engenheiro(a) de Backend Senior",
          "description": "<p>Construa a plataforma.</p>",
          "hiringOrganization": {"@type": "Organization", "name": "Acme Corp Brasil"},
          "url": "https://careers.example.test/vagas/engenheiro-backend",
          "datePosted": "2026-09-05T00:00:00-03:00",
          "applicantLocationRequirements": [
            {"@type": "Country", "name": "Brazil"}
          ]
        }
        """
    )


def list_of_postings() -> str:
    return _wrap(
        """
        [
          {
            "@type": "JobPosting",
            "identifier": "ACME-3001",
            "title": "Data Engineer",
            "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
            "url": "https://careers.example.test/jobs/data-engineer"
          },
          {
            "@type": "JobPosting",
            "identifier": "ACME-3002",
            "title": "Frontend Engineer",
            "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
            "url": "https://careers.example.test/jobs/frontend-engineer"
          }
        ]
        """
    )


def graph_of_postings() -> str:
    return _wrap(
        """
        {
          "@context": "https://schema.org/",
          "@graph": [
            {"@type": "WebPage", "name": "Careers"},
            {
              "@type": "JobPosting",
              "identifier": "ACME-4001",
              "title": "Site Reliability Engineer",
              "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
              "url": "https://careers.example.test/jobs/sre"
            }
          ]
        }
        """
    )


def missing_required_fields() -> str:
    """No `title`; the node must be skipped, and the page has nothing else, so the whole
    page fails rather than returning an empty success."""
    return _wrap(
        """
        {
          "@type": "JobPosting",
          "identifier": "ACME-5001",
          "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
          "url": "https://careers.example.test/jobs/incomplete"
        }
        """
    )


def mixed_valid_and_missing() -> str:
    """One node lacks a title (skipped), the other is valid — the page still succeeds
    with exactly the valid one."""
    return _wrap(
        """
        [
          {
            "@type": "JobPosting",
            "identifier": "ACME-6001",
            "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
            "url": "https://careers.example.test/jobs/incomplete"
          },
          {
            "@type": "JobPosting",
            "identifier": "ACME-6002",
            "title": "Support Engineer",
            "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
            "url": "https://careers.example.test/jobs/support-engineer"
          }
        ]
        """
    )


def divergent_schema() -> str:
    """A `Product` review, not a `JobPosting` — a real, common false lead."""
    return _wrap(
        """
        {
          "@type": "Product",
          "name": "Acme Widget",
          "review": {"@type": "Review", "reviewBody": "Great widget"}
        }
        """
    )


def soft_404() -> str:
    """HTTP 200 with an error page's body — no `JobPosting` markup anywhere."""
    return (
        "<html><body><h1>Página não encontrada</h1>"
        "<p>A vaga que você procura não existe mais.</p></body></html>"
    )


def no_markup_at_all() -> str:
    return "<html><body><h1>Careers</h1><p>See open roles below.</p></body></html>"


def telecommute_without_location_requirements() -> str:
    """`jobLocationType=TELECOMMUTE` with no `applicantLocationRequirements` at all —
    must never be read as global eligibility."""
    return _wrap(
        """
        {
          "@type": "JobPosting",
          "identifier": "ACME-7001",
          "title": "Remote Support Engineer",
          "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
          "url": "https://careers.example.test/jobs/remote-support",
          "jobLocationType": "TELECOMMUTE"
        }
        """
    )
