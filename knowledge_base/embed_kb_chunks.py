"""
embed_kb_chunks.py
-------------------
Reads kb_chunks.json, embeds each chunk via OpenRouter's hosted embeddings
endpoint (same model/dimensions the retriever uses at query time), and
writes kb_index.json: chunk metadata plus an L2-normalized embedding per
chunk. This file *is* the vector index — there is no separate ingest step
(no ChromaDB, no on-disk DB, no local embedding model to load).

Run:
    python3 knowledge_base/embed_kb_chunks.py

Requires OPENROUTER_API_KEY to be set (in .env or the environment).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from retriever import embed_texts, EMBEDDINGS_MODEL, EMBEDDINGS_DIMENSIONS

INPUT_FILE  = Path(__file__).parent / "kb_chunks.json"
OUTPUT_FILE = Path(__file__).parent / "kb_index.json"

BATCH_SIZE = 64  # chunks per embeddings API call


def normalize(vector: list[float]) -> list[float]:
    import numpy as np
    arr = np.array(vector, dtype="float64")
    norm = np.linalg.norm(arr)
    if norm == 0:
        return arr.tolist()
    return (arr / norm).tolist()


def main() -> None:
    import os
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("[ERROR] OPENROUTER_API_KEY not set.\nCreate a .env file with OPENROUTER_API_KEY=...")
        sys.exit(1)

    if not INPUT_FILE.exists():
        print(f"[ERROR] kb_chunks.json not found at {INPUT_FILE}")
        print("Run build_kb_chunks.py first.")
        sys.exit(1)

    chunks = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    total = len(chunks)

    print(f"Embedding {total} chunks with: {EMBEDDINGS_MODEL} ({EMBEDDINGS_DIMENSIONS}-dim)\n")

    texts = [f"{c['title']}\n\n{c['text']}" for c in chunks]

    records = []
    for start in range(0, total, BATCH_SIZE):
        batch_chunks = chunks[start:start + BATCH_SIZE]
        batch_texts  = texts[start:start + BATCH_SIZE]

        vectors = embed_texts(batch_texts, api_key)

        for chunk, vector in zip(batch_chunks, vectors):
            records.append({
                "id": chunk["id"],
                "title": chunk["title"],
                "source_path": chunk["source_path"],
                "text": chunk["text"],
                "word_count": chunk["word_count"],
                "embedding": normalize(vector),
            })
            print(f"  {chunk['id']:38s} ✓  ({len(vector)}-dim vector)")

    OUTPUT_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nDone! {len(records)} chunks embedded.")
    print(f"Model          : {EMBEDDINGS_MODEL}")
    print(f"Embedding dims : {len(records[0]['embedding'])}")
    print(f"Output file    : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
