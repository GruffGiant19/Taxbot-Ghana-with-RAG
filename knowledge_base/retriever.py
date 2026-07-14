"""
retriever.py
------------
RAG retriever for TaxBot Ghana.

Embeds a user query with fastembed's ONNX runtime (the same model used to
build kb_index.json), then finds the top-K most similar chunks via an
in-memory cosine-similarity search — no ChromaDB, no on-disk vector DB.
The corpus is small (~76 chunks), so a linear scan over precomputed,
L2-normalized vectors is simpler, smaller, and faster to cold-start than a
full vector database, and it works identically in the CLI and inside a
Vercel Python serverless function.

Usage (standalone test):
    python3 knowledge_base/retriever.py "What is the VAT threshold in Ghana?"

Usage (from core.py):
    from knowledge_base.retriever import Retriever
    retriever = Retriever()
    context   = retriever.get_context("What is the VAT threshold?", top_k=5)
"""

import sys
from pathlib import Path

KB_INDEX_PATH  = Path(__file__).parent / "kb_index.json"
MODEL_CACHE_DIR = Path(__file__).parent / ".fastembed_cache"
EMBED_MODEL    = "sentence-transformers/all-MiniLM-L6-v2"

DEFAULT_TOP_K  = 5   # number of chunks to retrieve per query


class Retriever:
    """
    Thin wrapper around fastembed + an in-memory cosine-similarity search.

    The model and the embedding matrix are both loaded once on
    instantiation and reused for every query, keeping inference fast
    across a multi-turn conversation.
    """

    def __init__(self) -> None:
        self._model              = self._load_model()
        self._chunks, self._vectors = self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_context(self, query: str, top_k: int = DEFAULT_TOP_K) -> str:
        """
        Embed `query`, retrieve the top-K most relevant chunks, and return
        them as a single formatted string ready to inject into the
        system/user prompt.

        Returns an empty string if the retriever is unavailable.
        """
        hits = self.similarity_search(query, top_k=top_k)
        if not hits:
            return ""

        lines = ["## Relevant Knowledge Base Excerpts\n"]
        for i, hit in enumerate(hits, start=1):
            lines.append(
                f"### Excerpt {i}  (similarity: {hit['similarity']})  —  {hit['title']}\n"
                f"{hit['text']}\n"
            )

        return "\n".join(lines)

    def similarity_search(
        self, query: str, top_k: int = DEFAULT_TOP_K
    ) -> list[dict]:
        """
        Lower-level method — returns a list of dicts with full metadata.
        Useful for debugging or building custom prompt templates.

        Returns:
            [
              {"id": str, "title": str, "source_path": str,
               "similarity": float, "text": str},
              ...
            ]
        """
        if self._vectors is None or len(self._chunks) == 0:
            return []

        query_vector = self._embed(query)

        import numpy as np
        scores = self._vectors @ np.array(query_vector)
        k = min(top_k, len(self._chunks))
        top_indices = np.argsort(-scores)[:k]

        output = []
        for idx in top_indices:
            chunk = self._chunks[idx]
            output.append({
                "id"         : chunk["id"],
                "title"      : chunk["title"],
                "source_path": chunk["source_path"],
                "similarity" : round(float(scores[idx]), 4),
                "text"       : chunk["text"],
            })

        return output

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        """Embed a single string and return the L2-normalized vector."""
        import numpy as np
        vector = next(self._model.embed([text]))
        arr = np.array(vector, dtype="float64")
        norm = np.linalg.norm(arr)
        if norm == 0:
            return arr.tolist()
        return (arr / norm).tolist()

    @staticmethod
    def _load_model():
        try:
            from fastembed import TextEmbedding
            return TextEmbedding(model_name=EMBED_MODEL, cache_dir=str(MODEL_CACHE_DIR))
        except ImportError:
            print("[WARNING] fastembed not installed — retriever disabled.")
            return None

    @staticmethod
    def _load_index():
        import json

        if not KB_INDEX_PATH.exists():
            print(
                f"[WARNING] kb_index.json not found at {KB_INDEX_PATH}.\n"
                "Run build_kb_chunks.py then embed_kb_chunks.py to build it."
            )
            return [], None

        try:
            import numpy as np
        except ImportError:
            print("[WARNING] numpy not installed — retriever disabled.")
            return [], None

        records = json.loads(KB_INDEX_PATH.read_text(encoding="utf-8"))
        if not records:
            return [], None

        chunks  = records
        vectors = np.array([r["embedding"] for r in records], dtype="float64")
        return chunks, vectors


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    query = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "What is the VAT registration threshold in Ghana?"
    )

    print(f"\nQuery: {query}\n")
    print("-" * 60)

    retriever = Retriever()
    hits      = retriever.similarity_search(query, top_k=5)

    if not hits:
        print("No results — is kb_index.json built?")
        sys.exit(1)

    for hit in hits:
        print(
            f"\n[{hit['id']}]  {hit['title']}  "
            f"similarity={hit['similarity']}"
        )
        print(hit["text"][:300] + "…")
        print("-" * 60)
