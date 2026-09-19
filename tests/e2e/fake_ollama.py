import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The analysis model stays absent from /api/tags so health keeps reporting "degraded",
# while /api/chat answers a schema-valid analysis. That combination is what the compose
# smoke test needs: a semantic layer that works without pulling a real model in CI.
ANALYSIS = {
    "summary": "Remote senior Python role that matches the active profile stack.",
    "strengths": ["Required Python and React experience is present in the profile"],
    "risks": ["Country eligibility is not stated in the posting"],
    "inferences": [],
    "unknowns": ["Timezone overlap requirement"],
    "recommended_review": False,
}


class OllamaStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/api/tags":
            self.send_error(404)
            return

        self._respond({"models": []})

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._respond(
            {
                "model": "llama3.2:3b",
                "done": True,
                "message": {"role": "assistant", "content": json.dumps(ANALYSIS)},
            }
        )

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
    ThreadingHTTPServer(("0.0.0.0", 11434), OllamaStubHandler).serve_forever()
