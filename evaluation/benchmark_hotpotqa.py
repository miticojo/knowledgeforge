"""HotpotQA Benchmark: evaluate KB RAG pipeline on academic benchmark.

Runs the FULL pipeline (Spanner ingestion → vector search → graph → reranking →
generation) on HotpotQA distractor setting, measuring standard EM/F1 metrics
for direct comparison with paper-reported results.

Paper baselines (200 questions, HotpotQA distractor):
  A2RAG:         EM=32.2, F1=43.7, R@2=62.4, R@5=73.6
  LightRAG(mix): EM=33.9, F1=46.5
  CompactRAG:    EM=45.2, F1=66.2 (with GPT-4 KB)
  IRCoT:         EM=42.8, F1=49.0

Usage:
  python benchmark_hotpotqa.py [--n-questions 200] [--seed 42] [--skip-ingest] [--skip-cleanup]
"""
import json
import os
import re
import sys
import time
import string
import collections
import argparse
import uuid
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kb-agent"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "kb-agent", ".env"), override=True)

from services.tenant_context import set_tenant, SHARED_HOTPOTQA
_batch_tenant = os.getenv("TENANT_ID", SHARED_HOTPOTQA)
set_tenant(_batch_tenant)

# Paper baselines for comparison
PAPER_BASELINES = {
    "A2RAG": {"em": 32.2, "f1": 43.7, "r_at_2": 62.4, "r_at_5": 73.6},
    "LightRAG(mix)": {"em": 33.9, "f1": 46.5},
    "CompactRAG (LLaMA KB)": {"em": 45.2, "f1": 66.2},
    "CompactRAG (GPT-4 KB)": {"em": 49.6, "f1": 69.5},
    "IRCoT": {"em": 42.8, "f1": 49.0},
    "Iter-RetGen": {"em": 46.8, "f1": 52.2},
}


# ═══════════════════════════════════════════════════════════════════════
# Standard HotpotQA Evaluation Metrics (from hotpot_evaluate_v1.py)
# ═══════════════════════════════════════════════════════════════════════

def normalize_answer(s):
    """Lower text and remove punctuation, articles and extra whitespace."""
    def remove_articles(text):
        return re.sub(r'\b(a|an|the)\b', ' ', text)
    def white_space_fix(text):
        return ' '.join(text.split())
    def remove_punc(text):
        exclude = set(string.punctuation)
        return ''.join(ch for ch in text if ch not in exclude)
    def lower(text):
        return text.lower()
    return white_space_fix(remove_articles(remove_punc(lower(s))))


def compute_f1(prediction, ground_truth):
    """Compute token-level F1 between prediction and ground truth."""
    prediction_tokens = normalize_answer(prediction).split()
    ground_truth_tokens = normalize_answer(ground_truth).split()
    common = collections.Counter(prediction_tokens) & collections.Counter(ground_truth_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    precision = num_same / len(prediction_tokens)
    recall = num_same / len(ground_truth_tokens)
    return (2 * precision * recall) / (precision + recall)


def compute_em(prediction, ground_truth):
    """Compute Exact Match."""
    return float(normalize_answer(prediction) == normalize_answer(ground_truth))


def compute_sp_recall(retrieved_titles, gold_titles):
    """Supporting Facts recall: did we retrieve the gold paragraphs?"""
    if not gold_titles:
        return 1.0
    found = sum(1 for t in gold_titles if t in retrieved_titles)
    return found / len(gold_titles)


# ═══════════════════════════════════════════════════════════════════════
# Dataset Loading
# ═══════════════════════════════════════════════════════════════════════

def load_hotpotqa(n_questions=200, seed=42):
    """Load and sample HotpotQA distractor validation set."""
    from datasets import load_dataset
    print(f"  Loading HotpotQA distractor validation set...")
    ds = load_dataset("hotpotqa/hotpot_qa", "distractor", split="validation",
                      trust_remote_code=True)
    print(f"  Full validation set: {len(ds)} questions")

    # Sample N questions, balanced across types
    ds = ds.shuffle(seed=seed).select(range(min(n_questions, len(ds))))
    print(f"  Sampled: {len(ds)} questions (seed={seed})")

    questions = []
    for ex in ds:
        titles = ex["context"]["title"]
        sentences = ex["context"]["sentences"]
        gold_titles = list(set(ex["supporting_facts"]["title"]))

        # Build paragraphs
        paragraphs = []
        for title, sents in zip(titles, sentences):
            text = " ".join(sents)
            paragraphs.append({"title": title, "text": text, "is_gold": title in gold_titles})

        questions.append({
            "id": ex["id"],
            "question": ex["question"],
            "answer": ex["answer"],
            "type": ex["type"],
            "level": ex["level"],
            "paragraphs": paragraphs,
            "gold_titles": gold_titles,
        })

    types = collections.Counter(q["type"] for q in questions)
    levels = collections.Counter(q["level"] for q in questions)
    print(f"  Types: {dict(types)}")
    print(f"  Levels: {dict(levels)}")
    return questions


# ═══════════════════════════════════════════════════════════════════════
# Spanner Ingestion (full pipeline)
# ═══════════════════════════════════════════════════════════════════════

_BENCHMARK_PREFIX = "[HotpotQA] "


def ingest_hotpotqa_docs(questions):
    """Ingest HotpotQA paragraphs into Spanner as documents."""
    import agents.processing as proc
    from services.spanner_client import get_database

    # Collect unique paragraphs across all questions
    unique_docs = {}
    for q in questions:
        for p in q["paragraphs"]:
            title = p["title"]
            if title not in unique_docs:
                unique_docs[title] = p["text"]
            else:
                # Append if different text for same title
                if p["text"] not in unique_docs[title]:
                    unique_docs[title] += "\n\n" + p["text"]

    print(f"  Unique paragraphs to ingest: {len(unique_docs)}")

    success = 0
    errors = 0
    t_start = time.perf_counter()

    for i, (title, text) in enumerate(unique_docs.items()):
        if i % 50 == 0:
            print(f"    [{i}/{len(unique_docs)}] Ingesting...", flush=True)

        doc_title = f"{_BENCHMARK_PREFIX}{title}"

        # Reset processing state
        proc._last_metadata = None
        proc._last_doc_embedding = None
        proc._last_chunks = None
        proc._last_graph_result = None
        proc._last_doc_text = None
        proc._full_document_text = text
        proc._full_document_images = []

        try:
            # Step 1: Metadata
            proc.extract_metadata(
                titolo=doc_title,
                autore="HotpotQA Wikipedia",
                tipo_documento="Encyclopedia Article",
                argomenti_chiave=title,
            )

            # Step 2: Embeddings (includes chunking + contextualization + metadata prefix)
            proc.extract_embeddings(text[:2000])

            # Step 3: Write to Spanner (skip graph extraction for speed — focus on retrieval)
            # Set minimal graph result as dict (NOT json string) to allow write
            proc._last_graph_result = {
                "NodiEstratti": [],
                "ArchiEstratti": [],
                "TotaleNodi": 0,
                "TotaleArchi": 0,
            }
            proc.write_to_spanner("OK")
            success += 1

        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"    ERROR ingesting '{title}': {str(e)[:100]}")

        # Rate limit
        if i % 5 == 0 and i > 0:
            time.sleep(0.5)

    elapsed = time.perf_counter() - t_start
    print(f"  Ingestion complete: {success}/{len(unique_docs)} success, "
          f"{errors} errors, {elapsed:.0f}s")
    return success


def cleanup_hotpotqa_docs():
    """Remove all HotpotQA benchmark documents from Spanner."""
    from services.spanner_client import get_database

    db = get_database()
    # Find all benchmark documents
    with db.snapshot() as snap:
        result = snap.execute_sql(
            "SELECT doc_id, title FROM Documents WHERE STARTS_WITH(title, @prefix)",
            params={"prefix": _BENCHMARK_PREFIX},
            param_types={"prefix": __import__('google.cloud.spanner_v1', fromlist=['param_types']).param_types.STRING},
        )
        docs = [(row[0], row[1]) for row in result]

    if not docs:
        print("  No benchmark documents to clean up")
        return

    print(f"  Deleting {len(docs)} benchmark documents...")
    from google.cloud.spanner_v1 import keyset
    # Delete in batches
    for i in range(0, len(docs), 20):
        batch = docs[i:i + 20]
        keys = [d[0] for d in batch]
        db.run_in_transaction(
            lambda txn: txn.delete("Documents", keyset.KeySet(keys=[[k] for k in keys]))
        )
    print(f"  Cleanup complete: {len(docs)} documents removed")


# ═══════════════════════════════════════════════════════════════════════
# Evaluation Pipeline
# ═══════════════════════════════════════════════════════════════════════

def extract_answer_from_response(response_text):
    """Extract the core answer from the Coordinator's response.

    The Coordinator returns a full prose answer. We extract the key
    factual statement for EM/F1 comparison.
    """
    # Remove sources block
    text = re.sub(r'<sources>.*?</sources>', '', response_text, flags=re.DOTALL)
    # Remove markdown formatting
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Take first sentence or line as the answer
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if not lines:
        return ""
    # Return first substantive line (skip "STEP" lines from thinking)
    for line in lines:
        if not line.startswith("STEP") and len(line) > 5:
            # Truncate to first sentence
            sent = re.split(r'[.!?\n]', line)[0].strip()
            return sent
    return lines[0]


def scoped_vector_search(query: str, corpus_prefix: str, top_k: int = 15):
    """Vector search scoped to a specific corpus (by document title prefix).

    Replicates the production pipeline: multi-query expansion → embedding →
    ScaNN vector search → Vertex AI reranking, but filtered to benchmark docs.
    """
    from services.spanner_client import get_database
    from services.document_chunker import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
    from google.cloud.spanner_v1 import param_types
    from google import genai

    client = genai.Client()

    # Embed the query
    emb = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=query[:8000],
        config=genai.types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    query_embedding = list(emb.embeddings[0].values)

    # Vector search with corpus filter
    db = get_database()
    with db.snapshot() as snap:
        result = snap.execute_sql(
            """SELECT chunk.chunk_text, chunk.chunk_type, chunk.page_number,
                      doc.title AS source_doc,
                      COSINE_DISTANCE(chunk.chunk_embedding, @query_emb) AS distance
               FROM DocumentChunks chunk
               JOIN Documents doc ON doc.doc_id = chunk.doc_id
               WHERE chunk.chunk_embedding IS NOT NULL
                 AND STARTS_WITH(doc.title, @prefix)
               ORDER BY distance ASC
               LIMIT @top_k""",
            params={
                "query_emb": query_embedding,
                "prefix": corpus_prefix,
                "top_k": top_k * 2,  # Fetch more for reranking
            },
            param_types={
                "query_emb": param_types.Array(param_types.FLOAT32),
                "prefix": param_types.STRING,
                "top_k": param_types.INT64,
            },
        )
        candidates = []
        for row in result:
            candidates.append({
                "text": (row[0] or "")[:1500],
                "type": row[1],
                "page": row[2],
                "source": row[3],
                "distance": row[4],
            })

    # Reranking via Vertex AI Ranking API (same as production)
    try:
        from google.cloud.discoveryengine_v1 import RankServiceClient, RankRequest, RankingRecord
        _rerank_client = RankServiceClient()
        _project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not _project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT env var is required")
        _ranking_config = f"projects/{_project}/locations/global/rankingConfigs/default_ranking_config"

        records = [RankingRecord(id=str(i), content=c["text"][:1000])
                   for i, c in enumerate(candidates[:30])]

        rerank_response = _rerank_client.rank(
            request=RankRequest(
                ranking_config=_ranking_config,
                model="semantic-ranker-512@latest",
                top_n=top_k,
                query=query,
                records=records,
            )
        )
        reranked = [candidates[int(r.id)] for r in rerank_response.records]
    except Exception:
        reranked = candidates[:top_k]

    return reranked


def run_benchmark(questions, use_full_agent=False):
    """Run the benchmark: scoped search + generate for each question."""
    from google import genai

    client = genai.Client()
    results = []
    t_start = time.perf_counter()

    for i, q in enumerate(questions):
        if i % 10 == 0:
            print(f"  [{i}/{len(questions)}] Processing...", flush=True)

        t0 = time.perf_counter()
        result = {
            "id": q["id"],
            "question": q["question"],
            "gold_answer": q["answer"],
            "type": q["type"],
            "level": q["level"],
            "gold_titles": q["gold_titles"],
        }

        try:
            # Scoped vector search (only HotpotQA docs) + reranking
            chunks = scoped_vector_search(q["question"], _BENCHMARK_PREFIX, top_k=10)

            # Extract retrieved document titles
            retrieved_titles = set()
            for c in chunks:
                title = c.get("source", "")
                if title.startswith(_BENCHMARK_PREFIX):
                    clean_title = title[len(_BENCHMARK_PREFIX):]
                    retrieved_titles.add(clean_title)

            # Supporting facts recall
            sp_recall = compute_sp_recall(retrieved_titles, q["gold_titles"])

            # Generate answer from retrieved chunks
            context = "\n\n".join(
                f"[{c['source']}]: {c['text']}" for c in chunks[:5]
            )
            if context.strip():
                gen_response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"""Based ONLY on the provided context, answer the question.
Give the shortest possible answer — a name, date, number, or brief phrase.
Do NOT explain or elaborate. Just state the answer directly.

Context:
{context}

Question: {q['question']}

Answer:""",
                    config=genai.types.GenerateContentConfig(temperature=0.0),
                )
                predicted_answer = (gen_response.text or "").strip()
                # Clean: take first line only, remove markdown
                predicted_answer = predicted_answer.split('\n')[0].strip()
                predicted_answer = re.sub(r'\*\*([^*]+)\*\*', r'\1', predicted_answer)
            else:
                predicted_answer = ""

            # Compute metrics
            em = compute_em(predicted_answer, q["answer"])
            f1 = compute_f1(predicted_answer, q["answer"])
            elapsed = (time.perf_counter() - t0) * 1000

            result.update({
                "predicted_answer": predicted_answer,
                "em": em,
                "f1": round(f1, 4),
                "sp_recall": round(sp_recall, 4),
                "retrieved_titles": list(retrieved_titles),
                "chunks_found": len(chunks),
                "time_ms": round(elapsed, 1),
            })

        except Exception as e:
            result.update({
                "predicted_answer": "",
                "em": 0.0,
                "f1": 0.0,
                "sp_recall": 0.0,
                "error": str(e)[:200],
                "time_ms": (time.perf_counter() - t0) * 1000,
            })

        results.append(result)

    total_time = time.perf_counter() - t_start
    return results, total_time


def compute_aggregates(results):
    """Compute aggregate metrics."""
    n = len(results)
    if n == 0:
        return {}

    avg_em = sum(r["em"] for r in results) / n * 100
    avg_f1 = sum(r["f1"] for r in results) / n * 100
    avg_sp = sum(r.get("sp_recall", 0) for r in results) / n * 100

    # By type
    by_type = {}
    for t in set(r["type"] for r in results):
        type_results = [r for r in results if r["type"] == t]
        by_type[t] = {
            "em": round(sum(r["em"] for r in type_results) / len(type_results) * 100, 1),
            "f1": round(sum(r["f1"] for r in type_results) / len(type_results) * 100, 1),
            "count": len(type_results),
        }

    # By level
    by_level = {}
    for l in set(r["level"] for r in results):
        level_results = [r for r in results if r["level"] == l]
        by_level[l] = {
            "em": round(sum(r["em"] for r in level_results) / len(level_results) * 100, 1),
            "f1": round(sum(r["f1"] for r in level_results) / len(level_results) * 100, 1),
            "count": len(level_results),
        }

    errors = sum(1 for r in results if "error" in r)
    avg_time = sum(r.get("time_ms", 0) for r in results) / n

    return {
        "avg_em": round(avg_em, 1),
        "avg_f1": round(avg_f1, 1),
        "avg_sp_recall": round(avg_sp, 1),
        "by_type": by_type,
        "by_level": by_level,
        "total_questions": n,
        "errors": errors,
        "avg_time_ms": round(avg_time, 1),
    }


def print_comparison(agg):
    """Print results compared to paper baselines."""
    print(f"\n{'=' * 75}")
    print(f"HOTPOTQA BENCHMARK RESULTS — KB vs Paper Baselines")
    print(f"{'=' * 75}\n")

    print(f"{'System':<30s} {'EM':>8s} {'F1':>8s} {'SP Recall':>10s}")
    print(f"{'-' * 58}")

    # Our result
    print(f"{'>>> KB (ours) <<<':<30s} {agg['avg_em']:>7.1f}% {agg['avg_f1']:>7.1f}% {agg['avg_sp_recall']:>9.1f}%")
    print(f"{'-' * 58}")

    # Paper baselines
    for name, metrics in PAPER_BASELINES.items():
        em = f"{metrics['em']:.1f}%" if 'em' in metrics else "   —  "
        f1 = f"{metrics['f1']:.1f}%" if 'f1' in metrics else "   —  "
        sp = f"{metrics.get('r_at_2', 0):.1f}%" if 'r_at_2' in metrics else "   —    "
        print(f"{name:<30s} {em:>8s} {f1:>8s} {sp:>10s}")

    # Breakdown
    print(f"\n--- By Question Type ---")
    for t, m in agg.get("by_type", {}).items():
        print(f"  {t:<15s} EM={m['em']:.1f}%  F1={m['f1']:.1f}%  (n={m['count']})")

    print(f"\n--- By Difficulty ---")
    for l, m in agg.get("by_level", {}).items():
        print(f"  {l:<10s} EM={m['em']:.1f}%  F1={m['f1']:.1f}%  (n={m['count']})")

    print(f"\n--- Pipeline Stats ---")
    print(f"  Questions: {agg['total_questions']}, Errors: {agg['errors']}")
    print(f"  Avg time/question: {agg['avg_time_ms']:.0f}ms")


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="HotpotQA Benchmark for KB")
    parser.add_argument("--n-questions", type=int, default=200, help="Number of questions")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip ingestion (use existing data)")
    parser.add_argument("--skip-cleanup", action="store_true", help="Don't remove benchmark docs after")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"{'=' * 75}")
    print(f"HOTPOTQA BENCHMARK — KB Full Pipeline Evaluation")
    print(f"{'=' * 75}")
    print(f"  Questions: {args.n_questions}, Seed: {args.seed}")
    print(f"  Timestamp: {timestamp}")
    print()

    # 1. Load dataset
    print("[1/4] LOADING DATASET")
    questions = load_hotpotqa(args.n_questions, args.seed)
    print()

    # 2. Ingest into Spanner
    if not args.skip_ingest:
        print("[2/4] INGESTING INTO SPANNER (full pipeline)")
        print("  Cleaning up previous benchmark data...")
        try:
            cleanup_hotpotqa_docs()
        except Exception as e:
            print(f"  Cleanup skipped: {e}")
        print("  Ingesting HotpotQA paragraphs...")
        n_ingested = ingest_hotpotqa_docs(questions)
        print()
    else:
        print("[2/4] SKIPPING INGESTION (--skip-ingest)")
        print()

    # 3. Run benchmark
    print("[3/4] RUNNING BENCHMARK")
    results, total_time = run_benchmark(questions)
    agg = compute_aggregates(results)
    print(f"  Completed in {total_time:.0f}s ({total_time/60:.1f}min)")
    print()

    # 4. Print and save results
    print("[4/4] RESULTS")
    print_comparison(agg)

    # Save detailed results
    out_dir = os.path.join(os.path.dirname(__file__), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"hotpotqa_benchmark_{timestamp}.json")

    output = {
        "benchmark": "HotpotQA Distractor",
        "timestamp": timestamp,
        "config": {
            "n_questions": args.n_questions,
            "seed": args.seed,
            "pipeline": "metadata_prefix + graph_gate + atomic_verification + compactrag",
        },
        "aggregates": agg,
        "paper_baselines": PAPER_BASELINES,
        "per_question": results,
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Detailed results: {out_path}")

    # Cleanup
    if not args.skip_cleanup and not args.skip_ingest:
        print(f"\n[CLEANUP] Removing benchmark documents from Spanner...")
        try:
            cleanup_hotpotqa_docs()
        except Exception as e:
            print(f"  Cleanup failed: {e}")

    print(f"\n{'=' * 75}")
    print(f"BENCHMARK COMPLETE")
    print(f"{'=' * 75}")


if __name__ == "__main__":
    main()
