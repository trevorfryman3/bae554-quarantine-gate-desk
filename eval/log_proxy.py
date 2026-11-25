"""Debug relay: log what a client (Hermes) sends to local Ollama, then pass it through unchanged.

  python eval/log_proxy.py [--port 11435] [--log .private_hermes/requests.jsonl]
  hermes chat ... --provider custom --base-url http://127.0.0.1:11435/v1 ...

Binds to 127.0.0.1 only and forwards only to http://127.0.0.1:11434. Logs each request path and JSON body
(never headers, so no Authorization value is written). The log goes under .private* (git-ignored).
Answers the parity question "does Hermes send a `tools` array to the model at all?".
shortcut: buffers each upstream response before relaying it, so streaming arrives in one piece; debug use only.
"""
import argparse
import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = "http://127.0.0.1:11434"


def summary(body):
    try:
        req = json.loads(body)
    except ValueError:
        return {"unparsed_bytes": len(body)}
    tools = req.get("tools") or []
    return {"model": req.get("model"), "stream": req.get("stream"), "n_messages": len(req.get("messages") or []),
            "n_tools": len(tools), "tool_names": [(t.get("function") or {}).get("name") for t in tools],
            "tool_choice": req.get("tool_choice"), "body": req}


class Relay(BaseHTTPRequestHandler):
    log_path = None

    def _relay(self, body=None):
        if body is not None:
            s = summary(body)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict(path=self.path, **s), ensure_ascii=False) + "\n")
            print(f"{self.path}: model={s.get('model')} tools={s.get('n_tools')} {s.get('tool_names')}", flush=True)
        req = urllib.request.Request(UPSTREAM + self.path, data=body, method=self.command,
                                     headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                status, ctype, data = r.status, r.headers.get("Content-Type", "application/json"), r.read()
        except urllib.error.HTTPError as e:
            status, ctype, data = e.code, e.headers.get("Content-Type", "application/json"), e.read()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._relay()

    def do_POST(self):
        self._relay(self.rfile.read(int(self.headers.get("Content-Length", 0))))

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11435)
    ap.add_argument("--log", default=".private_hermes/requests.jsonl")
    a = ap.parse_args()
    Path(a.log).parent.mkdir(parents=True, exist_ok=True)
    Relay.log_path = a.log
    print(f"relaying 127.0.0.1:{a.port} -> {UPSTREAM}; logging to {a.log} (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Relay).serve_forever()
