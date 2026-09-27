"""A Greenhouse-shaped job board for the autonomous-cycle gate and F20-47's browser E2E.

The gate has to prove that the worker collects on its own, which needs a source it can
actually reach. Pointing it at a real board would make the gate depend on a third party's
uptime and on that company's postings staying the same, so the board is served locally and
returns a fixed payload.

Two boards are served:
  * `radar-ci` answers a single posting that matches the CI profile.
  * anything else answers 404, so a failing source can be exercised alongside a healthy
    one and the pass can be shown to survive it.

F20-47 needs two more failure shapes injected into a running browser journey, without
restarting the container (a restart would drop an in-flight collection): a manifest whose
`meta.total` overstates the jobs actually returned (a truncated/partial page), and a
conditional `304 Not Modified` reply to `If-None-Match`. Both are driven by the same
runtime control file as `fake_groq.py`'s `FAKE_GROQ_MODE`, flipped with
`docker compose exec ... sh -c 'echo partial > /tmp/fake_board_mode'`.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEALTHY_BOARD = "radar-ci"
ETAG = '"radar-ci-v1"'

MODE_FILE = os.environ.get("FAKE_BOARD_MODE_FILE", "/tmp/fake_board_mode")

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

#: The "next page" job a truncated manifest claims exists but never returns, proving the
#: pipeline does not fabricate an item nor close the one it already has when a manifest's
#: `meta.total` overstates what came back.
_UNDELIVERED_JOB_COUNT = 1


def current_mode() -> str:
    """`ok`, `partial` (meta.total overstates the returned jobs) or `304`."""
    try:
        with open(MODE_FILE, encoding="utf-8") as handle:
            mode = handle.read().strip()
            if mode:
                return mode
    except OSError:
        pass
    return os.environ.get("FAKE_BOARD_MODE", "ok")


class JobBoardStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path != f"/v1/boards/{HEALTHY_BOARD}/jobs":
            # Greenhouse answers 404 for an unknown board, which the collector classifies
            # as SOURCE_NOT_FOUND. That is the failure the gate needs: real, not a timeout.
            self.send_error(404)
            return

        mode = current_mode()
        if mode == "304" and self.headers.get("If-None-Match") == ETAG:
            self.send_response(304)
            self.send_header("ETag", ETAG)
            self.end_headers()
            return

        total = len(JOBS) + (_UNDELIVERED_JOB_COUNT if mode == "partial" else 0)
        self._respond({"jobs": JOBS, "meta": {"total": total}}, headers={"ETag": ETAG})

    def _respond(self, payload: object, *, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8477), JobBoardStubHandler).serve_forever()
