"""
embed_kb_chunks.py
-------------------
Reads kb_chunks.json, embeds each chunk with fastembed's ONNX runtime
(no PyTorch — small, fast cold start, works inside a Vercel Python
serverless function), and writes kb_index.json: chunk metadata plus an
L2-normalized 384-dim embedding per chunk. This file *is* the vector
index — there is no separate ingest step (no ChromaDB, no on-disk DB).

Run:
    python3 knowledge_base/embed_kb_chunks.py

Install dependency:
    pip install fastembed
"""

import json
import sys
from pathlib import Path

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim, ONNX, no torch

INPUT_FILE = Path(__file__).parent / "kb_chunks.json"
OUTPUT_FILE = Path(__file__).parent / "kb_index.json"
MODEL_CACHE_DIR = Path(__file__).parent / ".fastembed_cache"


def load_model():
    try:
        from fastembed import TextEmbedding
    except ImportError:
        print("[ERROR] fastembed is not installed.\nRun:  pip install fastembed")
        sys.exit(1)

    print(f"Loading model: {EMBED_MODEL}")
    print(f"Cache dir: {MODEL_CACHE_DIR} (bundled for Vercel deploys)")
    return TextEmbedding(model_name=EMBED_MODEL, cache_dir=str(MODEL_CACHE_DIR))


def normalize(vector):
    import numpy as np
    arr = np.array(vector, dtype="float64")
    norm = np.linalg.norm(arr)
    if norm == 0:
        return arr.tolist()
    return (arr / norm).tolist()


def main() -> None:
    if not INPUT_FILE.exists():
        print(f"[ERROR] kb_chunks.json not found at {INPUT_FILE}")
        print("Run build_kb_chunks.py first.")
        sys.exit(1)

    chunks = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    total = len(chunks)

    model = load_model()

    print(f"Embedding {total} chunks with: {EMBED_MODEL}\n")

    texts = [f"{c['title']}\n\n{c['text']}" for c in chunks]
    vectors = list(model.embed(texts))

    records = []
    for chunk, vector in zip(chunks, vectors):
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
    print(f"Model          : {EMBED_MODEL}")
    print(f"Embedding dims : {len(records[0]['embedding'])}")
    print(f"Output file    : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
