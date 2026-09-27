"""L2: Retrieval Quality Metrics — Pure Scoring Core, Diagnostic Arms & Attrition Decomposition.

Evaluates retrieval quality across multiple arms:
- graph: Full hybrid search pipeline (keyword + vector + graph + HippoRAG/rerank)
- vector_only: Keyword + vector baseline (no graph)
- oracle: Upper bound / ceiling where all expected entities are present (reference only)
- blind: Lower bound / floor with empty context (reference only)
- constant: Majority-class / constant baseline

Attrition Decomposition (graph arm, mutually exclusive):
- C0_no_entities: The question has no expected entities defined.
- C1_entity_never_in_pool: At least one expected entity never appears anywhere in the candidate pool.
- C2_below_topk: All expected entities are in the pool, but not all made it into top-k returned.
- C3_capped_by_limit: The candidate pool was truncated by the configured limit constant.
- hit: All expected entities successfully retrieved in top-k chunks.

All scoring and aggregation functions are pure (no DB, no network, no I/O).
"""

import json
import math
import os
import random
import sys
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from evaluation.constants import (
        DEFAULT_CANDIDATE_LIMIT,
        DEFAULT_TOP_K,
        DEFAULT_CONTEXT_TRUNCATION_LIMIT,
        DEFAULT_MIN_GRAPH_PATHS,
        DEFAULT_SPLIT_SEED,
        DEFAULT_DEV_RATIO,
        CANDIDATE_LIMIT_SWEEP_VALUES,
    )
except ImportError:  # running from inside evaluation/ (documented entrypoint)
    from constants import (
        DEFAULT_CANDIDATE_LIMIT,
        DEFAULT_TOP_K,
        DEFAULT_CONTEXT_TRUNCATION_LIMIT,
        DEFAULT_MIN_GRAPH_PATHS,
        DEFAULT_SPLIT_SEED,
        DEFAULT_DEV_RATIO,
        CANDIDATE_LIMIT_SWEEP_VALUES,
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. Pure Scoring Core
# ═══════════════════════════════════════════════════════════════════════

def compute_context_recall(chunks: list[Union[str, dict]], expected_entities: list[str]) -> float:
    """Calculate the fraction of expected entities found in retrieved chunks.

    Args:
        chunks: List of text strings or chunk dicts containing 'text'.
        expected_entities: List of target entity names expected in context.

    Returns:
        Recall score in [0.0, 1.0]. Returns 1.0 if expected_entities is empty.
    """
    if not expected_entities:
        return 1.0
    if not chunks:
        return 0.0

    raw_texts = []
    for c in chunks:
        if isinstance(c, dict):
            raw_texts.append(c.get("text", "") or "")
        elif isinstance(c, str):
            raw_texts.append(c)

    chunks_lower = " ".join(t.lower() for t in raw_texts)
    found = sum(1 for e in expected_entities if e.lower() in chunks_lower)
    return round(found / len(expected_entities), 3)


def compute_uplift(arm_recall: float, baseline_recall: float) -> float:
    """Compute the difference between arm recall and baseline recall."""
    return round(arm_recall - baseline_recall, 3)


def compute_percentiles(values: list[Union[int, float]]) -> dict[str, Union[int, float]]:
    """Compute min, median, p90, max for a sequence of values."""
    if not values:
        return {"min": 0, "median": 0, "p90": 0, "max": 0}

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _percentile(p: float) -> Union[int, float]:
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        res = d0 + d1
        return round(res, 2) if isinstance(res, float) else res

    return {
        "min": sorted_vals[0],
        "median": _percentile(0.50),
        "p90": _percentile(0.90),
        "max": sorted_vals[-1],
    }


# ═══════════════════════════════════════════════════════════════════════
# 2. Diagnostic Arms & Attrition Decomposition
# ═══════════════════════════════════════════════════════════════════════

def score_question_arms(
    q: dict,
    graph_chunks: list[Union[str, dict]],
    vector_chunks: list[Union[str, dict]],
    all_eval_questions: Optional[list[dict]] = None,
    graph_time_ms: float = 0.0,
    vector_time_ms: float = 0.0,
) -> dict:
    """Score all diagnostic arms for a single question.

    Arms:
    - graph: Evaluated system (full pipeline)
    - vector_only: Baseline without graph
    - oracle: Ideal context with all expected entities present (upper bound, reference)
    - blind: Empty context (lower bound, reference)
    - constant: Constant majority entity context / baseline
    """
    expected = q.get("expected_entities", [])

    # Graph arm
    graph_recall = compute_context_recall(graph_chunks, expected)

    # Vector-only arm
    vector_recall = compute_context_recall(vector_chunks, expected)

    # Oracle arm (upper bound): all expected entities present
    oracle_context = [" ".join(expected)] if expected else []
    oracle_recall = compute_context_recall(oracle_context, expected)

    # Blind arm (lower bound): empty context
    blind_context: list[str] = []
    blind_recall = 0.0 if expected else 1.0

    # Constant arm: baseline based on most frequent global entities
    constant_context = []
    if all_eval_questions:
        all_ents = [
            e for item in all_eval_questions for e in item.get("expected_entities", [])
        ]
        if all_ents:
            most_common = [e for e, _ in Counter(all_ents).most_common(5)]
            constant_context = [" ".join(most_common)]
    constant_recall = compute_context_recall(constant_context, expected)

    return {
        "graph": {
            "context_recall": graph_recall,
            "chunks_found": len(graph_chunks),
            "time_ms": round(graph_time_ms, 1),
            "is_reference": False,
        },
        "vector_only": {
            "context_recall": vector_recall,
            "chunks_found": len(vector_chunks),
            "time_ms": round(vector_time_ms, 1),
            "is_reference": False,
        },
        "oracle": {
            "context_recall": oracle_recall,
            "chunks_found": len(oracle_context),
            "time_ms": 0.0,
            "is_reference": True,
        },
        "blind": {
            "context_recall": blind_recall,
            "chunks_found": 0,
            "time_ms": 0.0,
            "is_reference": True,
        },
        "constant": {
            "context_recall": constant_recall,
            "chunks_found": len(constant_context),
            "time_ms": 0.0,
            "is_reference": False,
        },
    }


def decompose_graph_attrition(
    q: dict,
    candidate_pool: list[Union[str, dict]],
    top_k_chunks: list[Union[str, dict]],
    candidate_pool_size: Optional[int] = None,
    configured_limit: int = DEFAULT_CANDIDATE_LIMIT,
    pool_was_truncated: bool = False,
) -> str:
    """Decompose the graph retrieval outcome into exactly one mutually exclusive bucket.

    Buckets:
    1. C0_no_entities: The question defines no expected entities.
    2. hit: All expected entities retrieved in top-k chunks.
    3. C3_capped_by_limit: Candidate pool was truncated by configured limit and not all entities in top-k.
    4. C2_below_topk: All expected entities exist in candidate pool, but not all in top-k.
    5. C1_entity_never_in_pool: At least one expected entity never appears in candidate pool.
    """
    expected = q.get("expected_entities", [])
    if not expected:
        return "C0_no_entities"

    actual_pool_size = candidate_pool_size if candidate_pool_size is not None else len(candidate_pool)

    # Check top-k recall
    topk_recall = compute_context_recall(top_k_chunks, expected)
    if topk_recall == 1.0:
        return "hit"

    # If pool was truncated by limit (or pool size >= configured limit) and not all entities in top-k
    is_capped = pool_was_truncated or (actual_pool_size >= configured_limit)

    # Check candidate pool recall
    pool_recall = compute_context_recall(candidate_pool, expected)

    if pool_recall == 1.0:
        # All entities made it into the candidate pool, but some dropped below top-k
        return "C2_below_topk"

    # Entities missing from candidate pool: was the pool capped?
    if is_capped:
        return "C3_capped_by_limit"

    return "C1_entity_never_in_pool"


# ═══════════════════════════════════════════════════════════════════════
# 3. Aggregation & Synthesis
# ═══════════════════════════════════════════════════════════════════════

def aggregate_evaluation_results(
    per_question_results: list[dict],
    configured_limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> dict:
    """Aggregate per-question results, diagnostic arms, attrition breakdown, and pool distribution."""
    n = len(per_question_results)
    if n == 0:
        return {
            "questions_total": 0,
            "arms": {},
            "winner": "none",
            "attrition": {"counts": {}, "shares": {}},
            "candidate_pool_distribution": {},
        }

    # Arm averages
    arms_data: dict[str, dict] = {}
    candidate_arms = ["graph", "vector_only", "oracle", "blind", "constant"]
    for arm_name in candidate_arms:
        recalls = [
            r["arms"][arm_name]["context_recall"]
            for r in per_question_results
            if arm_name in r.get("arms", {})
        ]
        if recalls:
            avg_rec = sum(recalls) / len(recalls)
            is_ref = per_question_results[0].get("arms", {}).get(arm_name, {}).get("is_reference", False)
            arms_data[arm_name] = {
                "avg_recall": round(avg_rec, 3),
                "is_reference": is_ref,
            }

    # Winner selection (excluding reference arms oracle and blind)
    competitors = {
        name: data["avg_recall"]
        for name, data in arms_data.items()
        if not data.get("is_reference", False)
    }
    winner = max(competitors.items(), key=lambda kv: kv[1])[0] if competitors else "none"

    # Attrition breakdown
    all_buckets = ["C0_no_entities", "C1_entity_never_in_pool", "C2_below_topk", "C3_capped_by_limit", "hit"]
    bucket_counts = {b: 0 for b in all_buckets}
    for r in per_question_results:
        b = r.get("attrition_bucket")
        if b in bucket_counts:
            bucket_counts[b] += 1
        elif b:
            bucket_counts[b] = 1

    bucket_shares = {
        b: round(count / n, 3) for b, count in bucket_counts.items()
    }

    # Candidate pool distribution
    pool_sizes = [r.get("candidate_pool_size", 0) for r in per_question_results]
    pool_dist = compute_percentiles(pool_sizes)
    pool_dist["configured_limit"] = configured_limit
    pool_dist["cap_inside_distribution"] = bool(pool_dist["min"] <= configured_limit <= pool_dist["max"])

    # Uplift aggregates
    uplifts = [r.get("graph_uplift", 0.0) for r in per_question_results]
    avg_uplift = round(sum(uplifts) / n, 3) if n > 0 else 0.0

    multi_hop = [r for r in per_question_results if r.get("requires_graph")]
    avg_multihop_uplift = (
        round(sum(r.get("graph_uplift", 0.0) for r in multi_hop) / len(multi_hop), 3)
        if multi_hop
        else 0.0
    )

    return {
        "questions_total": n,
        "arms": arms_data,
        "winner": winner,
        "avg_graph_uplift": avg_uplift,
        "avg_multihop_uplift": avg_multihop_uplift,
        "questions_where_graph_helps": sum(1 for u in uplifts if u > 0),
        "attrition": {
            "counts": bucket_counts,
            "shares": bucket_shares,
        },
        "candidate_pool_distribution": pool_dist,
    }


# ═══════════════════════════════════════════════════════════════════════
# 4. Constant Sweeps
# ═══════════════════════════════════════════════════════════════════════

def sweep_candidate_limit(
    recorded_records: list[dict],
    limits: Optional[list[int]] = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict]:
    """Recompute arms and decomposition across a range of candidate limits.

    Args:
        recorded_records: List of dicts, each with:
            - id, expected_entities, requires_graph
            - candidates: list of candidate chunk dicts sorted by relevance / RRF score
            - vector_chunks: list of chunks returned by vector-only baseline
        limits: List of candidate limit values to test (defaults to CANDIDATE_LIMIT_SWEEP_VALUES).
        top_k: Top-k chunks to evaluate for final recall.

    Returns:
        Table of sweep results with metrics per limit value.
    """
    if limits is None:
        limits = CANDIDATE_LIMIT_SWEEP_VALUES

    sweep_table = []

    for lim in limits:
        per_q_results = []
        for rec in recorded_records:
            expected = rec.get("expected_entities", [])
            all_cands = rec.get("candidates", [])

            # Truncate candidates by limit
            capped_cands = all_cands[:lim]
            topk_cands = capped_cands[:top_k]
            vec_chunks = rec.get("vector_chunks", [])

            # Pure scoring of arms
            graph_recall = compute_context_recall(topk_cands, expected)
            vec_recall = compute_context_recall(vec_chunks, expected)
            uplift = compute_uplift(graph_recall, vec_recall)

            arms = {
                "graph": {"context_recall": graph_recall, "is_reference": False},
                "vector_only": {"context_recall": vec_recall, "is_reference": False},
                "oracle": {"context_recall": 1.0 if expected else 1.0, "is_reference": True},
                "blind": {"context_recall": 0.0 if expected else 1.0, "is_reference": True},
            }

            bucket = decompose_graph_attrition(
                q=rec,
                candidate_pool=capped_cands,
                top_k_chunks=topk_cands,
                candidate_pool_size=len(all_cands),
                configured_limit=lim,
                pool_was_truncated=len(all_cands) > lim,
            )

            per_q_results.append({
                "id": rec.get("id"),
                "requires_graph": rec.get("requires_graph", False),
                "arms": arms,
                "graph_uplift": uplift,
                "attrition_bucket": bucket,
                "candidate_pool_size": len(all_cands),
            })

        agg = aggregate_evaluation_results(per_q_results, configured_limit=lim)
        sweep_table.append({
            "limit": lim,
            "avg_graph_recall": agg["arms"]["graph"]["avg_recall"],
            "avg_vector_recall": agg["arms"]["vector_only"]["avg_recall"],
            "avg_graph_uplift": agg["avg_graph_uplift"],
            "hit_count": agg["attrition"]["counts"]["hit"],
            "capped_count": agg["attrition"]["counts"]["C3_capped_by_limit"],
            "below_topk_count": agg["attrition"]["counts"]["C2_below_topk"],
            "never_in_pool_count": agg["attrition"]["counts"]["C1_entity_never_in_pool"],
        })

    return sweep_table


# ═══════════════════════════════════════════════════════════════════════
# 5. Dev/Test Split & Enforcement
# ═══════════════════════════════════════════════════════════════════════

def split_dataset(
    questions: list[dict],
    seed: int = DEFAULT_SPLIT_SEED,
    dev_ratio: float = DEFAULT_DEV_RATIO,
) -> dict[str, str]:
    """Deterministically partition questions into 'dev' and 'test' splits using a fixed seed."""
    q_ids = sorted(q["id"] for q in questions)
    rng = random.Random(seed)
    shuffled_ids = list(q_ids)
    rng.shuffle(shuffled_ids)

    n_dev = int(len(shuffled_ids) * dev_ratio)
    dev_set = set(shuffled_ids[:n_dev])

    return {
        qid: ("dev" if qid in dev_set else "test")
        for qid in q_ids
    }


def filter_questions_by_split(
    questions: list[dict],
    split: str,
    split_map: Optional[dict[str, str]] = None,
    seed: int = DEFAULT_SPLIT_SEED,
    dev_ratio: float = DEFAULT_DEV_RATIO,
    enforce_test_only_reporting: bool = False,
) -> list[dict]:
    """Filter questions for a specific split (dev or test).

    Enforces that reporting calls cannot access dev split when enforce_test_only_reporting is True.
    """
    if split not in ("dev", "test", "all"):
        raise ValueError(f"Invalid split '{split}'. Must be 'dev', 'test', or 'all'.")

    if split_map is None:
        split_map = split_dataset(questions, seed=seed, dev_ratio=dev_ratio)

    if enforce_test_only_reporting and split == "test":
        # Ensure no dev questions are passed into a reporting evaluation
        has_dev = any(split_map.get(q["id"]) == "dev" for q in questions)
        if has_dev:
            raise ValueError("Reporting is strictly restricted to test split; dev questions detected.")

    if split == "all":
        return questions

    return [q for q in questions if split_map.get(q["id"]) == split]


# ═══════════════════════════════════════════════════════════════════════
# 6. Evaluation Orchestrator (Unit Testable / Invalidation Enforcing)
# ═══════════════════════════════════════════════════════════════════════

def run_l2_evaluation(
    questions: list[dict],
    search_full_fn: Callable[[str], dict],
    search_vector_fn: Callable[[str], dict],
    configured_limit: int = DEFAULT_CANDIDATE_LIMIT,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """Run L2 retrieval evaluation over questions.

    Query failures are not swallowed: if search_full_fn or search_vector_fn fails,
    it raises immediately or fails the run.
    """
    results = []

    for q in questions:
        query_text = q["question"]

        # Run full pipeline (graph)
        t0 = os.times().elapsed if hasattr(os, "times") else 0
        import time
        start_time = time.perf_counter()
        full_res = search_full_fn(query_text)
        graph_time = (time.perf_counter() - start_time) * 1000

        # Run vector-only baseline
        start_time = time.perf_counter()
        vec_res = search_vector_fn(query_text)
        vec_time = (time.perf_counter() - start_time) * 1000

        full_chunks = full_res.get("semantically_similar_chunks", [])
        vec_chunks = vec_res.get("semantically_similar_chunks", [])

        # Diagnostic arms scoring
        arms = score_question_arms(
            q=q,
            graph_chunks=full_chunks[:top_k],
            vector_chunks=vec_chunks[:top_k],
            all_eval_questions=questions,
            graph_time_ms=graph_time,
            vector_time_ms=vec_time,
        )

        uplift = compute_uplift(
            arms["graph"]["context_recall"],
            arms["vector_only"]["context_recall"],
        )

        candidate_pool = full_res.get("candidate_pool", full_chunks)
        candidate_pool_size = full_res.get("candidate_pool_size", len(candidate_pool))
        pool_truncated = full_res.get("pool_was_truncated", candidate_pool_size >= configured_limit)

        attrition_bucket = decompose_graph_attrition(
            q=q,
            candidate_pool=candidate_pool,
            top_k_chunks=full_chunks[:top_k],
            candidate_pool_size=candidate_pool_size,
            configured_limit=configured_limit,
            pool_was_truncated=pool_truncated,
        )

        res = {
            "id": q["id"],
            "category": q.get("category", ""),
            "hop_count": q.get("hop_count", 0),
            "requires_graph": q.get("requires_graph", False),
            "expected_entities": q.get("expected_entities", []),
            "arms": arms,
            "full_pipeline": {
                "context_recall": arms["graph"]["context_recall"],
                "chunks_found": len(full_chunks),
                "graph_connections": len(full_res.get("graph_connections", [])),
                "graph_chunks": full_res.get("retrieval_metadata", {}).get("graph_chunks", 0),
                "time_ms": round(graph_time, 1),
            },
            "vector_only": {
                "context_recall": arms["vector_only"]["context_recall"],
                "chunks_found": len(vec_chunks),
                "time_ms": round(vec_time, 1),
            },
            "graph_uplift": uplift,
            "attrition_bucket": attrition_bucket,
            "candidate_pool_size": candidate_pool_size,
        }
        results.append(res)

    aggregates = aggregate_evaluation_results(results, configured_limit=configured_limit)

    return {
        "layer": "L2_Retrieval_Quality",
        "per_question": results,
        "aggregates": aggregates,
    }


# ═══════════════════════════════════════════════════════════════════════
# 7. Live Spanner / Agent Search Helpers (Thin wrappers)
# ═══════════════════════════════════════════════════════════════════════

def load_eval_questions(split: str = "all") -> list[dict]:
    """Load evaluation questions from ground truth dataset with split support."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "ground_truth", "eval_questions.json")
    with open(path) as f:
        questions = json.load(f)

    if split != "all":
        questions = filter_questions_by_split(questions, split=split)
    return questions


def search_full_pipeline(query: str) -> dict:
    """Run full search pipeline against Spanner graph. Does NOT swallow exceptions."""
    from agents.search import tool_query_spanner_graph
    result_json = tool_query_spanner_graph(query)
    parsed = json.loads(result_json)
    if not isinstance(parsed, dict):
        raise ValueError(f"Invalid search output format: {result_json}")
    return parsed


def search_vector_only(query: str) -> dict:
    """Run vector-only search against Spanner. Does NOT swallow exceptions."""
    from services.spanner_client import get_database
    from services.document_chunker import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
    from google.cloud.spanner_v1 import param_types
    from google import genai

    client = genai.Client()
    emb = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=query[:8000],
        config=genai.types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    query_embedding = list(emb.embeddings[0].values)

    db = get_database()
    with db.snapshot() as snap:
        result = snap.execute_sql(
            """SELECT chunk.chunk_text, chunk.chunk_type, chunk.page_number, doc.title,
                      COSINE_DISTANCE(chunk.chunk_embedding, @query_emb) AS distance
               FROM DocumentChunks chunk
               JOIN Documents doc ON doc.doc_id = chunk.doc_id
               WHERE chunk.chunk_embedding IS NOT NULL
                 AND ARRAY_LENGTH(chunk.chunk_embedding) > 0
                 AND chunk.chunk_embedding[OFFSET(0)] != 0.0
               ORDER BY distance ASC
               LIMIT 15""",
            params={"query_emb": query_embedding},
            param_types={"query_emb": param_types.Array(param_types.FLOAT32)},
        )
        chunks = [row[0] for row in result]

    return {
        "semantically_similar_chunks": chunks,
        "graph_connections": [],
        "candidate_pool": chunks,
        "candidate_pool_size": len(chunks),
        "retrieval_metadata": {"strategy": "vector_only"},
    }


def run(split: str = "all", configured_limit: int = DEFAULT_CANDIDATE_LIMIT) -> dict:
    """Run L2 retrieval quality evaluation."""
    questions = load_eval_questions(split=split)
    return run_l2_evaluation(
        questions=questions,
        search_full_fn=search_full_pipeline,
        search_vector_fn=search_vector_only,
        configured_limit=configured_limit,
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="L2 Retrieval Evaluation")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="all", help="Dataset split to evaluate")
    parser.add_argument("--limit", type=int, default=DEFAULT_CANDIDATE_LIMIT, help="Candidate pool limit")
    args = parser.parse_args()

    results = run(split=args.split, configured_limit=args.limit)
    print(json.dumps(results, indent=2, ensure_ascii=False))
