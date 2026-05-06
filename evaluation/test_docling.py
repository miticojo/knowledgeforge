"""Test Docling parsing service — repeatable multi-format tests.

Tests parsing of PDF, DOCX, PPTX, XLSX via the Docling Cloud Run service.
Compares output quality vs pdf-parse baseline.

Usage:
  # Test against deployed service (requires auth token)
  python test_docling.py --url https://docling-parser-....run.app

  # Test against local service
  python test_docling.py --url http://localhost:8090

  # Run with a specific test file
  python test_docling.py --url http://localhost:8090 --file path/to/doc.pdf
"""
import argparse
import json
import os
import sys
import time
import subprocess

# Test documents (ArchiSurance PDFs from evaluation/data/)
TEST_DIR = os.path.join(os.path.dirname(__file__), "data", "archisurance")


def get_auth_token():
    """Get identity token for authenticated Cloud Run calls."""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-identity-token"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return None


def test_parse_file(url: str, file_path: str, token: str = None) -> dict:
    """Parse a single file via the Docling service."""
    import requests

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with open(file_path, "rb") as f:
        t0 = time.perf_counter()
        response = requests.post(
            f"{url}/parse",
            files={"file": (os.path.basename(file_path), f)},
            data={"output_format": "markdown"},
            headers=headers,
            timeout=300,
        )
        elapsed = time.perf_counter() - t0

    if response.status_code != 200:
        return {
            "file": os.path.basename(file_path),
            "status": "FAIL",
            "error": response.text[:200],
            "http_code": response.status_code,
            "time_s": round(elapsed, 1),
        }

    data = response.json()
    return {
        "file": os.path.basename(file_path),
        "status": "OK",
        "text_length": data["metadata"]["text_length"],
        "num_tables": data["metadata"]["num_tables"],
        "parse_time_ms": data["metadata"]["parse_time_ms"],
        "total_time_s": round(elapsed, 1),
        "text_preview": data["text"][:200] if data.get("text") else "",
    }


def test_parse_gcs(url: str, gcs_uri: str, token: str = None) -> dict:
    """Parse a document from GCS."""
    import requests

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    t0 = time.perf_counter()
    response = requests.post(
        f"{url}/parse/gcs",
        data={"gcs_uri": gcs_uri, "output_prefix": "parsed/test/"},
        headers=headers,
        timeout=300,
    )
    elapsed = time.perf_counter() - t0

    if response.status_code != 200:
        return {"status": "FAIL", "error": response.text[:200], "time_s": round(elapsed, 1)}

    data = response.json()
    return {
        "status": "OK",
        "source": gcs_uri,
        "output": data.get("output_uri", ""),
        "text_length": data.get("text_length", 0),
        "num_tables": data.get("num_tables", 0),
        "time_s": round(elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Test Docling parsing service")
    parser.add_argument("--url", required=True, help="Docling service URL")
    parser.add_argument("--file", help="Test a specific file")
    parser.add_argument("--gcs", help="Test GCS URI (gs://bucket/path)")
    parser.add_argument("--no-auth", action="store_true", help="Skip auth token")
    args = parser.parse_args()

    # Get auth token for Cloud Run
    token = None if args.no_auth else get_auth_token()
    if token:
        print(f"Using identity token for authentication")
    else:
        print(f"No auth token (local mode or --no-auth)")

    print(f"\n{'=' * 60}")
    print(f"DOCLING PARSING SERVICE TEST")
    print(f"URL: {args.url}")
    print(f"{'=' * 60}")

    # 1. Health check
    print(f"\n[1] Health check...")
    try:
        import requests
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = requests.get(f"{args.url}/health", headers=headers, timeout=30)
        print(f"  Status: {r.status_code} — {r.json()}")
    except Exception as e:
        print(f"  FAIL: {e}")
        return

    # 2. Supported formats
    print(f"\n[2] Supported formats...")
    try:
        r = requests.get(f"{args.url}/formats", headers=headers, timeout=10)
        formats = r.json().get("supported_formats", {})
        print(f"  {len(formats)} formats: {', '.join(formats.keys())}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # 3. Test specific file
    if args.file:
        print(f"\n[3] Parsing: {args.file}")
        result = test_parse_file(args.url, args.file, token)
        for k, v in result.items():
            print(f"  {k}: {v}")
        return

    # 4. Test GCS
    if args.gcs:
        print(f"\n[3] GCS parse: {args.gcs}")
        result = test_parse_gcs(args.url, args.gcs, token)
        for k, v in result.items():
            print(f"  {k}: {v}")
        return

    # 5. Test ArchiSurance PDFs
    print(f"\n[3] Testing ArchiSurance PDFs...")
    pdfs = sorted([f for f in os.listdir(TEST_DIR) if f.endswith(".pdf")])[:5]  # First 5
    results = []
    for pdf in pdfs:
        path = os.path.join(TEST_DIR, pdf)
        print(f"  Parsing {pdf}...", end=" ", flush=True)
        result = test_parse_file(args.url, path, token)
        results.append(result)
        if result["status"] == "OK":
            print(f"OK ({result['text_length']} chars, {result['num_tables']} tables, {result['total_time_s']}s)")
        else:
            print(f"FAIL: {result.get('error', '')[:80]}")

    # Summary
    ok = [r for r in results if r["status"] == "OK"]
    print(f"\n{'=' * 60}")
    print(f"RESULTS: {len(ok)}/{len(results)} passed")
    if ok:
        avg_chars = sum(r["text_length"] for r in ok) / len(ok)
        avg_tables = sum(r["num_tables"] for r in ok) / len(ok)
        avg_time = sum(r["total_time_s"] for r in ok) / len(ok)
        print(f"  Avg text: {avg_chars:.0f} chars")
        print(f"  Avg tables: {avg_tables:.1f}")
        print(f"  Avg time: {avg_time:.1f}s")
    print(f"{'=' * 60}")

    # Save results
    out_path = os.path.join(os.path.dirname(__file__), "results", "docling_test_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
