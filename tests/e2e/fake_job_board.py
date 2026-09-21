"""A Greenhouse-shaped job board for the autonomous-cycle gate.

The gate has to prove that the worker collects on its own, which needs a source it can
actually reach. Pointing it at a real board would make the gate depend on a third party's
uptime and on that company's postings staying the same, so the board is served locally and
returns a fixed payload.

Two boards are served:
  * `radar-ci` answers a single posting that matches the CI profile.
  * anything else answers 404, so a failing source can be exercised alongside a healthy
    one and the pass can be shown to survive it.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEALTHY_BOARD = "radar-ci"

JOBS = [
    {
        "id": 4242,
        "internal_job_id": 9001,
        "title": "Senior Python Engineer",
        "absolute_url": "https://jobs.example.test/radar-ci/4242",
        "updated_at": "2026-09-20T12:00:00-04:00",
        "requisition_id": "RADAR-1",
        "location": {"name": "Remote"},
        "content": "Required: Python and ReactJS. Full-time remote position.",
        "departments": [{"id": 1, "name": "Engineering"}],
        "offices": [{"id": 1, "name": "Remote"}],
        "metadata": [],
    }
]


class JobBoardStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == f"/v1/boards/{HEALTHY_BOARD}/jobs":
            self._respond({"jobs": JOBS, "meta": {"total": len(JOBS)}})
            return
        # Greenhouse answers 404 for an unknown board, which the collector classifies as
        # SOURCE_NOT_FOUND. That is the failure the gate needs: real, and not a timeout.
        self.send_error(404)

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
    ThreadingHTTPServer(("0.0.0.0", 8477), JobBoardStubHandler).serve_forever()
