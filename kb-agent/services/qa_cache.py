"""CompactRAG fast-path: pre-computed QA pair cache for zero-LLM-call responses.

Based on "CompactRAG" (arXiv 2602.05728). Pre-computed QA pairs are searched
by embedding similarity. If a match exceeds the confidence threshold, the
answer is returned directly without invoking the full RAG pipeline.

Tenant-aware: skips fast-path when search scope is "mine" (user expects only
their own data, but QA cache is built from shared datasets).

Usage in search.py:
    from services.qa_cache import search_qa_cache
    match = search_qa_cache(query_embedding)
    if match:
        return match  # Skip full pipeline
"""
import json
import math
import os
import logging
from services.tenant_context import get_search_scope

logger = logging.getLogger(__name__)

_QA_CACHE: list[dict] | None = None
_QA_CACHE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "evaluation", "data", "qa_pairs_embedded.json"
)
# Minimum cosine similarity to trigger fast-path response.
# Gemini embeddings produce lower cosine similarities than Contriever;
# 0.75 tested as appropriate for domain-specific QA pairs.
QA_CONFIDENCE_THRESHOLD = 0.75


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _load_cache() -> list[dict]:
    """Load QA pairs from JSON file (lazy, cached in module)."""
    global _QA_CACHE
    if _QA_CACHE is not None:
        return _QA_CACHE

    if not os.path.exists(_QA_CACHE_PATH):
        logger.info("QA cache not found — fast-path disabled")
        _QA_CACHE = []
        return _QA_CACHE

    with open(_QA_CACHE_PATH) as f:
        _QA_CACHE = json.load(f)
    logger.info(f"QA cache loaded: {len(_QA_CACHE)} pairs from {_QA_CACHE_PATH}")
    return _QA_CACHE


def search_qa_cache(query_embedding: list[float], top_k: int = 3) -> dict | None:
    """Search QA pairs by embedding similarity.

    Args:
        query_embedding: 768-dim embedding of the user query
        top_k: Number of top matches to consider

    Returns:
        Dict with answer, sources, and similarity if above threshold, else None
    """
    # Skip fast-path when scope is "mine" — QA cache contains shared data only
    if get_search_scope() == "mine":
        return None

    cache = _load_cache()
    if not cache:
        return None

    # Compute similarities
    scored = []
    for pair in cache:
        emb = pair.get("embedding")
        if not emb:
            continue
        sim = _cosine_similarity(query_embedding, emb)
        scored.append((sim, pair))

    if not scored:
        return None

    # Sort by similarity descending
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]
    best_sim, best_pair = top[0]

    if best_sim < QA_CONFIDENCE_THRESHOLD:
        logger.debug(f"QA cache: best match {best_sim:.3f} < threshold {QA_CONFIDENCE_THRESHOLD}")
        return None

    # Collect top matches above threshold for richer response
    matches = []
    for sim, pair in top:
        if sim >= QA_CONFIDENCE_THRESHOLD:
            matches.append({
                "question": pair["question"],
                "answer": pair["answer"],
                "doc_title": pair.get("doc_title", ""),
                "page": pair.get("page"),
                "similarity": round(sim, 4),
            })

    return {
        "fast_path": True,
        "confidence": round(best_sim, 4),
        "matches": matches,
        "best_answer": best_pair["answer"],
        "best_question": best_pair["question"],
        "source_doc": best_pair.get("doc_title", ""),
        "source_page": best_pair.get("page"),
    }
