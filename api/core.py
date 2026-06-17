"""
api/core.py — Shared logic for TaxBot Ghana.

Imported by both taxbot.py (CLI) and server.py (web).
Contains: config, knowledge base loading, system prompt, chat(), session save.
"""

import json
import os
import sys
import datetime
import requests
from dotenv import load_dotenv

# ── Configuration ──────────────────────────────────────────────────────────

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    if not os.environ.get("VERCEL"):
        print(
            "[ERROR] OPENROUTER_API_KEY not found.\n"
            "Create a .env file in this directory with:\n"
            "  OPENROUTER_API_KEY=your_key_here\n"
            "Get your key at https://openrouter.ai/keys"
        )
        sys.exit(1)
    else:
        OPENROUTER_API_KEY = ""

MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-flash-1.5")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
API_HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://taxbot-ghana.local",
    "X-Title": "TaxBot Ghana",
}

MAX_HISTORY_TURNS = 40

# ── Knowledge Base ─────────────────────────────────────────────────────────

# Try to find knowledge_base relative to project root (one level up if inside api folder)
_dir = os.path.dirname(__file__)
if os.path.basename(_dir) == "api":
    _dir = os.path.dirname(_dir)

KB_PATH = os.path.join(
    _dir,
    "knowledge_base",
    "ghana_msme_tax_knowledge_base.json",
)

def load_knowledge_base(path=None):
    path = path or KB_PATH
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"[WARNING] Knowledge base JSON is malformed: {e}")
        return None

# ── System Prompt ──────────────────────────────────────────────────────────

PERSONA_PROMPT = """\
You are TaxBot Ghana, an expert AI assistant specialising in Ghana's tax system for MSMEs (Micro, Small, and Medium Enterprises).

Your users are business owners, sole proprietors, and small company directors who are NOT tax experts. Explain things in plain, clear language. Avoid unnecessary jargon; when you must use a legal term, define it simply.

YOUR KNOWLEDGE SOURCES — use them in this order:
1. THE KNOWLEDGE BASE (injected below) is your primary source for all rates, deadlines, thresholds, act references, and penalties. For any fact involving a number, date, or legal citation, the knowledge base is authoritative. If the knowledge base and your training data conflict, always defer to the knowledge base and flag the discrepancy to the user.
2. YOUR OWN KNOWLEDGE AND CAPABILITIES are secondary. Use them to explain, interpret, and reason about what the knowledge base says in plain language, and to answer questions the knowledge base does not cover. When answering from your own training data rather than the knowledge base, always preface your response with: "This is not covered in my knowledge base, but based on publicly available information —" before giving the answer.
3. IF a question is not covered by the knowledge base, or may have changed since your training cutoff (e.g. budget changes, GRA announcements), tell the user you are answering based on your training data and recommend they verify with GRA directly at www.gra.gov.gh.

RESPONSE STYLE:
- Lead with the direct answer. Don't make users read three paragraphs to find out the rate.
- Use markdown in your responses: **bold** for key terms, bullet lists for multi-part answers, and code blocks for calculations or examples.
- When giving tax rates or deadlines, always cite the relevant Act and section number.
- End answers involving deadlines or penalties with: "Always verify current rates and deadlines with GRA at www.gra.gov.gh."
- If a question is outside your expertise (e.g. legal disputes, court cases), say so clearly and suggest consulting a qualified tax professional.

SCOPE:
- You specialise in Ghana tax but can handle related business and finance questions (cash flow, bookkeeping basics, business structure decisions).
- For non-Ghana tax questions, answer helpfully but briefly, then redirect to your core topic if relevant.

DISCLAIMER TO INCLUDE WHEN RELEVANT:
"This is general guidance based on Ghana's tax legislation and should not be treated as formal legal or professional tax advice. Consult a qualified tax consultant or GRA for advice specific to your situation."
"""

def build_system_prompt(kb):
    if kb is None:
        return PERSONA_PROMPT + "\n\n[Knowledge base unavailable — relying on own capabilities.]"

    kb_text = json.dumps(kb, indent=2)
    return PERSONA_PROMPT + f"""

---

## KNOWLEDGE BASE (Ghana MSME Tax — authoritative reference)

The following is a structured JSON knowledge base extracted from Ghana's primary tax legislation and GRA guidance documents. Treat it as a reliable reference but NOT as the ceiling of your knowledge. Use it to verify rates, deadlines, and act references.

```json
{kb_text}
```
"""

# ── Conversation ───────────────────────────────────────────────────────────

# Web sessions are keyed by session_id; CLI uses a single global list.
# For the web server, pass conversation_history explicitly.

def trim_history(history):
    """Trim in-place to MAX_HISTORY_TURNS, returns the list."""
    if len(history) > MAX_HISTORY_TURNS:
        del history[:-MAX_HISTORY_TURNS]
    return history


def chat(user_message, system_prompt, conversation_history):
    """
    Send user_message to OpenRouter; update conversation_history in-place.
    Returns the assistant's reply string.
    Raises Exception with a user-friendly message on any error.
    """
    conversation_history.append({"role": "user", "content": user_message})
    trim_history(conversation_history)

    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system_prompt}] + conversation_history,
        "temperature": 0.3,
        "max_tokens": 2048,
    }

    # Dynamic headers to ensure we pick up the environment variable at runtime
    api_key = os.getenv("OPENROUTER_API_KEY") or OPENROUTER_API_KEY
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://taxbot-ghana.local",
        "X-Title": "TaxBot Ghana",
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise Exception("Connection timed out. Check your internet connection.")
    except requests.exceptions.HTTPError:
        if response.status_code == 429:
            raise Exception("Rate limit reached. Wait a moment and try again.")
        raise Exception(f"API error {response.status_code}: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        raise Exception("Could not connect to OpenRouter. Check your internet connection.")

    data = response.json()
    try:
        reply = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise Exception("Unexpected response from API — please try again.")

    conversation_history.append({"role": "assistant", "content": reply})
    return reply

# ── Session Save ───────────────────────────────────────────────────────────

def save_session(conversation_history, model=MODEL):
    os.makedirs("sessions", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = f"sessions/session_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(
            {"timestamp": timestamp, "model": model, "messages": conversation_history},
            f,
            indent=2,
        )
    return path
