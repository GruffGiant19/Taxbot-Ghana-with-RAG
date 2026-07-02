"""
chunk_kb.py
-----------
Reads stripped_kb.md and splits it into overlapping word-based chunks.

Settings
--------
  CHUNK_SIZE  : 300 words per chunk
  OVERLAP     : 50 words carried forward from the previous chunk

Output
------
  chunks_kb.json   — JSON array of chunk objects:
    {
      "chunk_id"   : int,       # 1-based index
      "word_count" : int,       # actual words in this chunk
      "text"       : str        # chunk text
    }

Run:
    python3 knowledge_base/chunk_kb.py
"""

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
INPUT_FILE  = Path(__file__).parent / "stripped_kb.md"
OUTPUT_FILE = Path(__file__).parent / "chunks_kb.json"

CHUNK_SIZE = 300   # target words per chunk
OVERLAP    = 50    # words to carry over from previous chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalise(text: str) -> str:
    """Collapse multiple blank lines / trailing spaces but preserve newlines
    so that paragraph breaks survive into chunks."""
    text = re.sub(r"[ \t]+\n", "\n", text)          # trailing spaces
    text = re.sub(r"\n{3,}", "\n\n", text)           # 3+ blanks → 2
    return text.strip()


def tokenise(text: str) -> list[str]:
    """Split on whitespace, keeping the tokens (words/punctuation units)."""
    return text.split()


def detokenise(tokens: list[str]) -> str:
    """Join tokens back with a single space."""
    return " ".join(tokens)


def build_chunks(tokens: list[str], size: int, overlap: int) -> list[str]:
    """
    Slide a window of `size` tokens over `tokens` with `overlap` carry-over.
    The final chunk may be smaller than `size`.
    """
    chunks: list[str] = []
    start = 0
    total = len(tokens)

    while start < total:
        end = min(start + size, total)
        chunk_tokens = tokens[start:end]
        chunks.append(detokenise(chunk_tokens))

        if end == total:
            break                       # reached the end

        # next window begins (size - overlap) tokens ahead
        start += size - overlap

    return chunks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not INPUT_FILE.exists():
        print(f"[ERROR] Input file not found: {INPUT_FILE}")
        return

    raw   = INPUT_FILE.read_text(encoding="utf-8")
    clean = normalise(raw)
    words = tokenise(clean)

    print(f"Total words in stripped_kb: {len(words)}")

    raw_chunks = build_chunks(words, CHUNK_SIZE, OVERLAP)

    records = []
    for i, text in enumerate(raw_chunks, start=1):
        records.append({
            "chunk_id"   : i,
            "word_count" : len(text.split()),
            "text"       : text,
        })

    OUTPUT_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Chunks produced : {len(records)}")
    print(f"Chunk size      : {CHUNK_SIZE} words")
    print(f"Overlap         : {OVERLAP} words")
    print(f"Output          : {OUTPUT_FILE.name}")
    print()

    # Preview first and last chunk boundaries
    for rec in records:
        preview = rec["text"][:80].replace("\n", " ")
        print(f"  Chunk {rec['chunk_id']:>2}  ({rec['word_count']} words)  {preview}…")


if __name__ == "__main__":
    main()
