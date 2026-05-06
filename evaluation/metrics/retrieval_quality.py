"""L2: Retrieval Quality Metrics — Graph vs Vector A/B Comparison.

For each evaluation question, runs the search in two modes:
1. Full pipeline (keyword + vector + GQL graph + HippoRAG)
2. Vector-only baseline (keyword + vector, no graph)

Measures:
- Context Recall: Did we find chunks containing expected entities?
- Multi-hop Recall: Can graph traversal answer multi-hop questions?
- Graph Uplift: Delta between full pipeline and vector-only
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "kb-agent"))


def load_eval_questions() -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "ground_truth", "eval_questions.json")
    with open(path) as f:
        return json.load(f)


def search_full_pipeline(query: str) -> dict:
    """Run the full search pipeline (keyword + vector + graph + HippoRAG)."""
    from agents.search import tool_query_spanner_graph
    result_json = tool_query_spanner_graph(query)
    return json.loads(result_json)


def search_vector_only(query: str) -> dict:
    """Run vector-only search (no graph, no HippoRAG) for A/B comparison."""
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

    return {"semantically_similar_chunks": chunks, "graph_connections": [], "retrieval_metadata": {"strategy": "vector_only"}}


def compute_context_recall(chunks: list[str], expected_entities: list[str]) -> float:
    """What fraction of expected entities appear in at least one retrieved chunk?"""
    if not expected_entities:
        return 1.0
    chunks_lower = " ".join(c.lower() for c in chunks)
    found = sum(1 for e in expected_entities if e.lower() in chunks_lower)
    return round(found / len(expected_entities), 3)


def run():
    """Run L2 evaluation."""
    questions = load_eval_questions()
    results = []

    for q in questions:
        print(f"  [{q['id']}] {q['question'][:60]}...", end=" ", flush=True)

        # Full pipeline
        t0 = time.perf_counter()
        full = search_full_pipeline(q["question"])
        full_time = (time.perf_counter() - t0) * 1000
        full_chunks = full.get("semantically_similar_chunks", [])
        full_recall = compute_context_recall(full_chunks, q["expected_entities"])

        # Vector-only baseline
        t0 = time.perf_counter()
        vec = search_vector_only(q["question"])
        vec_time = (time.perf_counter() - t0) * 1000
        vec_chunks = vec.get("semantically_similar_chunks", [])
        vec_recall = compute_context_recall(vec_chunks, q["expected_entities"])

        uplift = round(full_recall - vec_recall, 3)
        meta = full.get("retrieval_metadata", {})

        result = {
            "id": q["id"],
            "category": q["category"],
            "hop_count": q["hop_count"],
            "requires_graph": q["requires_graph"],
            "full_pipeline": {
                "context_recall": full_recall,
                "chunks_found": len(full_chunks),
                "graph_connections": len(full.get("graph_connections", [])),
                "graph_chunks": meta.get("graph_chunks", 0),
                "time_ms": round(full_time, 1),
            },
            "vector_only": {
                "context_recall": vec_recall,
                "chunks_found": len(vec_chunks),
                "time_ms": round(vec_time, 1),
            },
            "graph_uplift": uplift,
        }
        results.append(result)

        status = "GRAPH+" if uplift > 0 else ("EQUAL" if uplift == 0 else "VECTOR+")
        print(f"recall: {full_recall:.2f} vs {vec_recall:.2f} ({status}, +{uplift:.3f})")

    # Aggregate
    avg_full_recall = sum(r["full_pipeline"]["context_recall"] for r in results) / len(results)
    avg_vec_recall = sum(r["vector_only"]["context_recall"] for r in results) / len(results)
    avg_uplift = sum(r["graph_uplift"] for r in results) / len(results)

    multi_hop = [r for r in results if r["requires_graph"]]
    avg_multihop_uplift = sum(r["graph_uplift"] for r in multi_hop) / len(multi_hop) if multi_hop else 0

    return {
        "layer": "L2_Retrieval_Quality",
        "per_question": results,
        "aggregates": {
            "avg_full_pipeline_recall": round(avg_full_recall, 3),
            "avg_vector_only_recall": round(avg_vec_recall, 3),
            "avg_graph_uplift": round(avg_uplift, 3),
            "avg_multihop_uplift": round(avg_multihop_uplift, 3),
            "questions_where_graph_helps": sum(1 for r in results if r["graph_uplift"] > 0),
            "questions_total": len(results),
        },
    }


if __name__ == "__main__":
    results = run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
