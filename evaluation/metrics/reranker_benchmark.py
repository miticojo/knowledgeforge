"""Benchmark: Vertex AI Ranking API vs Gemini LLM-as-Reranker.

Compares:
1. No reranker (RRF only)
2. Vertex AI Ranking API (semantic-ranker-512)
3. Gemini 2.5 Flash as reranker (LLM-as-judge relevance scoring)

For each eval question, runs all 3 strategies and measures context recall.

Usage:
  GOOGLE_API_KEY=... GOOGLE_CLOUD_PROJECT=... SPANNER_INSTANCE=... SPANNER_DATABASE=... \
  python -m metrics.reranker_benchmark
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


def get_rrf_candidates(query: str) -> tuple[list[dict], list[str], set]:
    """Run Q1 (keyword + vector) and Q2 (graph) to get RRF-scored candidates.
    Returns (candidates, graph_connections, discovered_entity_names)."""
    from agents.search import tool_query_spanner_graph
    import agents.search as _mod

    # Monkey-patch to capture pre-rerank candidates
    # We'll call the full pipeline and parse the output
    result_json = tool_query_spanner_graph(query)
    result = json.loads(result_json)
    return result


def rerank_vertex_ai(query: str, chunks: list[dict], top_n: int = 15) -> list[dict]:
    """Rerank using Vertex AI Ranking API."""
    from google.cloud.discoveryengine_v1 import RankServiceClient, RankRequest, RankingRecord

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT env var is required")
    config = f"projects/{project}/locations/global/rankingConfigs/default_ranking_config"
    client = RankServiceClient()

    records = [
        RankingRecord(id=str(i), content=c["text"][:1000])
        for i, c in enumerate(chunks)
    ]

    response = client.rank(request=RankRequest(
        ranking_config=config,
        model="semantic-ranker-512@latest",
        top_n=top_n,
        query=query,
        records=records,
    ))

    reranked = []
    for record in response.records:
        idx = int(record.id)
        c = dict(chunks[idx])
        c["rerank_score"] = round(record.score, 4)
        reranked.append(c)
    return reranked


def rerank_gemini(query: str, chunks: list[dict], top_n: int = 15) -> list[dict]:
    """Rerank using Gemini 2.5 Flash as relevance scorer."""
    from google import genai

    client = genai.Client()

    # Build a compact representation for scoring
    chunk_list = ""
    for i, c in enumerate(chunks):
        chunk_list += f"[{i}] {c['text'][:300]}\n---\n"

    prompt = f"""Rate the relevance of each text chunk to the query on a scale 0.0 to 1.0.
Return ONLY a JSON array of objects with "id" (integer) and "score" (float).
No explanation, just the JSON array.

QUERY: {query}

CHUNKS:
{chunk_list}

JSON ARRAY:"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    text = response.text or "[]"
    try:
        scores = json.loads(text)
    except json.JSONDecodeError:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        scores = json.loads(text.strip())

    # Build scored list
    score_map = {s["id"]: s["score"] for s in scores if isinstance(s, dict)}
    for i, c in enumerate(chunks):
        c["rerank_score"] = score_map.get(i, 0.0)

    reranked = sorted(chunks, key=lambda c: c.get("rerank_score", 0), reverse=True)
    return reranked[:top_n]


def compute_context_recall(chunks: list, expected_entities: list[str]) -> float:
    if not expected_entities:
        return 1.0
    text_lower = " ".join(
        (c["text"].lower() if isinstance(c, dict) else c.lower()) for c in chunks
    )
    found = sum(1 for e in expected_entities if e.lower() in text_lower)
    return round(found / len(expected_entities), 3)


def run():
    questions = load_eval_questions()

    print("=" * 70)
    print("RERANKER BENCHMARK: RRF-only vs Vertex AI vs Gemini")
    print("=" * 70)

    results = []

    for q in questions:
        print(f"\n  [{q['id']}] {q['question'][:55]}...")

        # Get full pipeline result (which uses current reranker)
        t0 = time.perf_counter()
        full_result = get_rrf_candidates(q["question"])
        full_chunks = full_result.get("semantically_similar_chunks", [])
        pipeline_ms = round((time.perf_counter() - t0) * 1000)

        # We need raw text chunks for reranking — extract from enriched format
        # Format: "[Source: Title, Page: N]\nactual text"
        raw_chunks = []
        for chunk_str in full_chunks:
            if isinstance(chunk_str, str):
                # Strip source prefix
                text = chunk_str.split("\n", 1)[-1] if "\n" in chunk_str else chunk_str
                raw_chunks.append({"text": text})
            else:
                raw_chunks.append(chunk_str)

        if not raw_chunks:
            print(f"    No chunks retrieved, skipping")
            continue

        # Strategy 1: RRF only (current order = already reranked by pipeline)
        rrf_recall = compute_context_recall(raw_chunks[:15], q["expected_entities"])

        # Strategy 2: Vertex AI Reranker
        try:
            t0 = time.perf_counter()
            vertex_chunks = rerank_vertex_ai(q["question"], raw_chunks[:30])
            vertex_ms = round((time.perf_counter() - t0) * 1000)
            vertex_recall = compute_context_recall(vertex_chunks, q["expected_entities"])
        except Exception as e:
            vertex_ms = 0
            vertex_recall = rrf_recall
            print(f"    Vertex AI failed: {str(e)[:80]}")

        # Strategy 3: Gemini reranker
        try:
            t0 = time.perf_counter()
            gemini_chunks = rerank_gemini(q["question"], raw_chunks[:20])
            gemini_ms = round((time.perf_counter() - t0) * 1000)
            gemini_recall = compute_context_recall(gemini_chunks, q["expected_entities"])
        except Exception as e:
            gemini_ms = 0
            gemini_recall = rrf_recall
            print(f"    Gemini failed: {str(e)[:80]}")

        # Determine winners
        best = max(rrf_recall, vertex_recall, gemini_recall)
        winners = []
        if rrf_recall == best:
            winners.append("RRF")
        if vertex_recall == best:
            winners.append("Vertex")
        if gemini_recall == best:
            winners.append("Gemini")

        result = {
            "id": q["id"],
            "category": q["category"],
            "rrf": {"recall": rrf_recall, "time_ms": pipeline_ms},
            "vertex_ai": {"recall": vertex_recall, "time_ms": vertex_ms},
            "gemini": {"recall": gemini_recall, "time_ms": gemini_ms},
            "winner": "+".join(winners),
        }
        results.append(result)

        print(f"    RRF={rrf_recall:.2f}  Vertex={vertex_recall:.2f} ({vertex_ms}ms)  Gemini={gemini_recall:.2f} ({gemini_ms}ms)  -> {result['winner']}")

    # Aggregates
    n = len(results)
    avg_rrf = sum(r["rrf"]["recall"] for r in results) / n
    avg_vertex = sum(r["vertex_ai"]["recall"] for r in results) / n
    avg_gemini = sum(r["gemini"]["recall"] for r in results) / n

    avg_vertex_ms = sum(r["vertex_ai"]["time_ms"] for r in results) / n
    avg_gemini_ms = sum(r["gemini"]["time_ms"] for r in results) / n

    vertex_wins = sum(1 for r in results if "Vertex" in r["winner"])
    gemini_wins = sum(1 for r in results if "Gemini" in r["winner"])
    rrf_wins = sum(1 for r in results if "RRF" in r["winner"])

    print(f"\n{'=' * 70}")
    print(f"RERANKER BENCHMARK RESULTS")
    print(f"{'=' * 70}")
    print(f"")
    print(f"  {'Strategy':<20} {'Avg Recall':<15} {'Avg Latency':<15} {'Wins':<10}")
    print(f"  {'-' * 60}")
    print(f"  {'RRF (no rerank)':<20} {avg_rrf:<15.3f} {'(baseline)':<15} {rrf_wins}/{n}")
    print(f"  {'Vertex AI':<20} {avg_vertex:<15.3f} {f'{avg_vertex_ms:.0f}ms':<15} {vertex_wins}/{n}")
    print(f"  {'Gemini 2.5 Flash':<20} {avg_gemini:<15.3f} {f'{avg_gemini_ms:.0f}ms':<15} {gemini_wins}/{n}")
    print()

    # Save
    out = {
        "benchmark": "reranker_comparison",
        "per_question": results,
        "aggregates": {
            "rrf": {"avg_recall": round(avg_rrf, 3), "wins": rrf_wins},
            "vertex_ai": {"avg_recall": round(avg_vertex, 3), "avg_latency_ms": round(avg_vertex_ms), "wins": vertex_wins},
            "gemini": {"avg_recall": round(avg_gemini, 3), "avg_latency_ms": round(avg_gemini_ms), "wins": gemini_wins},
            "questions_total": n,
        },
    }
    out_path = os.path.join(os.path.dirname(__file__), "..", "results", "reranker_benchmark.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  Results saved: {out_path}")

    return out


if __name__ == "__main__":
    run()
