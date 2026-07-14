"""
server.py — TaxBot Ghana local development web server.

Serves index.html and exposes a JSON API for the chat UI.
Uses only Python stdlib (http.server) and the project's existing dependencies.

Routes:
  GET  /              → serves public/index.html
  POST /api/chat      → {"message": "..."} → {"reply": "...", "error": null}
  POST /api/command   → {"command": "/rates"|"/deadlines"|"/help"} → {"reply": "..."}
  POST /api/clear     → clears server-side conversation history → {"ok": true}

Usage:
  python server.py            # default port 5001
  python server.py 8080       # custom port
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# ── Resolve project root ───────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import load_knowledge_base, build_system_prompt, chat, save_session

# ── Startup ────────────────────────────────────────────────────────────────
kb = load_knowledge_base()
if kb is None:
    print("[WARNING] Knowledge base not found. Server will continue without it.")

SYSTEM_PROMPT = build_system_prompt(kb)

conversation_history = []
history_lock = threading.Lock()

INDEX_PATH = os.path.join(ROOT, "public", "index.html")

# ── Helpers ────────────────────────────────────────────────────────────────

def send_json(handler, status, data):
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)

def send_html(handler, path):
    try:
        with open(path, "rb") as f:
            content = f.read()
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)
    except FileNotFoundError:
        handler.send_response(404)
        handler.end_headers()
        handler.wfile.write(b"index.html not found")

def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None

def build_rates_response(kb_data):
    lines = [
        "### Key Ghana Tax Rates",
        "",
        "The following rates are loaded directly from the knowledge base:",
        "",
        "| Tax / Item | Rate |",
        "| :--- | :--- |",
    ]
    for item in kb_data.get("key_rates", []):
        lines.append(f"| {item['tax']} | **{item['rate']}** |")
    lines.append("")
    lines.append("*Always verify current rates with GRA at [www.gra.gov.gh](https://www.gra.gov.gh).*")
    return "\n".join(lines)

def build_deadlines_response(kb_data):
    lines = [
        "### Key Ghana Tax Deadlines",
        "",
        "The following deadlines are loaded directly from the knowledge base:",
        "",
        "| Obligation | Deadline | Legislation |",
        "| :--- | :--- | :--- |",
    ]
    for item in kb_data.get("key_deadlines", []):
        legislation = item.get("legislation", "")
        lines.append(f"| {item['obligation']} | **{item['deadline']}** | *{legislation}* |")
    lines.append("")
    lines.append("*Always verify deadlines with GRA at [www.gra.gov.gh](https://www.gra.gov.gh).*")
    return "\n".join(lines)

def build_help_response():
    return "\n".join([
        "### Available Commands",
        "",
        "- `/rates` — Display key Ghana tax rates",
        "- `/deadlines` — Display all filing deadlines",
        "- `/clear` — Clear this conversation",
        "- `/help` — Show this help message",
        "",
        "You can also type any tax question in plain language.",
    ])

# ── Request Handler ────────────────────────────────────────────────────────

class TaxBotHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        path = getattr(self, "_path_line", "")
        print(f"  {self.command} {path} → {args[1]}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code, X-Session-ID")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        self._path_line = parsed.path
        if parsed.path in ("/", "/index.html"):
            send_html(self, INDEX_PATH)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        self._path_line = parsed.path

        if parsed.path == "/api/chat":
            self._handle_chat()
        elif parsed.path == "/api/command":
            self._handle_command()
        elif parsed.path == "/api/clear":
            self._handle_clear()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_chat(self):
        body = read_json_body(self)
        if body is None or "message" not in body:
            send_json(self, 400, {"reply": None, "error": "Invalid request body."})
            return

        user_message = str(body["message"]).strip()
        if not user_message:
            send_json(self, 400, {"reply": None, "error": "Message cannot be empty."})
            return

        try:
            with history_lock:
                reply = chat(user_message, SYSTEM_PROMPT, conversation_history)
            send_json(self, 200, {"reply": reply, "error": None})
        except Exception as e:
            send_json(self, 200, {"reply": None, "error": str(e)})

    def _handle_command(self):
        body = read_json_body(self)
        if body is None or "command" not in body:
            send_json(self, 400, {"reply": None, "error": "Missing 'command' in request body."})
            return

        command = str(body["command"]).strip().lower()

        if not kb:
            send_json(self, 500, {"reply": None, "error": "Knowledge base unavailable."})
            return

        if command == "/rates":
            reply = build_rates_response(kb)
        elif command == "/deadlines":
            reply = build_deadlines_response(kb)
        elif command == "/help":
            reply = build_help_response()
        else:
            send_json(self, 400, {"reply": None, "error": f"Unsupported command: {command}"})
            return

        send_json(self, 200, {"reply": reply, "error": None})

    def _handle_clear(self):
        with history_lock:
            conversation_history.clear()
        print("  [clear] Conversation history reset.")
        send_json(self, 200, {"ok": True})


# ── Entry Point ────────────────────────────────────────────────────────────

def run(port=5001):
    server = HTTPServer(("localhost", port), TaxBotHandler)
    print(f"\n  TaxBot Ghana server running at http://localhost:{port}")
    print(f"  Open that URL in your browser.")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        if conversation_history:
            ans = input("  Save this session? (y/n): ").strip().lower()
            if ans == "y":
                path = save_session(conversation_history)
                print(f"  Session saved to {path}")
        print("  Goodbye.")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    run(port)