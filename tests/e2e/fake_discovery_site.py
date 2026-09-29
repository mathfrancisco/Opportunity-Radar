"""In-process fake careers site for F20-36's limited discovery tests.

Each scenario builder returns an `httpx.MockTransport`-compatible handler (a plain
function, `httpx.Request -> httpx.Response`) for one behaviour the crawler must survive:
a self-referencing sitemap, a redirect into a private network, an unreachable
`robots.txt`, a sitemap that declares an external entity, and a JS-rendered shell. No real
socket is opened — `httpx.MockTransport` intercepts before any connection, which is why
`run_limited_discovery`'s `resolve_ips` is always faked alongside it (real DNS would never
resolve `*.example.test`).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

HOST = "careers.example.test"
ORIGIN = f"https://{HOST}"
#: A real public IP (Google Public DNS) used only as a stand-in resolution answer —
#: `httpx.MockTransport` never opens a socket, so this address is never actually
#: contacted. RFC 5737 documentation ranges (192.0.2.0/24 etc.) will not do here: Python's
#: `ipaddress.is_private` classifies them as private.
PUBLIC_IP = "8.8.8.8"
PRIVATE_IP = "127.0.0.1"

Handler = Callable[[httpx.Request], httpx.Response]


def _xml(body: str) -> httpx.Response:
    return httpx.Response(
        200, content=body.encode("utf-8"), headers={"content-type": "application/xml"}
    )


def _html(body: str) -> httpx.Response:
    return httpx.Response(200, content=body.encode("utf-8"), headers={"content-type": "text/html"})


_ROBOTS_OK = "User-agent: *\nDisallow:\nSitemap: https://careers.example.test/sitemap.xml\n"


def _router(
    routes: dict[str, httpx.Response | Callable[[httpx.Request], httpx.Response]],
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        entry = routes.get(path)
        if entry is None:
            return httpx.Response(404, content=b"not found")
        return entry(request) if callable(entry) else entry

    return handler


def sitemap_loop_site() -> Handler:
    """`/sitemap.xml` is a sitemapindex that references itself forever."""
    sitemap = _xml(
        """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://careers.example.test/sitemap.xml</loc></sitemap>
</sitemapindex>"""
    )
    careers = _html('<html><body>Careers at Acme. <a href="/jobs">Open roles</a></body></html>')
    return _router(
        {
            "/robots.txt": _xml(_ROBOTS_OK),
            "/sitemap.xml": sitemap,
            "/careers": careers,
            "/jobs": _html("<html><body>No ATS signature here.</body></html>"),
        }
    )


def redirect_to_private_ip_site() -> Handler:
    """`/careers` 302s to an allowlisted subdomain that resolves to a private IP; the
    crawler must refuse before following, not because the host is off the allowlist."""
    redirect = httpx.Response(
        302, headers={"location": "https://internal.careers.example.test/internal-admin"}
    )
    return _router(
        {
            "/robots.txt": _xml(_ROBOTS_OK),
            "/sitemap.xml": _xml(
                '<?xml version="1.0"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
            ),
            "/careers": redirect,
        }
    )


def robots_unavailable_site() -> Handler:
    """`robots.txt` always 500s; discovery must suspend, never guess "allowed"."""
    return _router(
        {
            "/robots.txt": httpx.Response(500, content=b"internal error"),
            "/careers": _html("<html><body>Should never be reached.</body></html>"),
        }
    )


def unsafe_sitemap_site() -> Handler:
    """The sitemap declares a DOCTYPE/ENTITY — refused before any XML parser sees it."""
    unsafe = _xml(
        """<?xml version="1.0"?>
<!DOCTYPE urlset [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>&xxe;</loc></url>
</urlset>"""
    )
    return _router(
        {
            "/robots.txt": _xml(_ROBOTS_OK),
            "/sitemap.xml": unsafe,
            "/careers": _html("<html><body>Careers</body></html>"),
        }
    )


def dynamic_shell_site() -> Handler:
    """`/careers` is a near-empty React shell: evidence of client-side rendering."""
    shell = _html(
        '<html><body><div id="root"></div><script src="/static/bundle.js"></script></body></html>'
    )
    return _router(
        {
            "/robots.txt": _xml(_ROBOTS_OK),
            "/sitemap.xml": _xml(
                '<?xml version="1.0"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
            ),
            "/careers": shell,
        }
    )


def ats_behind_link_site() -> Handler:
    """The careers page has no ATS itself, but links one click deeper to a Greenhouse
    embed — the scenario limited discovery exists for (F20-27 only checks the seed page).
    """
    careers = _html(
        '<html><body>Careers at Acme. <a href="/join-us">Join us</a></body></html>'
    )
    join_us = _html(
        '<html><body><iframe src="https://boards.greenhouse.io/acme"></iframe></body></html>'
    )
    return _router(
        {
            "/robots.txt": _xml(_ROBOTS_OK),
            "/sitemap.xml": _xml(
                '<?xml version="1.0"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
            ),
            "/careers": careers,
            "/join-us": join_us,
        }
    )


def robots_disallow_site() -> Handler:
    """`robots.txt` explicitly disallows `/careers`."""
    return _router(
        {
            "/robots.txt": _xml("User-agent: *\nDisallow: /careers\n"),
            "/careers": _html("<html><body>Should never be reached.</body></html>"),
        }
    )


def identifying_query_site() -> Handler:
    """`/sitemap.xml` lists two job pages that differ only by their identifying query."""
    return _router(
        {
            "/robots.txt": _xml(_ROBOTS_OK),
            "/sitemap.xml": _xml(
                """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://careers.example.test/careers/job?id=1</loc></url>
  <url><loc>https://careers.example.test/careers/job?id=2</loc></url>
</urlset>"""
            ),
            "/careers": _html("<html><body>Careers</body></html>"),
            "/careers/job": _html("<html><body>A single role.</body></html>"),
        }
    )


def sitemap_with_noise_site() -> Handler:
    """The sitemap lists one relevant URL (`/careers/team`, a Greenhouse embed) and one
    irrelevant one (`/blog/launch`). The careers page itself has no ATS signature, so a
    hit here only comes from the sitemap follow-up — proving the stricter sitemap keyword
    filter (F20-36 follow-up) let the relevant URL through without needing the broader
    same-page-link hints. `/blog/launch` raises if ever fetched, so a test proves the
    tighter filter kept it out of the crawl entirely by the absence of that error.
    """

    def _never(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("the stricter sitemap keyword filter should have excluded this URL")

    return _router(
        {
            "/robots.txt": _xml(_ROBOTS_OK),
            "/sitemap.xml": _xml(
                """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://careers.example.test/careers/team</loc></url>
  <url><loc>https://careers.example.test/blog/launch</loc></url>
</urlset>"""
            ),
            "/careers": _html("<html><body>Careers at Acme.</body></html>"),
            "/careers/team": _html(
                '<html><body><iframe src="https://boards.greenhouse.io/acme"></iframe></body></html>'
            ),
            "/blog/launch": _never,
        }
    )


def fake_resolve_ips(host_ips: dict[str, str] | None = None) -> Callable:
    """An injectable `resolve_ips` that never hits real DNS (`*.example.test` never
    resolves in reality). Every host in `host_ips` answers its mapped IP; anything else
    answers nothing, which `is_public_destination` treats as unsafe. Defaults to `HOST`
    resolving to `PUBLIC_IP`.
    """
    mapping = host_ips if host_ips is not None else {HOST: PUBLIC_IP}

    async def resolve(host: str) -> tuple[str, ...]:
        ip = mapping.get(host)
        return (ip,) if ip else ()

    return resolve
