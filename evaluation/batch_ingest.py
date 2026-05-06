"""Batch ingestion of evaluation PDFs into the KB.

Uses Gemini to extract ArchiMate entities (like the ProcessingAgent does),
then normalizes and persists via the existing tool functions.

Usage:
  GOOGLE_API_KEY=... GOOGLE_CLOUD_PROJECT=... SPANNER_INSTANCE=... SPANNER_DATABASE=... \
  python batch_ingest.py [--start N] [--only N] [--dry-run]
"""
import glob
import json
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kb-agent"))

# Load environment variables from agent .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "kb-agent", ".env"), override=True)

from pypdf import PdfReader
from services.tenant_context import set_tenant, SHARED_ARCHISURANCE

# Set tenant for batch ingestion (default: __shared__:archisurance)
_batch_tenant = os.getenv("TENANT_ID", SHARED_ARCHISURANCE)
set_tenant(_batch_tenant)

def extract_text_from_pdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def ingest_document(text: str, pdf_name: str) -> dict:
    """Run the full ingestion pipeline on a single document.

    Uses the Controlled Generation path (process_document + write_to_spanner)
    which extracts confidence labels (EXTRACTED/INFERRED/AMBIGUOUS) on edges.
    """
    import agents.processing as proc

    # Set the document text in global state (both fields needed for proper chunking)
    proc._last_doc_text = text
    proc._full_document_text = text
    proc._full_document_images = []
    result = {"steps": {}}

    # Step 1: Extract metadata
    print(f"    [1/3] metadata...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        title_parts = pdf_name.replace("doc_", "").replace(".pdf", "").split("_")
        title = " ".join(w.capitalize() for w in title_parts[1:])
        proc.extract_metadata(
            title=title or "Architecture Document",
            author="ArchiSurance EA Team",
            document_type="Architecture Document",
            key_topics=["ArchiMate", "enterprise architecture", "insurance"],
        )
        result["steps"]["metadata"] = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000)}
        print(f"ok ({result['steps']['metadata']['ms']}ms)")
    except Exception as e:
        result["steps"]["metadata"] = {"status": "error", "error": str(e)[:200]}
        print(f"FAILED: {e}")
        return result

    # Step 2: Parallel pipeline (embeddings + Controlled Gen graph + entity search)
    print(f"    [2/3] process_document (embeddings + graph + entity search)...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        proc_json = proc.process_document(
            summary=text[:2000],
            search_themes="ArchiMate enterprise architecture insurance"
        )
        proc_data = json.loads(proc_json)
        ms = round((time.perf_counter() - t0) * 1000)
        graph_info = proc_data.get("graph", {})
        result["steps"]["process"] = {
            "status": "ok",
            "ms": ms,
            "nodes": graph_info.get("total_nodes", 0),
            "edges": graph_info.get("total_edges", 0),
            "chunks": proc_data.get("embedding", {}).get("chunks", 0),
        }
        print(f"ok ({ms}ms) — {graph_info.get('total_nodes', 0)} nodes, {graph_info.get('total_edges', 0)} edges")
    except Exception as e:
        result["steps"]["process"] = {"status": "error", "error": str(e)[:200]}
        print(f"FAILED: {e}")
        return result

    # Step 3: Write to Spanner
    print(f"    [3/3] write to Spanner...", end=" ", flush=True)
    t0 = time.perf_counter()
    try:
        write_json = proc.write_to_spanner("OK")
        write_data = json.loads(write_json)
        ms = round((time.perf_counter() - t0) * 1000)
        result["steps"]["write"] = {
            "status": "ok",
            "ms": ms,
            "doc_id": write_data.get("document_id"),
            "entities": write_data.get("entities", 0),
            "edges": write_data.get("edges", 0),
            "chunks": write_data.get("chunks", 0),
        }
        print(f"ok ({ms}ms) — {write_data.get('chunks', 0)} chunks written")
    except Exception as e:
        result["steps"]["write"] = {"status": "error", "error": str(e)[:200]}
        print(f"FAILED: {e}")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1, help="Start from doc N")
    parser.add_argument("--only", type=int, help="Ingest only doc N")
    parser.add_argument("--dry-run", action="store_true", help="Extract text only, don't ingest")
    args = parser.parse_args()

    pdf_dir = os.path.join(os.path.dirname(__file__), "data", "archisurance")
    pdfs = sorted(glob.glob(os.path.join(pdf_dir, "doc_*.pdf")))

    if args.only:
        pdfs = [p for p in pdfs if f"doc_{args.only:02d}" in p]
    else:
        pdfs = pdfs[args.start - 1:]

    print(f"{'=' * 60}")
    print(f"BATCH INGESTION: {len(pdfs)} documents")
    print(f"{'=' * 60}")

    all_results = []
    t_start = time.perf_counter()

    for i, pdf_path in enumerate(pdfs):
        filename = os.path.basename(pdf_path)
        print(f"\n[{i + 1}/{len(pdfs)}] {filename}")

        print(f"    Extracting text...", end=" ", flush=True)
        text = extract_text_from_pdf(pdf_path)
        print(f"{len(text)} chars, {text.count(chr(12)) + 1} pages")

        if args.dry_run:
            all_results.append({"document": filename, "text_length": len(text), "dry_run": True})
            continue

        if len(text) < 200:
            print(f"    SKIPPED: text too short")
            continue

        t0 = time.perf_counter()
        result = ingest_document(text, filename)
        result["document"] = filename
        result["text_length"] = len(text)
        result["total_seconds"] = round(time.perf_counter() - t0, 1)
        all_results.append(result)

        # Rate limit: avoid Gemini quota issues
        if i < len(pdfs) - 1:
            time.sleep(2)

    total = time.perf_counter() - t_start

    # Save
    out_path = os.path.join(os.path.dirname(__file__), "results", "batch_ingest_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"BATCH INGESTION COMPLETE")
    print(f"{'=' * 60}")
    ok = [r for r in all_results if r.get("steps", {}).get("write", {}).get("status") == "ok"]
    print(f"  Success: {len(ok)}/{len(all_results)}")
    print(f"  Total chunks: {sum(r['steps']['write'].get('chunks', 0) for r in ok)}")
    print(f"  Total nodes:  {sum(r['steps'].get('process', {}).get('nodes', 0) for r in ok)}")
    print(f"  Total edges:  {sum(r['steps'].get('process', {}).get('edges', 0) for r in ok)}")
    print(f"  Total time:   {total:.0f}s ({total / 60:.1f}min)")
    print(f"  Results:      {out_path}")


if __name__ == "__main__":
    main()
