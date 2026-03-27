# retriever.py
# ─────────────────────────────────────────────────────────────
# Hybrid retriever = Semantic (ChromaDB) + Keyword (BM25).
# Results are merged with Reciprocal Rank Fusion (RRF) and
# optionally filtered by user profile metadata.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
from typing import List, Dict, Optional, Any
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rank_bm25 import BM25Okapi

from config import (
    CHROMA_DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL,
    TOP_K_SEMANTIC, TOP_K_BM25, TOP_K_FINAL, HYBRID_ALPHA,
)


class HybridRetriever:
    """
    Combines ChromaDB semantic search and BM25 keyword search.

    Merge strategy: Reciprocal Rank Fusion (RRF)
      score(d) = HYBRID_ALPHA * (1/(k+rank_semantic))
              + (1-HYBRID_ALPHA) * (1/(k+rank_bm25))
    where k=60 is the RRF constant.
    """

    RRF_K = 60

    def __init__(self):
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        self.collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._all_docs: List[str]  = []
        self._all_meta: List[dict] = []
        self._all_ids:  List[str]  = []
        self._bm25: Optional[BM25Okapi] = None
        self._load_bm25_corpus()

    # ── BM25 Setup ────────────────────────────────────────────

    def _load_bm25_corpus(self):
        """Load all documents from ChromaDB to build BM25 index."""
        result = self.collection.get(include=["documents", "metadatas"])
        if not result["documents"]:
            return
        self._all_docs = result["documents"]
        self._all_meta = result["metadatas"]
        self._all_ids  = result["ids"]
        tokenized = [doc.lower().split() for doc in self._all_docs]
        self._bm25 = BM25Okapi(tokenized)

    def refresh_bm25(self):
        """Call this after adding new documents at runtime."""
        self._load_bm25_corpus()

    # ── Metadata Filter Builder ───────────────────────────────

    @staticmethod
    def _build_where(user_profile: Optional[Dict]) -> Optional[Dict]:
        """
        Converts user profile into a ChromaDB metadata filter.
        Only filters on risk_level and user_type when clearly set.
        """
        if not user_profile:
            return None

        conditions = []

        risk = user_profile.get("risk_appetite")
        risk_map = {
            "conservative": ["low"],
            "moderate":     ["low", "moderate"],
            "aggressive":   ["low", "moderate", "high", "very_high"],
        }
        if risk and risk in risk_map:
            allowed = risk_map[risk]
            if len(allowed) == 1:
                conditions.append({"risk_level": {"$eq": allowed[0]}})
            else:
                conditions.append({"risk_level": {"$in": allowed}})

        exp = user_profile.get("experience_level")
        exp_map = {
            "beginner":     ["beginner"],
            "intermediate": ["beginner", "intermediate"],
            "advanced":     ["beginner", "intermediate", "advanced"],
        }
        if exp and exp in exp_map:
            allowed = exp_map[exp]
            if len(allowed) == 1:
                conditions.append({"user_type": {"$eq": allowed[0]}})
            else:
                conditions.append({"user_type": {"$in": allowed}})

        if len(conditions) == 0:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    # ── Semantic Search ───────────────────────────────────────

    def _semantic_search(
        self, query: str, where: Optional[Dict], n: int
    ) -> List[Dict[str, Any]]:
        kwargs: Dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n, max(1, self.collection.count())),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        result = self.collection.query(**kwargs)
        hits = []
        for doc, meta, dist in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            hits.append({"text": doc, "metadata": meta, "score": 1 - dist})
        return hits

    # ── BM25 Search ───────────────────────────────────────────

    def _bm25_search(
        self, query: str, where: Optional[Dict], n: int
    ) -> List[Dict[str, Any]]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        hits = []
        for idx in ranked:
            if len(hits) >= n:
                break
            meta = self._all_meta[idx]
            # Manual metadata filter for BM25 results
            if where:
                if not self._matches_filter(meta, where):
                    continue
            hits.append({
                "text": self._all_docs[idx],
                "metadata": meta,
                "score": float(scores[idx]),
            })
        return hits

    @staticmethod
    def _matches_filter(meta: Dict, where: Dict) -> bool:
        """Simple metadata filter evaluator for BM25 results."""
        for key, condition in where.items():
            if key == "$and":
                return all(
                    HybridRetriever._matches_filter(meta, c) for c in condition
                )
            val = meta.get(key)
            if isinstance(condition, dict):
                op, target = next(iter(condition.items()))
                if op == "$eq"  and val != target:        return False
                if op == "$in"  and val not in target:    return False
                if op == "$ne"  and val == target:        return False
            elif val != condition:
                return False
        return True

    # ── RRF Merge ─────────────────────────────────────────────

    def _rrf_merge(
        self,
        semantic_hits: List[Dict],
        bm25_hits: List[Dict],
    ) -> List[Dict]:
        scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict] = {}

        for rank, hit in enumerate(semantic_hits):
            key = hit["text"][:80]
            scores[key] = scores.get(key, 0) + HYBRID_ALPHA / (self.RRF_K + rank + 1)
            doc_map[key] = hit

        for rank, hit in enumerate(bm25_hits):
            key = hit["text"][:80]
            scores[key] = scores.get(key, 0) + (1 - HYBRID_ALPHA) / (self.RRF_K + rank + 1)
            doc_map[key] = hit

        ranked_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
        return [doc_map[k] for k in ranked_keys[:TOP_K_FINAL]]

    # ── Public API ────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        user_profile: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Main retrieval method.

        Args:
            query:        Natural language user question.
            user_profile: Dict with keys like risk_appetite, experience_level.

        Returns:
            List of top-K dicts with keys: text, metadata, score.
        """
        where = self._build_where(user_profile)
        semantic = self._semantic_search(query, where, TOP_K_SEMANTIC)
        bm25     = self._bm25_search(query, where, TOP_K_BM25)
        merged   = self._rrf_merge(semantic, bm25)
        return merged

    def format_context(self, hits: List[Dict]) -> str:
        """Format retrieved chunks into a clean context string for the LLM."""
        from config import GEMINI_CONTEXT_MAX_HIT_CHARS, GEMINI_CONTEXT_MAX_TOTAL_CHARS
        parts = []
        running_chars = 0
        for i, hit in enumerate(hits, 1):
            meta = hit["metadata"]
            header = (
                f"[{i}] Source: {meta.get('source_file','?')} | "
                f"Topic: {meta.get('topic','?')} | "
                f"Risk: {meta.get('risk_level','?')}"
            )
            text = hit["text"].strip()
            if len(text) > GEMINI_CONTEXT_MAX_HIT_CHARS:
                text = text[:GEMINI_CONTEXT_MAX_HIT_CHARS] + "..."
            candidate = f"{header}\n{text}"

            # Cap total context length to leave room for the answer
            running_chars += len(candidate)
            if running_chars > GEMINI_CONTEXT_MAX_TOTAL_CHARS:
                break

            parts.append(candidate)

        return "\n\n---\n\n".join(parts)
