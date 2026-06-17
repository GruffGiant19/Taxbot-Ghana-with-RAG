# TaxBot Ghana — AI MSME Tax CLI Chatbot

## Spec
Read `TaxBotSKILL.md` in full before writing any code. It is the complete,
unambiguous specification for this project. Follow it exactly — do not
deviate, add frameworks not listed, or make architectural decisions not
covered in the spec.

## Knowledge Base
The file `knowledge_base/ghana_msme_tax_knowledge_base.json` is the
primary data source for the chatbot. It must be loaded in full at startup
and injected into the system prompt as specified in TaxBotSKILL.md.

## Stack
- Python 3.11+
- Dependencies: rich, requests, python-dotenv
- No additional frameworks (no Click, no Typer, no FastAPI)
- LLM via OpenRouter

## Build Order
1. taxbot.py — main entry point and chat loop
2. Knowledge base loader and system prompt builder
3. Slash command handlers (/rates, /deadlines, /clear, /save, /exit, /help)
4. Error handling (all cases in the spec's error table)
5. Session save/load
6. requirements.txt and README.md

## Important Constraints
- Never hardcode API key — always read from `.env`
- Slash commands (`/help`, `/rates`, `/deadlines`, `/clear`, `/save`, `/exit`) are handled locally in Python, not sent to LLM
- Temperature must be `0.3` — factual tax answers, not creative
- If conversation exceeds 40 turns, trim oldest turns but keep system prompt
- Missing knowledge base = warn and continue (LLM still works)
- Missing API key = exit with clear error message

## Setup & Run
```bash
pip install rich requests python-dotenv
python taxbot.py
```
