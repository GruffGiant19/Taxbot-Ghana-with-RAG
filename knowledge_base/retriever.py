"""
retriever.py
------------
RAG retriever for TaxBot Ghana.

Embeds a user query with the same sentence-transformers model used during
ingestion, then queries ChromaDB for the top-K most semantically similar
chunks. The returned chunks are injected into the LLM prompt as context.

Usage (standalone test):
    python3 knowledge_base/retriever.py "What is the VAT threshold in Ghana?"

Usage (from taxbot.py):
    from knowledge_base.retriever import Retriever
    retriever = Retriever()
    context   = retriever.get_context("What is the VAT threshold?", top_k=3)
"""

import sys
from pathlib import Path

ROOT           = Path(__file__).parent.parent
CHROMA_DIR     = ROOT / "chroma_db"
COLLECTION     = "taxbot_ghana_kb"
EMBED_MODEL    = "sentence-transformers/all-MiniLM-L6-v2"

DEFAULT_TOP_K  = 3   # number of chunks to retrieve per query


class Retriever:
    """
    Thin wrapper around ChromaDB + sentence-transformers.

    The model is loaded once on instantiation and reused for every query,
    keeping inference fast across a multi-turn conversation.
    """

    def __init__(self) -> None:
        self._model      = self._load_model()
        self._collection = self._load_collection()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_context(self, query: str, top_k: int = DEFAULT_TOP_K) -> str:
        """
        Embed `query`, retrieve the top-K most relevant chunks from
        ChromaDB, and return them as a single formatted string ready to
        inject into the system/user prompt.

        Returns an empty string if ChromaDB is unavailable.
        """
        if self._collection is None:
            return ""

        query_vector = self._embed(query)

        results = self._collection.query(
            query_embeddings = [query_vector],
            n_results        = min(top_k, self._collection.count()),
            include          = ["documents", "metadatas", "distances"],
        )

        chunks     = results["documents"][0]      # list of chunk texts
        distances  = results["distances"][0]      # cosine distances (lower = more similar)

        if not chunks:
            return ""

        lines = ["## Relevant Knowledge Base Excerpts\n"]
        for i, (text, dist) in enumerate(zip(chunks, distances), start=1):
            similarity = round(1 - dist, 3)      # convert distance → similarity score
            lines.append(f"### Excerpt {i}  (similarity: {similarity})\n{text}\n")

        return "\n".join(lines)

    def similarity_search(
        self, query: str, top_k: int = DEFAULT_TOP_K
    ) -> list[dict]:
        """
        Lower-level method — returns a list of dicts with full metadata.
        Useful for debugging or building custom prompt templates.

        Returns:
            [
              {"chunk_id": int, "text": str, "similarity": float},
              ...
            ]
        """
        if self._collection is None:
            return []

        query_vector = self._embed(query)

        results = self._collection.query(
            query_embeddings = [query_vector],
            n_results        = min(top_k, self._collection.count()),
            include          = ["documents", "metadatas", "distances"],
        )

        output = []
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            output.append({
                "chunk_id"  : meta["chunk_id"],
                "word_count": meta["word_count"],
                "similarity": round(1 - dist, 4),
                "text"      : text,
            })

        return output

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        """Embed a single string and return the vector as a Python list."""
        return self._model.encode(text, convert_to_numpy=True).tolist()

    @staticmethod
    def _load_model():
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer(EMBED_MODEL)
        except ImportError:
            print("[WARNING] sentence-transformers not installed — retriever disabled.")
            return None

    @staticmethod
    def _load_collection():
        try:
            import chromadb
        except ImportError:
            print("[WARNING] chromadb not installed — retriever disabled.")
            return None

        if not CHROMA_DIR.exists():
            print(
                f"[WARNING] ChromaDB not found at {CHROMA_DIR}.\n"
                "Run knowledge_base/ingest_chroma.py to build it."
            )
            return None

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            return client.get_collection(name=COLLECTION)
        except Exception:
            print(
                f"[WARNING] Collection '{COLLECTION}' not found in ChromaDB.\n"
                "Run knowledge_base/ingest_chroma.py to build it."
            )
            return None


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
    hits      = retriever.similarity_search(query, top_k=3)

    if not hits:
        print("No results — is the ChromaDB collection built?")
        sys.exit(1)

    for hit in hits:
        print(
            f"\n[Chunk {hit['chunk_id']}]  "
            f"similarity={hit['similarity']}  "
            f"words={hit['word_count']}"
        )
        print(hit["text"][:300] + "…")
        print("-" * 60)
