# api/command.py
from http.server import BaseHTTPRequestHandler
import json
import os
import sys

# Resolve project root so imports work from any execution context
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.utils import verify_access_code, is_rate_limited, get_client_ip
from api.core import load_knowledge_base

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Code, X-Session-ID")
        self.end_headers()

    def do_POST(self):
        # 1. Access Code Verification
        if not verify_access_code(self.headers):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "reply": None,
                "error": "Unauthorized: Invalid or missing access code."
            }).encode("utf-8"))
            return

        # 2. Rate Limiting Check
        ip = get_client_ip(self.headers)
        limited, limit_msg = is_rate_limited(ip)
        if limited:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "reply": None,
                "error": limit_msg
            }).encode("utf-8"))
            return

        # 3. Read request body
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length)
        try:
            body = json.loads(body_bytes)
        except Exception:
            body = {}

        command = str(body.get("command", "")).strip().lower()
        if not command:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "reply": None,
                "error": "Missing 'command' in request body."
            }).encode("utf-8"))
            return

        # 4. Load the knowledge base JSON
        kb = load_knowledge_base()
        if not kb:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "reply": None,
                "error": "Knowledge base details are currently unavailable."
            }).encode("utf-8"))
            return

        # 5. Extract requested tables
        if command == "/rates":
            reply = self.build_rates_response(kb)
        elif command == "/deadlines":
            reply = self.build_deadlines_response(kb)
        else:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "reply": None,
                "error": f"Unsupported command: {command}"
            }).encode("utf-8"))
            return

        # 6. Return response
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({
            "reply": reply,
            "error": None
        }).encode("utf-8"))

    def build_rates_response(self, kb) -> str:
        lines = [
            "### Key Ghana Tax Rates",
            "",
            "The following rates are loaded directly from the Ghanaian tax legislation knowledge base:",
            "",
            "| Tax / Item | Rate |",
            "| :--- | :--- |"
        ]
        for item in kb.get("key_rates", []):
            lines.append(f"| {item['tax']} | **{item['rate']}** |")
        lines.append("")
        lines.append("*Always verify current rates with GRA at [www.gra.gov.gh](https://www.gra.gov.gh).*")
        return "\n".join(lines)

    def build_deadlines_response(self, kb) -> str:
        lines = [
            "### Key Ghana Tax Deadlines",
            "",
            "The following deadlines are loaded directly from the Ghanaian tax legislation knowledge base:",
            "",
            "| Obligation | Deadline | Legislation |",
            "| :--- | :--- | :--- |"
        ]
        for item in kb.get("key_deadlines", []):
            legislation = item.get("legislation", "")
            lines.append(f"| {item['obligation']} | **{item['deadline']}** | *{legislation}* |")
        lines.append("")
        lines.append("*Always verify deadlines with GRA at [www.gra.gov.gh](https://www.gra.gov.gh).*")
        return "\n".join(lines)
