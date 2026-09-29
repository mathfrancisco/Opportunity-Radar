"""A Factorial-shaped career page for the autonomous-cycle gate.

Same purpose as `fake_job_board.py` (a local stand-in so the gate does not depend on a real
company's board staying up or unchanged), shaped like Factorial's public careers page
instead of Greenhouse's JSON API.

Real Factorial has no JSON endpoint (`docs/pesquisas/termos-factorial.md`): the board is a
server-rendered HTML page with one `<li class="job-offer-item">` per job, carrying the
collector's inputs in `data-*` attributes and three ordered `<div>` labels (title, team,
location). This stub reproduces that shape closely enough for
`FactorialCollector` to parse it, and takes an explicit `fail` query parameter to exercise
the error paths the sub-card needs — a query parameter the real page does not have, but the
collector never reads request query parameters back out of a response, so this does not
change what the collector under test sees.

  * `GET /` answers a fixed two-job HTML page.
  * `GET /?fail=404` answers 404 (unknown/deleted board).
  * `GET /?fail=429` answers 429 with `Retry-After: 2`.
  * `GET /?fail=500` answers 500 (upstream error).
  * `GET /?fail=schema` answers 200 with a page missing the job-filters marker (not a
    jobs-listing page at all), which the collector must never mistake for zero postings.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

_JOB_1_URL = "https://jobs.example.test/job_posting/senior-python-engineer-4242"
_JOB_2_URL = "https://jobs.example.test/job_posting/hr-analyst-4243"

_JOB_ITEMS = f"""
<li class='job-offer-item w-full' data-contract-type='indefinite'
    data-is-remote='true' data-job-postings-url='{_JOB_1_URL}'
    data-location-id='1' data-team-id='1'>
<div class='mb-4'><div class='md:flex'>
<span class='md:w-3/6'><div class="text-sm font-bold factorial__headingFontFamily">
Senior Python Engineer</div></span>
<div class='flex-grow'><div class="text-sm text-gray-350">Engineering</div></div>
<div class='flex-grow'><div class="text-sm text-gray-350">Remote</div></div>
</div></div>
</li>
<li class='job-offer-item w-full' data-contract-type='indefinite'
    data-is-remote='false' data-job-postings-url='{_JOB_2_URL}'
    data-location-id='2' data-team-id='2'>
<div class='mb-4'><div class='md:flex'>
<span class='md:w-3/6'><div class="text-sm font-bold factorial__headingFontFamily">
HR Analyst</div></span>
<div class='flex-grow'><div class="text-sm text-gray-350">People</div></div>
<div class='flex-grow'><div class="text-sm text-gray-350">Sao Paulo, BR</div></div>
</div></div>
</li>
"""

PAGE = f"""<!DOCTYPE html>
<html><head><title>Radar CI - Job offers, offices and team</title></head>
<body>
<div data-controller='job-filters'>
<select id='team_filter' name='team_filter'><option value=''>All teams</option></select>
<select id='contract_filter' name='contract_filter'>
<option value=''>All contract types</option></select>
<ul class='w-full text-left'>
{_JOB_ITEMS}
</ul>
</div>
</body></html>"""

# Missing the job-filters marker entirely: a schema/redirect surprise, never zero postings.
SCHEMA_CHANGED_PAGE = """<!DOCTYPE html>
<html><head><title>Radar CI</title></head><body><p>Nothing here.</p></body></html>"""


class FactorialBoardStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != "/":
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
        if failure == "schema":
            self._respond_html(SCHEMA_CHANGED_PAGE)
            return
        self._respond_html(PAGE)

    def _respond_html(self, page: str) -> None:
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
    ThreadingHTTPServer(("0.0.0.0", 8479), FactorialBoardStubHandler).serve_forever()
