"""A Workday-shaped career-site backend for the autonomous-cycle gate.

Same purpose as `fake_job_board.py` (Greenhouse-shaped): the gate needs a source it can
actually reach without depending on a real tenant's uptime or its postings staying put.
Workday's public backend is `POST /wday/cxs/<tenant>/<site>/jobs`, offset/limit paginated,
no authentication — see `docs/pesquisas/termos-workday.md`.

Tenants served:
  * `radar-ci` (site `ExternalCareerSite`) answers a two-job, two-page listing that
    matches the CI profile.
  * `rate-limited` answers 429 with `Retry-After: 1` on the first call, then 200 — for
    exercising the collector's retry path against something real.
  * `broken` answers 500.
  * anything else answers 404, same as an unknown Greenhouse board.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEALTHY_TENANT = "radar-ci"
HEALTHY_SITE = "ExternalCareerSite"
RATE_LIMITED_TENANT = "rate-limited"
BROKEN_TENANT = "broken"

JOBS = [
    {
        "title": "Senior Python Engineer",
        "externalPath": "/job/Remote/Senior-Python-Engineer_RADAR-1",
        "locationsText": "Remote",
        "postedOn": "Posted Today",
        "bulletFields": ["RADAR-1"],
    },
    {
        "title": "Site Reliability Engineer",
        "externalPath": "/job/Remote/Site-Reliability-Engineer_RADAR-2",
        "locationsText": "Remote",
        "postedOn": "Posted Today",
        "bulletFields": ["RADAR-2"],
    },
]

_rate_limit_calls = 0


class WorkdayBoardStubHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        global _rate_limit_calls
        path = self.path.split("?", 1)[0]
        expected_prefix = "/wday/cxs/"
        if not path.startswith(expected_prefix):
            self.send_error(404)
            return
        remainder = path[len(expected_prefix) :]
        parts = remainder.split("/")
        if len(parts) != 3 or parts[2] != "jobs":
            self.send_error(404)
            return
        tenant, site = parts[0], parts[1]
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            request_payload = json.loads(body) if body else {}
        except ValueError:
            request_payload = {}
        if tenant == BROKEN_TENANT:
            self.send_error(500)
            return
        if tenant == RATE_LIMITED_TENANT:
            _rate_limit_calls += 1
            if _rate_limit_calls == 1:
                self.send_response(429)
                self.send_header("Retry-After", "1")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._respond({"total": 0, "jobPostings": []})
            return
        if tenant != HEALTHY_TENANT or site != HEALTHY_SITE:
            self.send_error(404)
            return
        offset = int(request_payload.get("offset", 0))
        limit = int(request_payload.get("limit", 20))
        page = JOBS[offset : offset + limit]
        self._respond({"total": len(JOBS), "jobPostings": page})

    def _respond(self, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8478), WorkdayBoardStubHandler).serve_forever()
