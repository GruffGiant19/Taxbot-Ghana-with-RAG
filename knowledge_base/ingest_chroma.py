"""
ingest_chroma.py
----------------
Loads pre-computed embeddings from embedded_kb.json into a persistent
ChromaDB collection stored at <project_root>/chroma_db/.

Safe to re-run — it wipes and recreates the collection each time so the
DB always reflects the current embedded_kb.json.

Run:
    python3 knowledge_base/ingest_chroma.py
"""

import json
import sys
from pathlib import Path

# Project root is one level up from this script
ROOT = Path(__file__).parent.parent

EMBEDDED_FILE = Path(__file__).parent / "embedded_kb.json"
CHROMA_DIR    = ROOT / "chroma_db"
COLLECTION    = "taxbot_ghana_kb"


def main() -> None:
    # --- Guard ---
    if not EMBEDDED_FILE.exists():
        print(f"[ERROR] embedded_kb.json not found at {EMBEDDED_FILE}")
        print("Run embed_kb.py first.")
        sys.exit(1)

    try:
        import chromadb
    except ImportError:
        print("[ERROR] chromadb is not installed.\nRun: pip install chromadb")
        sys.exit(1)

    # Load embedded chunks
    records = json.loads(EMBEDDED_FILE.read_text(encoding="utf-8"))
    print(f"Loaded {len(records)} embedded chunks from {EMBEDDED_FILE.name}")

    # Initialise persistent ChromaDB client
    CHROMA_DIR.mkdir(exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Drop existing collection so re-runs are idempotent
    try:
        client.delete_collection(name=COLLECTION)
        print(f"Dropped existing collection: '{COLLECTION}'")
    except Exception:
        pass  # doesn't exist yet — fine

    # Create fresh collection
    # embedding_function=None because we supply our own pre-computed vectors
    collection = client.create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},   # cosine similarity at query time
    )
    print(f"Created collection: '{COLLECTION}'  (cosine similarity)")

    # Build Chroma-compatible lists
    ids         = [str(r["chunk_id"])  for r in records]
    embeddings  = [r["embedding"]      for r in records]
    documents   = [r["text"]           for r in records]
    metadatas   = [{"chunk_id": r["chunk_id"], "word_count": r["word_count"]}
                   for r in records]

    # Upsert everything in one call
    collection.add(
        ids        = ids,
        embeddings = embeddings,
        documents  = documents,
        metadatas  = metadatas,
    )

    # Verify
    count = collection.count()
    print(f"\n✓ Ingestion complete.")
    print(f"  Collection : '{COLLECTION}'")
    print(f"  Documents  : {count}")
    print(f"  Stored at  : {CHROMA_DIR}")


if __name__ == "__main__":
    main()
