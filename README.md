# TaxBot Ghana

AI-powered CLI assistant for Ghana MSME tax queries.

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file:
   ```
   OPENROUTER_API_KEY=your_key_here
   ```

3. Place the knowledge base file at:
   ```
   knowledge_base/ghana_msme_tax_knowledge_base.json
   ```

4. Run:
   ```bash
   python taxbot.py
   ```

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/rates` | Show key Ghana tax rates |
| `/deadlines` | Show all filing deadlines |
| `/clear` | Clear conversation history |
| `/save` | Save session to file |
| `/exit` | Exit (with save prompt) |

## Disclaimer

TaxBot Ghana provides general guidance only.
Always verify with GRA (www.gra.gov.gh) or a qualified tax professional.
