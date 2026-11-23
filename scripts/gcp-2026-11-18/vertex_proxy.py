"""Loopback OpenAI-compatible proxy to Vertex AI using the VM service-account token.

Lets unmodified OpenAI-style benchmark clients call Gemini on Vertex without a
credential in any command line, config or log: the token is fetched from the
GCE metadata server, cached until shortly before expiry and only ever sent to
aiplatform.googleapis.com. Binds 127.0.0.1 only.

usage: vertex_proxy.py PORT USAGE_JSONL REASONING_EFFORT MODEL
Every request is pinned to MODEL (native runners send a local checkpoint path)
and gets the same ``reasoning_effort`` unless the client set one, so thinking
tokens cannot consume the answer budget differently across arms. Status,
latency and provider token usage are appended per request.
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROJECT = "optimum-zone"
UPSTREAM = (f"https://aiplatform.googleapis.com/v1/projects/{PROJECT}"
            "/locations/global/endpoints/openapi/chat/completions")
METADATA = ("http://metadata.google.internal/computeMetadata/v1/instance/"
            "service-accounts/default/token")
_lock = threading.Lock()
_token = {"value": None, "expires": 0.0}


def token() -> str:
    with _lock:
        if _token["value"] is None or time.time() > _token["expires"] - 120:
            request = urllib.request.Request(METADATA, headers={"Metadata-Flavor": "Google"})
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.load(response)
            _token["value"] = payload["access_token"]
            _token["expires"] = time.time() + float(payload["expires_in"])
        return _token["value"]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        payload = json.loads(body)
        payload["model"] = MODEL
        payload.setdefault("reasoning_effort", EFFORT)
        request = urllib.request.Request(UPSTREAM, data=json.dumps(payload).encode(), method="POST", headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + token()})
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                status, data = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, data = error.code, error.read()
        usage = None
        try:
            usage = json.loads(data).get("usage")
        except (ValueError, AttributeError):
            pass
        with _lock, open(USAGE_LOG, "a") as log:
            log.write(json.dumps({"at": started, "latency_ms": int((time.time() - started) * 1000),
                                  "status": status, "model": payload.get("model"),
                                  "images": sum(1 for m in payload.get("messages", [])
                                                if isinstance(m.get("content"), list)
                                                for c in m["content"] if c.get("type") == "image_url"),
                                  "usage": usage}) + "\n")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))


if __name__ == "__main__":
    USAGE_LOG = sys.argv[2]
    EFFORT = sys.argv[3]
    MODEL = sys.argv[4]
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
