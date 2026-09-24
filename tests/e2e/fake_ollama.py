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


# Fixed costs in nanoseconds, as the real server reports them, so the pipeline proves the
# analysis records what a call cost.
COST = {
    "total_duration": 1_250_000_000,
    "load_duration": 50_000_000,
    "prompt_eval_count": 640,
    "prompt_eval_duration": 300_000_000,
    "eval_count": 120,
    "eval_duration": 900_000_000,
}


class OllamaStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/tags":
            self._respond({"models": []})
        elif self.path == "/api/version":
            self._respond({"version": "0.34.4"})
        elif self.path == "/api/ps":
            self._respond({"models": []})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        if self.path == "/api/chat":
            self._respond(
                {
                    "model": "qwen3:8b-q4_K_M",
                    "done": True,
                    "message": {"role": "assistant", "content": json.dumps(ANALYSIS)},
                    **COST,
                }
            )
        elif self.path == "/api/generate":
            # Warm-up: an empty prompt loads the model and generates nothing.
            self._respond(
                {"model": "qwen3:8b-q4_K_M", "done": True, "load_duration": 50_000_000}
            )
        else:
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
    ThreadingHTTPServer(("0.0.0.0", 11434), OllamaStubHandler).serve_forever()
