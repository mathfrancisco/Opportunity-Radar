"""A Workable-shaped careers widget for the autonomous-cycle gate.

Same purpose as `fake_job_board.py` (Greenhouse-shaped) and `fake_workday_board.py`
(Workday-shaped): the gate needs a source it can actually reach without depending on a
real account's uptime or its postings staying put. Workable's public widget is
`GET /api/v1/widget/accounts/<account>?details=true` — see
`docs/pesquisas/termos-workable.md`. Unlike Workday and Lever, the widget has no
pagination: one request answers with every active job for the account.

Accounts served:
  * `radar-ci` answers a two-job listing that matches the CI profile, in one response.
  * `rate-limited` answers 429 with `Retry-After: 1` on the first call, then 200 with an
    empty job list — for exercising the collector's retry path against something real.
  * `broken` answers 500.
  * anything else answers 404, same as an unknown Greenhouse board.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEALTHY_ACCOUNT = "radar-ci"
RATE_LIMITED_ACCOUNT = "rate-limited"
BROKEN_ACCOUNT = "broken"

JOBS = [
    {
        "id": "RADAR-1",
        "title": "Senior Python Engineer",
        "url": "https://apply.workable.com/radar-ci/j/RADAR-1/",
        "location": {"location_str": "Remote", "telecommuting": True},
        "full_description": "<p>Build the radar.</p>",
        "published_on": "2026-09-01",
    },
    {
        "id": "RADAR-2",
        "title": "Site Reliability Engineer",
        "url": "https://apply.workable.com/radar-ci/j/RADAR-2/",
        "location": {"location_str": "Remote", "telecommuting": True},
        "full_description": "<p>Keep the radar up.</p>",
        "published_on": "2026-09-02",
    },
]

_rate_limit_calls = 0


class WorkableBoardStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global _rate_limit_calls
        path = self.path.split("?", 1)[0]
        expected_prefix = "/api/v1/widget/accounts/"
        if not path.startswith(expected_prefix):
            self.send_error(404)
            return
        account = path[len(expected_prefix) :]
        if account == BROKEN_ACCOUNT:
            self.send_error(500)
            return
        if account == RATE_LIMITED_ACCOUNT:
            _rate_limit_calls += 1
            if _rate_limit_calls == 1:
                self.send_response(429)
                self.send_header("Retry-After", "1")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._respond({"jobs": []})
            return
        if account != HEALTHY_ACCOUNT:
            self.send_error(404)
            return
        self._respond({"jobs": JOBS})

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
    ThreadingHTTPServer(("0.0.0.0", 8479), WorkableBoardStubHandler).serve_forever()
