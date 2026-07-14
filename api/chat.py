"""
api/chat.py — Unified Vercel Python entrypoint.

Routes all incoming requests:
  GET  /              → serves public/index.html
  POST /api/chat      → LLM chat via OpenRouter
  POST /api/command   → /rates and /deadlines from knowledge base
  POST /api/clear     → clears session history
  OPTIONS *           → CORS preflight
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import traceback

STARTUP_ERROR = None
STARTUP_TRACEBACK = ""

try:
    # Resolve project root so imports work
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from api.utils import (
        verify_access_code,
        is_rate_limited,
        get_client_ip,
        get_conversation_history,
        save_conversation_history,
        KV_REST_API_URL,
        KV_REST_API_TOKEN,
    )
    from core import load_knowledge_base, build_system_prompt, chat
    import requests as http_requests

    # ── Startup: load KB and build system prompt once (cold start) ─────────────
    kb = load_knowledge_base()
    SYSTEM_PROMPT = build_system_prompt(kb)
except Exception as e:
    STARTUP_ERROR = e
    STARTUP_TRACEBACK = traceback.format_exc()


def _send_json(handler_inst, status, data):
    """Helper to send a JSON response with CORS headers."""
    body = json.dumps(data).encode("utf-8")
    handler_inst.send_response(status)
    handler_inst.send_header("Content-Type", "application/json")
    handler_inst.send_header("Access-Control-Allow-Origin", "*")
    handler_inst.end_headers()
    handler_inst.wfile.write(body)


def _read_body(handler_inst):
    """Read and parse JSON body from request."""
    length = int(handler_inst.headers.get("Content-Length", 0))
    raw = handler_inst.rfile.read(length)
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ── Route: POST /api/chat ──────────────────────────────────────────────────

def handle_chat(handler_inst):
    if not verify_access_code(handler_inst.headers):
        _send_json(handler_inst, 401, {"reply": None, "error": "Unauthorized: Invalid or missing access code."})
        return

    ip = get_client_ip(handler_inst.headers)
    limited, limit_msg = is_rate_limited(ip)
    if limited:
        _send_json(handler_inst, 429, {"reply": None, "error": limit_msg})
        return

    body = _read_body(handler_inst)
    user_message = str(body.get("message", "")).strip()
    if not user_message:
        _send_json(handler_inst, 400, {"reply": None, "error": "Message cannot be empty."})
        return

    session_id = handler_inst.headers.get("x-session-id") or handler_inst.headers.get("X-Session-ID") or f"ip_{ip}"
    history = get_conversation_history(session_id)

    try:
        reply = chat(user_message, SYSTEM_PROMPT, history)
        save_conversation_history(session_id, history)
        _send_json(handler_inst, 200, {"reply": reply, "error": None})
    except Exception as e:
        _send_json(handler_inst, 200, {"reply": None, "error": str(e)})


# ── Route: POST /api/command ───────────────────────────────────────────────

def handle_command(handler_inst):
    if not verify_access_code(handler_inst.headers):
        _send_json(handler_inst, 401, {"reply": None, "error": "Unauthorized: Invalid or missing access code."})
        return

    ip = get_client_ip(handler_inst.headers)
    limited, limit_msg = is_rate_limited(ip)
    if limited:
        _send_json(handler_inst, 429, {"reply": None, "error": limit_msg})
        return

    body = _read_body(handler_inst)
    command = str(body.get("command", "")).strip().lower()
    if not command:
        _send_json(handler_inst, 400, {"reply": None, "error": "Missing 'command' in request body."})
        return

    local_kb = load_knowledge_base()
    if not local_kb:
        _send_json(handler_inst, 500, {"reply": None, "error": "Knowledge base details are currently unavailable."})
        return

    if command == "/rates":
        reply = _build_rates_response(local_kb)
    elif command == "/deadlines":
        reply = _build_deadlines_response(local_kb)
    elif command == "/help":
        reply = "Access verified."
    else:
        _send_json(handler_inst, 400, {"reply": None, "error": f"Unsupported command: {command}"})
        return

    _send_json(handler_inst, 200, {"reply": reply, "error": None})


def _build_rates_response(kb_data):
    lines = [
        "### Key Ghana Tax Rates",
        "",
        "The following rates are loaded directly from the Ghanaian tax legislation knowledge base:",
        "",
        "| Tax / Item | Rate |",
        "| :--- | :--- |",
    ]
    for item in kb_data.get("key_rates", []):
        lines.append(f"| {item['tax']} | **{item['rate']}** |")
    lines.append("")
    lines.append("*Always verify current rates with GRA at [www.gra.gov.gh](https://www.gra.gov.gh).*")
    return "\n".join(lines)


def _build_deadlines_response(kb_data):
    lines = [
        "### Key Ghana Tax Deadlines",
        "",
        "The following deadlines are loaded directly from the Ghanaian tax legislation knowledge base:",
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


# ── Route: POST /api/clear ─────────────────────────────────────────────────

def handle_clear(handler_inst):
    if not verify_access_code(handler_inst.headers):
        _send_json(handler_inst, 401, {"ok": False, "error": "Unauthorized: Invalid or missing access code."})
        return

    session_id = handler_inst.headers.get("x-session-id") or handler_inst.headers.get("X-Session-ID")
    if session_id and KV_REST_API_URL and KV_REST_API_TOKEN:
        key = f"history:{session_id}"
        headers = {"Authorization": f"Bearer {KV_REST_API_TOKEN}"}
        try:
            url = f"{KV_REST_API_URL.rstrip('/')}/del/{key}"
            http_requests.post(url, headers=headers, timeout=5)
        except Exception as e:
            print(f"[WARNING] Vercel KV clear error: {e}")

    _send_json(handler_inst, 200, {"ok": True})


# ── Unified Handler ────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def handle_startup_error(self):
        if STARTUP_ERROR:
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            error_html = f"""
            <html>
                <head><title>Startup Error</title></head>
                <body style="font-family: sans-serif; padding: 20px; background: #fff5f5; color: #9b2c2c;">
                    <h1>Startup Error Detected</h1>
                    <p><strong>Error:</strong> {STARTUP_ERROR}</p>
                    <pre style="background: #fff; padding: 15px; border: 1px solid #feb2b2; border-radius: 4px; overflow-x: auto;">{STARTUP_TRACEBACK}</pre>
                </body>
            </html>
            """
            self.wfile.write(error_html.encode("utf-8"))
            return True
        return False

    def do_OPTIONS(self):
        if self.handle_startup_error():
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code, X-Session-ID")
        self.end_headers()

    def do_GET(self):
        if self.handle_startup_error():
            return
        index_path = os.path.join(ROOT, "public", "index.html")
        try:
            with open(index_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        if self.handle_startup_error():
            return
        path = self.path.split("?")[0].rstrip("/")

        if path == "/api/chat":
            handle_chat(self)
        elif path == "/api/command":
            handle_command(self)
        elif path == "/api/clear":
            handle_clear(self)
        else:
            _send_json(self, 404, {"error": f"Unknown route: {path}"})