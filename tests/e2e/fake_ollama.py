from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class OllamaStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/api/tags":
            self.send_error(404)
            return

        payload = b'{"models": []}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 11434), OllamaStubHandler).serve_forever()
