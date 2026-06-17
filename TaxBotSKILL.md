# SKILL.md — Ghana MSME Tax CLI Chatbot

## Overview

Build a Python CLI chatbot called **TaxBot Ghana** that helps MSME owners navigate Ghana's tax system. It targets non-expert users — business owners, sole proprietors, and small company directors who need clear, plain-language guidance on income tax, VAT, PAYE, withholding tax, free zones, and compliance obligations.

The LLM backend is **OpenRouter**. The chatbot maintains **multi-turn conversation history** within each session and optionally saves sessions to file. It uses **Rich** for terminal formatting. The knowledge base JSON is a support file — loaded in full at startup into the system prompt — but the LLM's own capabilities are primary; the knowledge base supplements and grounds them with Ghana-specific authoritative data.

---

## Project Structure

```
taxbot-ghana/
├── taxbot.py                          # Main entry point
├── knowledge_base/
│   └── ghana_msme_tax_knowledge_base.json
├── sessions/                          # Auto-created; saved session files
├── .env                               # OPENROUTER_API_KEY lives here
├── requirements.txt
└── README.md
```

---

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| LLM API | OpenRouter (`https://openrouter.ai/api/v1`) |
| Terminal UI | `rich` — panels, markdown rendering, tables |
| HTTP client | `httpx` (async-capable) or `requests` |
| Env management | `python-dotenv` |
| CLI structure | Plain Python (no Click/Typer — keep it simple) |

### requirements.txt

```
rich>=13.0.0
requests>=2.31.0
python-dotenv>=1.0.0
```

---

## API Configuration

### OpenRouter endpoint

```
POST https://openrouter.ai/api/v1/chat/completions
```

### Headers

```python
headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://taxbot-ghana.local",   # required by OpenRouter
    "X-Title": "TaxBot Ghana"                        # shown in OpenRouter dashboard
}
```

### API key loading

Load from a `.env` file at startup using `python-dotenv`. The `.env` file must contain:

```
OPENROUTER_API_KEY=your-openrouter-api-key-here
```

If the key is missing or empty, print a clear error and exit with instructions:

```
[ERROR] OPENROUTER_API_KEY not found.
Create a .env file in this directory with:
  OPENROUTER_API_KEY=your_key_here
Get your key at https://openrouter.ai/keys
```

### Model selection

Default to a capable, cost-effective model. Use:

```python
MODEL = "google/gemini-flash-1.5"   # default — fast, cheap, strong reasoning
```

Allow the user to override via `.env`:

```
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
```

---

## Knowledge Base Loading

At startup, load `knowledge_base/ghana_msme_tax_knowledge_base.json` in full and inject it into the system prompt. This gives the LLM authoritative Ghana-specific data to supplement its own capabilities.

```python
import json

def load_knowledge_base(path="knowledge_base/ghana_msme_tax_knowledge_base.json"):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None   # chatbot still works without it; warn user
    except json.JSONDecodeError as e:
        print(f"[WARNING] Knowledge base JSON is malformed: {e}")
        return None
```

If the knowledge base fails to load, the chatbot continues using the LLM's own capabilities and prints a non-blocking warning.

---

## System Prompt

Construct the system prompt at startup. It has three parts:

### Part 1 — Persona and core instructions

```
You are TaxBot Ghana, an expert AI assistant specialising in Ghana's tax system for MSMEs (Micro, Small, and Medium Enterprises).

Your users are business owners, sole proprietors, and small company directors who are NOT tax experts. Explain things in plain, clear language. Avoid unnecessary jargon; when you must use a legal term, define it simply.

YOUR KNOWLEDGE SOURCES — use them in this order:
1. THE KNOWLEDGE BASE (injected below) is your primary source for all rates, deadlines, thresholds, act references, and penalties. For any fact involving a number, date, or legal citation, the knowledge base is authoritative. If the knowledge base and your training data conflict, always defer to the knowledge base and flag the discrepancy to the user.
2. YOUR OWN KNOWLEDGE AND CAPABILITIES are secondary. Use them to explain, interpret, and reason about what the knowledge base says in plain language, and to answer questions the knowledge base does not cover. When answering from your own training data rather than the knowledge base, make this explicit to the user.
3. IF a question is not covered by the knowledge base, or may have changed since your training cutoff (e.g. budget changes, GRA announcements), tell the user you are answering based on your training data and recommend they verify with GRA directly at www.gra.gov.gh.

RESPONSE STYLE:
- Lead with the direct answer. Don't make users read three paragraphs to find out the rate.
- Use Rich markdown in your responses: **bold** for key terms, bullet lists for multi-part answers, and code blocks for calculations or examples.
- When giving tax rates or deadlines, always cite the relevant Act and section number.
- End answers involving deadlines or penalties with: "⚠ Always verify current rates and deadlines with GRA at www.gra.gov.gh."
- If a question is outside your expertise (e.g. legal disputes, court cases), say so clearly and suggest consulting a qualified tax professional.

SCOPE:
- You specialise in Ghana tax but can handle related business and finance questions (cash flow, bookkeeping basics, business structure decisions).
- For non-Ghana tax questions, answer helpfully but briefly, then redirect to your core topic if relevant.

DISCLAIMER TO INCLUDE WHEN RELEVANT:
"This is general guidance based on Ghana's tax legislation and should not be treated as formal legal or professional tax advice. Consult a qualified tax consultant or GRA for advice specific to your situation."
```

### Part 2 — Knowledge base injection

```python
def build_system_prompt(kb: dict | None) -> str:
    base_prompt = PERSONA_PROMPT   # Part 1 above

    if kb is None:
        return base_prompt + "\n\n[Knowledge base unavailable — relying on own capabilities.]"

    kb_text = json.dumps(kb, indent=2)
    return base_prompt + f"""

---

## KNOWLEDGE BASE (Ghana MSME Tax — authoritative reference)

The following is a structured JSON knowledge base extracted from Ghana's primary tax legislation and GRA guidance documents. Treat it as a reliable reference but NOT as the ceiling of your knowledge. Use it to verify rates, deadlines, and act references.

```json
{kb_text}
```
"""
```

**Important implementation note:** OpenRouter models have large context windows (Gemini Flash supports 1M tokens; Claude 3.5 Sonnet supports 200k). The knowledge base is ~39KB / ~10k tokens — well within limits. Load it fully. Do not truncate.

---

## Conversation History

Maintain full conversation history within a session as a list of message dicts:

```python
conversation_history = []  # persists for the lifetime of the session

def chat(user_message: str) -> str:
    conversation_history.append({"role": "user", "content": user_message})

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + conversation_history,
        "temperature": 0.3,      # lower = more factual, less creative
        "max_tokens": 2048
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=HEADERS,
        json=payload
    )
    response.raise_for_status()

    reply = response.json()["choices"][0]["message"]["content"]
    conversation_history.append({"role": "assistant", "content": reply})
    return reply
```

**Temperature:** Use `0.3`. Tax guidance must be factual and consistent, not creative.

**Context window management:** If conversation history grows very long (>50 turns), trim the oldest turns (not the system prompt) to avoid hitting token limits:

```python
MAX_HISTORY_TURNS = 40  # keep last 40 turns (20 exchanges)

def trim_history():
    global conversation_history
    if len(conversation_history) > MAX_HISTORY_TURNS:
        conversation_history = conversation_history[-MAX_HISTORY_TURNS:]
```

---

## Session Save / Load

After each session, prompt the user to save:

```
Save this session? (y/n):
```

If yes, save to `sessions/session_YYYY-MM-DD_HH-MM-SS.json`:

```python
import datetime, os

def save_session():
    os.makedirs("sessions", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = f"sessions/session_{timestamp}.json"
    with open(path, "w") as f:
        json.dump({
            "timestamp": timestamp,
            "model": MODEL,
            "messages": conversation_history
        }, f, indent=2)
    print(f"Session saved to {path}")
```

---

## CLI Interface and Slash Commands

The main loop reads input, handles slash commands first, then routes to the LLM.

### Slash commands

| Command | Action |
|---|---|
| `/help` | Print all available slash commands |
| `/rates` | Print a formatted table of key tax rates from the knowledge base |
| `/deadlines` | Print a formatted table of all key filing deadlines |
| `/clear` | Clear conversation history for this session |
| `/save` | Save current session immediately |
| `/exit` or `/quit` | Optionally save and exit |

Slash commands are handled **locally in Python** — they do NOT call the LLM. They read directly from the loaded knowledge base JSON and render with Rich.

### `/rates` implementation example

```python
from rich.table import Table
from rich import print as rprint

def cmd_rates(kb):
    if not kb:
        rprint("[yellow]Knowledge base not loaded.[/yellow]")
        return
    table = Table(title="Ghana Key Tax Rates", show_header=True, header_style="bold cyan")
    table.add_column("Tax / Item", style="bold")
    table.add_column("Rate", justify="right")
    for item in kb.get("key_rates", []):
        table.add_row(item["tax"], item["rate"])
    rprint(table)
```

### `/deadlines` implementation example

```python
def cmd_deadlines(kb):
    if not kb:
        rprint("[yellow]Knowledge base not loaded.[/yellow]")
        return
    table = Table(title="Ghana Key Tax Deadlines", show_header=True, header_style="bold cyan")
    table.add_column("Obligation", style="bold")
    table.add_column("Deadline")
    table.add_column("Legislation", style="dim")
    for item in kb.get("key_deadlines", []):
        table.add_row(item["obligation"], item["deadline"], item.get("legislation", ""))
    rprint(table)
```

---

## Main Loop

```python
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

def main():
    console.print(Panel.fit(
        "[bold cyan]TaxBot Ghana[/bold cyan]\n"
        "[dim]Your MSME Tax Assistant — powered by OpenRouter[/dim]\n"
        "Type your question or [bold]/help[/bold] for commands. [bold]/exit[/bold] to quit.",
        border_style="cyan"
    ))

    while True:
        try:
            user_input = console.input("\n[bold green]You:[/bold green] ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input:
            continue

        # Handle slash commands locally
        if user_input.startswith("/"):
            handle_slash_command(user_input, kb)
            continue

        # Call LLM
        with console.status("[dim]Thinking...[/dim]", spinner="dots"):
            try:
                reply = chat(user_input)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                continue

        console.print("\n[bold cyan]TaxBot:[/bold cyan]")
        console.print(Markdown(reply))

    # On exit
    if conversation_history:
        save_prompt = console.input("\n[dim]Save this session? (y/n):[/dim] ").strip().lower()
        if save_prompt == "y":
            save_session()

    console.print("[dim]Goodbye.[/dim]")
```

---

## Error Handling

Handle these cases explicitly:

| Scenario | Behaviour |
|---|---|
| Missing `.env` / API key | Print instructions and exit cleanly |
| Missing knowledge base JSON | Warn and continue without it |
| OpenRouter HTTP error (4xx/5xx) | Print the status code and message; allow user to retry |
| OpenRouter rate limit (429) | Print "Rate limit hit — wait a moment and try again" |
| Network timeout | Print "Connection timed out — check your internet connection" |
| Malformed JSON response | Print "Unexpected response from API — please try again" |
| KeyboardInterrupt | Gracefully exit the loop and offer session save |

```python
import requests

def chat(user_message: str) -> str:
    ...
    try:
        response = requests.post(..., timeout=30)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise Exception("Connection timed out. Check your internet connection.")
    except requests.exceptions.HTTPError as e:
        if response.status_code == 429:
            raise Exception("Rate limit reached. Wait a moment and try again.")
        raise Exception(f"API error {response.status_code}: {response.text[:200]}")
    except requests.exceptions.ConnectionError:
        raise Exception("Could not connect to OpenRouter. Check your internet connection.")
```

---

## README.md Content

The generated README should include:

```markdown
# TaxBot Ghana

AI-powered CLI assistant for Ghana MSME tax queries.

## Setup

1. Clone the repo and install dependencies:
   pip install -r requirements.txt

2. Create a .env file:
   OPENROUTER_API_KEY=your_key_here

3. Place the knowledge base file at:
   knowledge_base/ghana_msme_tax_knowledge_base.json

4. Run:
   python taxbot.py

## Commands
/help       Show all commands
/rates      Show key Ghana tax rates
/deadlines  Show all filing deadlines
/clear      Clear conversation history
/save       Save session to file
/exit       Exit (with save prompt)

## Disclaimer
TaxBot Ghana provides general guidance only.
Always verify with GRA (www.gra.gov.gh) or a qualified tax professional.
```

---

## What NOT to Do

| Don't | Do instead |
|---|---|
| Don't truncate the knowledge base | Load the full JSON — it's ~10k tokens, well within context limits |
| Don't use the knowledge base as the only source | The LLM's own capabilities are primary; KB is a supplement |
| Don't hardcode the API key | Always read from `.env` |
| Don't call the LLM for slash commands | Handle `/rates`, `/deadlines`, `/help` locally in Python |
| Don't use `temperature > 0.5` | Tax answers must be consistent and factual |
| Don't suppress error details | Show the user what went wrong so they can act |
| Don't block on missing knowledge base | Warn and continue — the LLM still works without it |
| Don't forget the disclaimer | Include it in responses involving specific rates, penalties, or advice |

---

## Testing Checklist

Before shipping, verify:

- [ ] `.env` file is read correctly and API key is passed in Authorization header
- [ ] Knowledge base JSON loads without error and is injected into system prompt
- [ ] Chatbot starts, greets user, and accepts input
- [ ] Multi-turn: the bot correctly remembers earlier turns in the conversation
- [ ] `/rates` prints a formatted table from the knowledge base
- [ ] `/deadlines` prints a formatted table from the knowledge base
- [ ] `/clear` resets conversation history
- [ ] `/save` writes a valid JSON file to the `sessions/` directory
- [ ] `/exit` prompts to save and exits cleanly
- [ ] A question about VAT registration threshold returns the correct GHS 200,000 figure
- [ ] A question about the young entrepreneur exemption returns the 5-year exemption with correct post-exemption rates
- [ ] Missing `.env` exits with a helpful message
- [ ] Missing knowledge base file warns but continues running
- [ ] A network error is caught and shown as a user-friendly message
- [ ] Long conversations (>40 turns) trim history correctly without dropping the system prompt
