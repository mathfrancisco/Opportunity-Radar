"""A Teamtailor-shaped career site for the autonomous-cycle gate.

Same purpose as `fake_job_board.py` (a local stand-in so the gate does not depend on a real
company's board staying up or unchanged), shaped like Teamtailor's public feed instead of
Greenhouse's.

Real Teamtailor keys a board by the whole career-site hostname, not by a path segment
(`docs/pesquisas/termos-teamtailor.md`), so there is no board slug to switch on the way
`fake_job_board.py` switches on `/v1/boards/<slug>/jobs`. This stub instead answers the one
real path, `/jobs.json`, and takes an explicit `fail` query parameter to exercise the error
paths the sub-card needs — a query parameter the real feed does not have, but the collector
never reads request query parameters back out of a response, so this does not change what
the collector under test sees.

  * `GET /jobs.json` answers the fixed JSON Feed 1.1 payload below (two published jobs).
  * `GET /jobs.json?fail=404` answers 404 (unknown/deleted board).
  * `GET /jobs.json?fail=429` answers 429 with `Retry-After: 2`.
  * `GET /jobs.json?fail=500` answers 500 (upstream error).
  * anything else answers 404.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

JOBS_PATH = "/jobs.json"

FEED = {
    "version": "https://jsonfeed.org/version/1.1",
    "title": "Radar CI",
    "home_page_url": "https://jobs.example.test/",
    "feed_url": f"https://jobs.example.test{JOBS_PATH}",
    "items": [
        {
            "id": "radar-ci-1",
            "title": "Senior Python Engineer",
            "url": "https://jobs.example.test/jobs/radar-ci-1",
            "date_published": "2026-09-20T12:00:00Z",
            "content_html": "<p>Required: Python and ReactJS. Full-time remote position.</p>",
            "_jobposting": {
                "@context": "https://schema.org",
                "@type": "JobPosting",
                "title": "Senior Python Engineer",
                "hiringOrganization": {"@type": "Organization", "name": "Radar CI"},
                "jobLocation": {
                    "@type": "Place",
                    "address": {"@type": "PostalAddress", "addressCountry": "Remote"},
                },
            },
        }
    ],
}


class TeamtailorBoardStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != JOBS_PATH:
            self.send_error(404)
            return
        failure = parse_qs(parsed.query).get("fail", [None])[0]
        if failure == "404":
            self.send_error(404)
            return
        if failure == "429":
            self._respond_error(429, headers={"Retry-After": "2"})
            return
        if failure == "500":
            self._respond_error(500)
            return
        self._respond(FEED)

    def _respond(self, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _respond_error(self, status: int, *, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8478), TeamtailorBoardStubHandler).serve_forever()
