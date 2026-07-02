"""
embed_kb.py
-----------
Reads chunks_kb.json, generates an embedding vector for each chunk using
the local sentence-transformers model (all-MiniLM-L6-v2).

Completely FREE — no API key, no rate limits, runs offline.
Model weights (~90 MB) are downloaded once from HuggingFace on first run
and cached locally at ~/.cache/huggingface/hub/.

Each record in embedded_kb.json:
    {
      "chunk_id"   : int,           # matches chunks_kb.json
      "word_count" : int,
      "text"       : str,
      "embedding"  : [float, ...]   # 384-dim vector
    }

Run:
    python3 knowledge_base/embed_kb.py

Install dependency:
    pip install sentence-transformers
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim, fast, free

INPUT_FILE  = Path(__file__).parent / "chunks_kb.json"
OUTPUT_FILE = Path(__file__).parent / "embedded_kb.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_model():
    """Load the sentence-transformer model (downloads once, then cached)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "[ERROR] sentence-transformers is not installed.\n"
            "Run:  pip install sentence-transformers"
        )
        sys.exit(1)

    print(f"Loading model: {EMBED_MODEL}")
    print("(First run downloads ~90 MB — cached afterwards)\n")
    return SentenceTransformer(EMBED_MODEL)


def embed_text(model, text: str) -> list[float]:
    """Return a 384-dim embedding vector for a single text string."""
    vector = model.encode(text, convert_to_numpy=True)
    return vector.tolist()


def _save(records: list[dict]) -> None:
    OUTPUT_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # --- Guard: input file ---
    if not INPUT_FILE.exists():
        print(f"[ERROR] chunks_kb.json not found at {INPUT_FILE}")
        print("Run chunk_kb.py first.")
        sys.exit(1)

    chunks = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    total  = len(chunks)

    # Load the model (downloads on first run, cached after)
    model = load_model()

    # --- Resume support: skip already-embedded chunks ---
    if OUTPUT_FILE.exists():
        existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        done_ids = {rec["chunk_id"] for rec in existing}
        results  = existing
        print(f"Resuming — {len(done_ids)} chunk(s) already embedded.\n")
    else:
        done_ids = set()
        results  = []

    print(f"Embedding {total} chunks with: {EMBED_MODEL}\n")

    # --- Embed each chunk ---
    for chunk in chunks:
        cid = chunk["chunk_id"]

        if cid in done_ids:
            print(f"  Chunk {cid:>2}/{total}  [skip — already embedded]")
            continue

        print(f"  Chunk {cid:>2}/{total}  ({chunk['word_count']} words) … ", end="", flush=True)

        vector = embed_text(model, chunk["text"])

        results.append({
            "chunk_id"  : cid,
            "word_count": chunk["word_count"],
            "text"      : chunk["text"],
            "embedding" : vector,
        })

        print(f"✓  ({len(vector)}-dim vector)")

        # Save after every chunk — crash-safe
        _save(results)

    # --- Final summary ---
    _save(results)
    print(f"\nDone! {len(results)} chunks embedded.")
    print(f"Model              : {EMBED_MODEL}")
    print(f"Embedding dims     : {len(results[0]['embedding'])}")
    print(f"Output file        : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
