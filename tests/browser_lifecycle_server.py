"""Manual UI smoke test: isolated mocks only, never use for authentication or deployment.

Run from the project root with `python tests/browser_lifecycle_server.py`. The server
binds to loopback and keeps only synthetic session identifiers in process memory.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
history = {"created": [], "closed": []}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, payload, kind="application/json"):
        raw = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/":
            return self.send((ROOT / "static/index.html").read_text(encoding="utf-8"), "text/html")
        if self.path == "/static/styles.css":
            return self.send((ROOT / "static/styles.css").read_text(encoding="utf-8"), "text/css")
        if self.path == "/static/app.js":
            script = (ROOT / "static/app.js").read_text(encoding="utf-8")
            script = script.replace(
                "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js",
                "/test/firebase-app.js",
            )
            script = script.replace(
                "https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js",
                "/test/firebase-auth.js",
            )
            return self.send(script, "text/javascript")
        if self.path == "/test/firebase-app.js":
            return self.send("export const initializeApp = () => ({});", "text/javascript")
        if self.path == "/test/firebase-auth.js":
            return self.send(
                """export const browserSessionPersistence = {};
export const getAuth = () => ({});
export const setPersistence = async () => {};
export const onAuthStateChanged = (_a, callback) => callback({uid:'test-user', email:'test@example.test', getIdToken:async ()=>'test-token'});
export const signInWithEmailAndPassword = async () => {};
export const signOut = async () => {};""",
                "text/javascript",
            )
        if self.path == "/api/config":
            return self.send(
                json.dumps({"firebase": {"apiKey": "test", "appId": "test", "projectId": "test"}})
            )
        if self.path == "/api/classes":
            return self.send(json.dumps({"classes": ["2° TECH D"]}, ensure_ascii=False))
        if self.path == "/test/state":
            return self.send(json.dumps(history))
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send_error(404)
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        session_id = request["session_id"]
        history["created"].append(session_id)
        return self.send(
            json.dumps(
                {
                    "session_id": session_id,
                    "answer": "Resposta de teste.",
                    "cards": [],
                    "remaining_messages": 49,
                }
            )
        )

    def do_DELETE(self):
        if not self.path.startswith("/api/session/"):
            return self.send_error(404)
        history["closed"].append(self.path.removeprefix("/api/session/"))
        return self.send(json.dumps({"closed": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local-only mock chat UI test server.")
    parser.add_argument("--port", type=int, default=8765)
    port = parser.parse_args().port
    print(f"Mock only: http://127.0.0.1:{port}/ (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
