"""
taxbot.py — TaxBot Ghana CLI entry point.

Shared logic (KB loading, chat, session save) lives in core.py.
This file owns: Rich UI, slash command rendering, and the main loop.
"""

import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from core import (
    load_knowledge_base,
    build_system_prompt,
    chat,
    save_session,
    retriever,
    MODEL,
)

load_dotenv()

console = Console()

# Per-session conversation history (CLI owns this list directly)
conversation_history = []

# ── Slash Commands ─────────────────────────────────────────────────────────

def cmd_help():
    console.print(Panel.fit(
        "[bold cyan]Available Commands[/bold cyan]\n\n"
        "[bold]/help[/bold]      Show this help\n"
        "[bold]/rates[/bold]     Show key Ghana tax rates\n"
        "[bold]/deadlines[/bold] Show all filing deadlines\n"
        "[bold]/clear[/bold]     Clear conversation history\n"
        "[bold]/save[/bold]      Save session to file\n"
        "[bold]/exit[/bold] or [bold]/quit[/bold]  Exit (with save prompt)",
        border_style="cyan"
    ))

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

def cmd_clear():
    global conversation_history
    conversation_history = []
    console.print("[dim]Conversation history cleared.[/dim]")

def handle_slash_command(user_input, kb):
    cmd = user_input.strip().lower()
    if cmd == "/help":
        cmd_help()
    elif cmd == "/rates":
        cmd_rates(kb)
    elif cmd == "/deadlines":
        cmd_deadlines(kb)
    elif cmd == "/clear":
        cmd_clear()
    elif cmd == "/save":
        path = save_session(conversation_history, MODEL)
        console.print(f"[dim]Session saved to {path}[/dim]")
    elif cmd in ("/exit", "/quit"):
        return "exit"
    else:
        console.print(f"[yellow]Unknown command: {user_input}. Type /help for options.[/yellow]")
    return None

# ── Main Loop ──────────────────────────────────────────────────────────────

def main():
    kb = load_knowledge_base()
    if kb is None:
        console.print("[yellow][WARNING] Knowledge base not found. Chatbot will run without it.[/yellow]")

    system_prompt = build_system_prompt(kb)

    rag_status = (
        "[bold green]RAG active[/bold green] — local vector search enabled"
        if retriever is not None
        else "[yellow]RAG offline[/yellow] — run ingest_chroma.py to enable"
    )

    console.print(Panel.fit(
        "[bold cyan]TaxBot Ghana[/bold cyan]\n"
        "[dim]Your MSME Tax Assistant — powered by OpenRouter[/dim]\n"
        f"{rag_status}\n"
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

        if user_input.startswith("/"):
            result = handle_slash_command(user_input, kb)
            if result == "exit":
                break
            continue

        with console.status("[dim]Thinking...[/dim]", spinner="dots"):
            try:
                reply = chat(user_input, system_prompt, conversation_history)
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                continue

        console.print("\n[bold cyan]TaxBot:[/bold cyan]")
        console.print(Markdown(reply))

    if conversation_history:
        save_prompt = console.input("\n[dim]Save this session? (y/n):[/dim] ").strip().lower()
        if save_prompt == "y":
            path = save_session(conversation_history, MODEL)
            console.print(f"[dim]Session saved to {path}[/dim]")

    console.print("[dim]Goodbye.[/dim]")


if __name__ == "__main__":
    main()
