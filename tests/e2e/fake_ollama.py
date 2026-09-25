import hashlib
import json
import math
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


def analysis_for(request: dict) -> dict:
    """Answer in the shape the request's schema asks for.

    `analysis-v2` wants each strength and risk as a claim with the passage behind it, and
    the adapter refuses a passage that is not in the payload it sent. So the stub quotes
    the posting title it received, which is always there, and leaves the risk without a
    passage, as an inference. `analysis-v1` gets the plain strings it always did.
    """
    schema = request.get("format") or {}
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


EMBEDDING_DIMENSIONS = 1024


def embedding(text: str) -> list[float]:
    """A deterministic unit vector derived from the text, like the real model's shape."""
    values: list[float] = []
    counter = 0
    while len(values) < EMBEDDING_DIMENSIONS:
        digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
        values.extend((byte - 127.5) / 127.5 for byte in digest)
        counter += 1
    values = values[:EMBEDDING_DIMENSIONS]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


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
        body = self.rfile.read(length)
        if self.path == "/api/embed":
            request = json.loads(body or b"{}")
            inputs = request.get("input") or []
            texts = [inputs] if isinstance(inputs, str) else list(inputs)
            self._respond(
                {
                    "model": request.get("model", "qwen3-embedding:0.6b"),
                    "embeddings": [embedding(str(text)) for text in texts],
                    "total_duration": 40_000_000,
                    "load_duration": 5_000_000,
                    "prompt_eval_count": sum(len(str(text)) // 4 for text in texts),
                }
            )
        elif self.path == "/api/chat":
            self._respond(
                {
                    "model": "qwen3:8b-q4_K_M",
                    "done": True,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(analysis_for(json.loads(body or b"{}"))),
                    },
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
