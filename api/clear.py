# api/clear.py
from http.server import BaseHTTPRequestHandler
import json
import os
import sys

# Resolve project root so imports work from any execution context
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.utils import verify_access_code, KV_REST_API_URL, KV_REST_API_TOKEN
import requests

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
                "ok": False,
                "error": "Unauthorized: Invalid or missing access code."
            }).encode("utf-8"))
            return

        # 2. Resolve session ID and delete history in KV
        session_id = self.headers.get("x-session-id") or self.headers.get("X-Session-ID")
        if session_id and KV_REST_API_URL and KV_REST_API_TOKEN:
            key = f"history:{session_id}"
            headers = {
                "Authorization": f"Bearer {KV_REST_API_TOKEN}"
            }
            try:
                url = f"{KV_REST_API_URL.rstrip('/')}/del/{key}"
                requests.post(url, headers=headers, timeout=5)
            except Exception as e:
                print(f"[WARNING] Vercel KV clear error: {e}")

        # 3. Return success
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
