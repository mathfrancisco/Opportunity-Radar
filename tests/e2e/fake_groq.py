"""Fake Groq server for end-to-end smoke tests (card F20-17, failure modes F20-47).

Answers the OpenAI-compatible chat-completions endpoint the real `GroqProvider` calls,
with a schema-valid analysis and the `x-ratelimit-*` headers the Quota Guard reads. Port
8080 and the `/openai/v1/chat/completions` path mirror how `GROQ_BASE_URL` would point at
this stub in `compose.ci.yaml`, the only place it runs.

F20-47 needs to inject Groq failures (429, 500, an invalid/malformed body) into a running
browser journey without restarting the container — a restart would drop the connection the
browser test is mid-way through. The mode is a plain file instead of an env var so it can be
flipped at runtime with a `docker compose exec ... sh -c 'echo 429 > /tmp/fake_groq_mode'`
from the host. `FAKE_GROQ_MODE` still sets the starting mode for a fresh container.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE_FILE = os.environ.get("FAKE_GROQ_MODE_FILE", "/tmp/fake_groq_mode")


def current_mode() -> str:
    """The live failure mode: `ok`, `429`, `500` or `invalid`.

    Reads the control file on every request so a test can flip it mid-run; falls back to
    `FAKE_GROQ_MODE` (default `ok`) when the file has never been written.
    """
    try:
        with open(MODE_FILE, encoding="utf-8") as handle:
            mode = handle.read().strip()
            if mode:
                return mode
    except OSError:
        pass
    return os.environ.get("FAKE_GROQ_MODE", "ok")

ANALYSIS = {
    "summary": "Remote senior Python role that matches the active profile stack.",
    "strengths": ["Required Python and React experience is present in the profile"],
    "risks": ["Country eligibility is not stated in the posting"],
    "inferences": [],
    "unknowns": ["Timezone overlap requirement"],
    "recommended_review": False,
}

#: Fixed usage the pipeline can assert on, in the shape Groq's `usage` block reports.
USAGE = {
    "prompt_tokens": 2100,
    "completion_tokens": 422,
    "total_tokens": 2522,
    "prompt_time": 0.12,
    "completion_time": 0.81,
    "total_time": 0.93,
}

#: Soft-limit headroom the Quota Guard's `remaining_*_reported` columns read.
RATE_LIMIT_HEADERS = {
    "x-ratelimit-limit-requests": "1000",
    "x-ratelimit-limit-tokens": "200000",
    "x-ratelimit-remaining-requests": "999",
    "x-ratelimit-remaining-tokens": "199000",
    "x-ratelimit-reset-requests": "2m59.56s",
    "x-ratelimit-reset-tokens": "7.66s",
}


def analysis_for(request: dict) -> dict:
    """Answer in the shape the request's `response_format.json_schema` asks for.

    `analysis-v2` wants each strength and risk as a claim with the passage behind it, and
    the adapter refuses a passage that is not in the payload it sent. So the stub quotes
    the posting title it received, which is always there, and leaves the risk without a
    passage, as an inference. `analysis-v1` gets the plain strings it always did.
    """
    response_format = request.get("response_format") or {}
    schema = (response_format.get("json_schema") or {}).get("schema") or {}
    strengths = (schema.get("properties") or {}).get("strengths") or {}
    if (strengths.get("items") or {}).get("type") != "object":
        return ANALYSIS
    messages = request.get("messages") or []
    user = json.loads(messages[-1]["content"]) if messages else {}
    title = (user.get("posting") or {}).get("title") or ""
    return {
        "summary": "Vaga sênior remota em Python compatível com o perfil ativo.",
        "strengths": [
            {
                "claim": "O título da vaga corresponde ao perfil",
                "evidence": title or None,
                "source": "posting" if title else None,
            }
        ],
        "risks": [
            {
                "claim": "Provavelmente não informa os países aceitos",
                "evidence": None,
                "source": None,
            }
        ],
        "inferences": [],
        "unknowns": ["Sobreposição de fuso exigida"],
        "recommended_review": False,
    }


#: A schema-invalid body: valid JSON, but missing every field `analysis-v1`/`analysis-v2`
#: require, so the adapter's own validation fails it rather than the transport layer.
INVALID_ANALYSIS = {"unexpected": "this is not an analysis"}


class GroqStubHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        if self.path != "/openai/v1/chat/completions":
            self.send_error(404)
            return

        mode = current_mode()
        if mode == "429":
            self._respond(
                {"error": {"message": "rate limit exceeded", "type": "rate_limit_error"}},
                status=429,
                headers={**RATE_LIMIT_HEADERS, "Retry-After": "1"},
            )
            return
        if mode == "500":
            self._respond(
                {"error": {"message": "internal error", "type": "server_error"}},
                status=500,
            )
            return

        request = json.loads(body or b"{}")
        content = (
            json.dumps(INVALID_ANALYSIS)
            if mode == "invalid"
            else json.dumps(analysis_for(request))
        )
        self._respond(
            {
                "model": request.get("model", "openai/gpt-oss-120b"),
                "choices": [
                    {
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": USAGE,
            },
            headers=RATE_LIMIT_HEADERS,
        )

    def _respond(
        self, payload: object, *, status: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), GroqStubHandler).serve_forever()
