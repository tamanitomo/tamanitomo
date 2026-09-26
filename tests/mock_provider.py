"""Loopback-only provider for synthetic workspace previews; no live inference."""

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

PUBLIC_TEXT = "Hello there. I kept the kettle warm."


class MockProvider:
    """Serve a deterministic completion or its streamed deltas with a temporary key."""

    def __init__(self):
        self.token = secrets.token_urlsafe(24)
        self.server = None
        self.thread = None

    def __enter__(self):
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def send_json(self, status, payload):
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if urlsplit(self.path).path != "/v1/chat/completions":
                    return self.send_json(404, {"error": "not found"})
                if self.headers.get("Authorization") != "Bearer " + provider.token:
                    return self.send_json(401, {"error": "bad token"})
                try:
                    body = json.loads(
                        self.rfile.read(int(self.headers.get("Content-Length") or 0))
                    )
                except (ValueError, TypeError):
                    return self.send_json(400, {"error": "invalid request"})
                if not body.get("stream"):
                    return self.send_json(
                        200, provider.completion(body.get("model", "deltas"))
                    )
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    for start in range(0, len(PUBLIC_TEXT), 7):
                        chunk = {
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "content": PUBLIC_TEXT[start : start + 7]
                                    },
                                    "finish_reason": None,
                                }
                            ]
                        }
                        self.wfile.write(
                            b"data: " + json.dumps(chunk).encode("utf-8") + b"\n\n"
                        )
                        self.wfile.flush()
                    self.wfile.write(
                        b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
                    )
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True
        )
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    @property
    def url(self):
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    @staticmethod
    def completion(model="deltas"):
        return {
            "id": "preview-completion",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": PUBLIC_TEXT},
                    "finish_reason": "stop",
                }
            ],
        }

    def hermes_config(self, scenario="deltas"):
        return (
            "model:\n"
            f"  default: {scenario}\n"
            "  provider: custom\n"
            f"  base_url: {self.url}\n"
            "  api_key_env: MOCK_PROVIDER_KEY\n"
            "fallback_providers: []\n"
        )
