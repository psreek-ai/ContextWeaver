"""
Vector Store - semantic search layer backed by ChromaDB.

Stores every Decision as a dense vector embedding so we can find
conceptually related decisions via cosine similarity - the foundation
for conflict detection and context briefings.
"""

from __future__ import annotations

import json
import os
from typing import Any

import chromadb
import structlog

from contextweaver.models import Decision

log = structlog.get_logger()


class VectorStore:
    """
    Persistent vector store for Decision embeddings.

    Uses ChromaDB's built-in embedding (default: all-MiniLM-L6-v2 via sentence-transformers)
    for local, zero-cost embedding that requires no external API calls.
    For production, swap to an Anthropic or OpenAI embedding model.
    """

    COLLECTION_NAME = "decisions"

    def __init__(self, persist_dir: str) -> None:
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("vector_store.initialized", persist_dir=persist_dir)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(self, decision: Decision) -> str:
        """Add or update a Decision's embedding. Returns the embedding ID."""
        doc = self._decision_to_doc(decision)
        embedding_id = f"d_{decision.id}"

        self._collection.upsert(
            ids=[embedding_id],
            documents=[doc],
            metadatas=[self._decision_to_meta(decision)],
        )
        log.debug("vector_store.upserted", id=decision.id, title=decision.title)
        return embedding_id

    def upsert_many(self, decisions: list[Decision]) -> None:
        if not decisions:
            return
        ids = [f"d_{d.id}" for d in decisions]
        docs = [self._decision_to_doc(d) for d in decisions]
        metas = [self._decision_to_meta(d) for d in decisions]
        self._collection.upsert(ids=ids, documents=docs, metadatas=metas)
        log.info("vector_store.batch_upsert", count=len(decisions))

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic similarity search.

        Returns a list of dicts with keys: id, document, metadata, distance.
        Distance is cosine distance (lower = more similar).
        """
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, max(1, self._collection.count())),
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)
        output = []
        if results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                output.append(
                    {
                        "id": doc_id,
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i],
                    }
                )
        return output

    def count(self) -> int:
        return self._collection.count()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decision_to_doc(d: Decision) -> str:
        """
        Produce the text blob that gets embedded.
        Richer text = better embeddings = better semantic search.
        """
        parts = [
            f"TITLE: {d.title}",
            f"SUMMARY: {d.summary}",
            f"RATIONALE: {d.rationale}",
        ]
        if d.alternatives_considered:
            parts.append("ALTERNATIVES: " + " | ".join(d.alternatives_considered))
        if d.trade_offs:
            parts.append("TRADE-OFFS: " + " | ".join(d.trade_offs))
        if d.tags:
            parts.append("TAGS: " + " ".join(d.tags))
        return "\n".join(parts)

    @staticmethod
    def _decision_to_meta(d: Decision) -> dict[str, Any]:
        return {
            "decision_id": d.id,
            "title": d.title[:256],
            "confidence": d.confidence.value,
            "made_at": d.made_at.isoformat(),
            "tags": json.dumps(d.tags),
            "debt_score": d.debt_score,
            "authors": json.dumps(d.authors),
        }
