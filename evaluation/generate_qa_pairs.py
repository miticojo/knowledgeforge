"""Generate atomic QA pairs from document chunks for CompactRAG fast-path.

Based on "CompactRAG: Reducing LLM Calls and Token Overhead" (arXiv 2602.05728).
Reads chunks from Spanner, generates QA pairs via Gemini, embeds them, saves to JSON.

Usage:
  python generate_qa_pairs.py [--limit N]
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kb-agent"))

QA_GENERATION_PROMPT = """Analyze this document chunk and generate atomic question-answer pairs.

Rules:
- Each question must be under 15 words
- Questions must start with a question word (What, Which, Who, Where, When, How, Does, Is)
- Questions must use EXPLICIT entity names — never pronouns
- Answers must be EXACT verbatim substrings from the text (copy-paste, not paraphrase)
- Each QA pair captures a SINGLE minimal factual unit
- Cover ALL important entities, relationships, and facts in the chunk
- No duplicate questions

Document: {doc_title}
Page: {page}

Chunk text:
{chunk_text}

Return a JSON array of objects with "q" (question) and "a" (answer) fields.
JSON array:"""


def load_chunks_from_spanner() -> list[dict]:
    """Load all document chunks from Spanner."""
    from services.spanner_client import get_database
    from google.cloud.spanner_v1 import param_types

    db = get_database()
    chunks = []
    with db.snapshot() as snap:
        result = snap.execute_sql("""
            SELECT dc.chunk_id, dc.doc_id, dc.chunk_text, dc.page_number, doc.title
            FROM DocumentChunks dc
            JOIN Documents doc ON doc.doc_id = dc.doc_id
            WHERE dc.chunk_type = 'text' AND dc.chunk_text IS NOT NULL
            ORDER BY doc.title, dc.chunk_index
        """)
        for row in result:
            chunks.append({
                "chunk_id": row[0],
                "doc_id": row[1],
                "chunk_text": row[2],
                "page": row[3],
                "doc_title": row[4],
            })
    return chunks


def generate_qa_pairs(chunk: dict, client) -> list[dict]:
    """Generate QA pairs from a single chunk using Gemini."""
    from google.genai.types import GenerateContentConfig

    prompt = QA_GENERATION_PROMPT.format(
        doc_title=chunk["doc_title"],
        page=chunk.get("page", "?"),
        chunk_text=chunk["chunk_text"][:2000],
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                service_tier="flex",  # 50% cost reduction
            ),
        )
        pairs = json.loads(response.text or "[]")
        if not isinstance(pairs, list):
            return []

        results = []
        for p in pairs:
            q = p.get("q", "").strip()
            a = p.get("a", "").strip()
            if q and a and len(q.split()) <= 20:
                results.append({
                    "question": q,
                    "answer": a,
                    "doc_title": chunk["doc_title"],
                    "page": chunk.get("page"),
                    "chunk_id": chunk["chunk_id"],
                })
        return results
    except Exception as e:
        print(f"    QA generation failed: {e}")
        return []


def embed_qa_pairs(qa_pairs: list[dict], client) -> list[dict]:
    """Embed QA pairs using gemini-embedding-2 (question;answer concatenation)."""
    from services.document_chunker import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS
    from google.genai.types import EmbedContentConfig

    # Concatenate question + answer for embedding (CompactRAG approach)
    texts = [f"{p['question']} {p['answer']}" for p in qa_pairs]

    _BATCH = 100
    all_embeddings = []
    for i in range(0, len(texts), _BATCH):
        batch = texts[i:i + _BATCH]
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=batch,
                config=EmbedContentConfig(
                    output_dimensionality=EMBEDDING_DIMENSIONS,
                ),
            )
            all_embeddings.extend([list(e.values) for e in response.embeddings])
        except Exception as e:
            print(f"    Embedding batch {i} failed: {e}")
            all_embeddings.extend([[0.0] * EMBEDDING_DIMENSIONS] * len(batch))

    for pair, emb in zip(qa_pairs, all_embeddings):
        pair["embedding"] = emb

    return qa_pairs


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of chunks to process")
    args = parser.parse_args()

    from google import genai
    from concurrent.futures import ThreadPoolExecutor, as_completed

    _project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not _project:
        raise SystemExit("GOOGLE_CLOUD_PROJECT env var is required")
    # Use Vertex AI client for generation (supports service_tier="flex" = 50% cost savings)
    gen_client = genai.Client(vertexai=True, project=_project, location="us-central1")
    # Use AI Studio client for embeddings (gemini-embedding-2-preview not on Vertex in EU)
    emb_client = genai.Client()

    # 1. Load chunks from Spanner
    print("Loading chunks from Spanner...")
    chunks = load_chunks_from_spanner()
    if args.limit:
        chunks = chunks[:args.limit]
    print(f"  {len(chunks)} chunks loaded")

    # 2. Generate QA pairs (parallel with Flex tier)
    print("Generating QA pairs (Vertex AI Flex, parallel)...")
    all_qa = []
    _MAX_WORKERS = 5  # Parallel LLM calls

    def _gen_chunk(i_chunk):
        i, chunk = i_chunk
        return i, generate_qa_pairs(chunk, gen_client)

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        futures = {executor.submit(_gen_chunk, (i, c)): i for i, c in enumerate(chunks)}
        done = 0
        for future in as_completed(futures):
            i, pairs = future.result()
            all_qa.extend(pairs)
            done += 1
            if done % 50 == 0:
                print(f"  [{done}/{len(chunks)}] {len(all_qa)} pairs so far...")
    print(f"  {len(all_qa)} QA pairs generated from {len(chunks)} chunks")

    # 3. Embed QA pairs
    print("Embedding QA pairs...")
    all_qa = embed_qa_pairs(all_qa, emb_client)
    print(f"  {len(all_qa)} QA pairs embedded")

    # 4. Save to JSON (without embeddings in readable file)
    out_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(out_dir, exist_ok=True)

    # Full file with embeddings (for search)
    full_path = os.path.join(out_dir, "qa_pairs_embedded.json")
    with open(full_path, "w") as f:
        json.dump(all_qa, f, ensure_ascii=False)
    print(f"  Full QA pairs saved: {full_path}")

    # Summary without embeddings (for review)
    summary = [{k: v for k, v in p.items() if k != "embedding"} for p in all_qa]
    summary_path = os.path.join(out_dir, "qa_pairs_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  Summary saved: {summary_path}")

    # Stats
    docs = set(p["doc_title"] for p in all_qa)
    print(f"\n{'=' * 50}")
    print(f"QA PAIR GENERATION COMPLETE")
    print(f"{'=' * 50}")
    print(f"  Documents: {len(docs)}")
    print(f"  Chunks processed: {len(chunks)}")
    print(f"  QA pairs generated: {len(all_qa)}")
    print(f"  Avg pairs/chunk: {len(all_qa)/len(chunks):.1f}")


if __name__ == "__main__":
    main()
