"""End-to-end tests for POST /ingest/document and the unified /ingest/* SSE.

Mirrors the assertions made for /ingest/git: route + parse_start + parse_end +
write_start + write_end + complete arrive in order, and the per-file artifact
exposes entities/edges in the same shape as the git path.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force the entity extractor to no-op so tests don't require Gemini.
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GOOGLE_API_KEY", None)


@pytest.fixture(autouse=True)
def _reset_state():
    from services import event_bus, raw_artifact_store
    from services import artifact_store as _a
    event_bus.reset()
    _a.store._reset_for_tests()
    raw_artifact_store._reset_for_tests()
    import main
    main._DOC_INGEST_JOBS.clear()
    main._GIT_INGEST_JOBS.clear()
    yield
    event_bus.reset()
    _a.store._reset_for_tests()
    raw_artifact_store._reset_for_tests()
    main._DOC_INGEST_JOBS.clear()
    main._GIT_INGEST_JOBS.clear()


def _post_text_doc(client, text: str, file_name: str = "demo.txt") -> str:
    r = client.post(
        "/ingest/document",
        json={"text": text, "fileName": file_name, "images": []},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    return body["job_id"]


def _wait_for_terminal(client, job_id: str, timeout: float = 5.0) -> dict:
    """Poll /ingest/document/{job_id} until status is terminal."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/ingest/document/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("status") in ("complete", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_ingest_document_emits_pipeline_events_in_order():
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    text = "Title\n\nThis demo document describes ApplicationComponent Foo."
    job_id = _post_text_doc(client, text, file_name="demo.txt")
    summary = _wait_for_terminal(client, job_id)
    assert summary["status"] == "complete"

    # SSE: subscribe AFTER the job completed — buffered events replay in order.
    with client.stream("GET", f"/ingest/{job_id}/events") as resp:
        assert resp.status_code == 200
        events: list[tuple[str, dict]] = []
        current_event: str | None = None
        for line in resp.iter_lines():
            if line is None:
                continue
            # httpx may yield str or bytes depending on version
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            if line.startswith("event: "):
                current_event = line[len("event: "):].strip()
            elif line.startswith("data: ") and current_event is not None:
                payload = json.loads(line[len("data: "):])
                events.append((current_event, payload))
                if current_event in ("complete", "failed"):
                    break
                current_event = None

    types = [et for et, _ in events]
    # Required ordering: route -> parse_start -> parse_end -> write_start -> write_end -> complete
    for required in ("route", "parse_start", "parse_end", "write_start", "write_end", "complete"):
        assert required in types, f"missing {required} in {types}"
    assert types.index("route") < types.index("parse_start") < types.index("parse_end")
    assert types.index("parse_end") < types.index("write_start") < types.index("write_end")
    assert types.index("write_end") < types.index("complete")

    # Shape parity with git: parse_end carries entities[] and edges[] arrays.
    parse_end = next(d for et, d in events if et == "parse_end")
    assert isinstance(parse_end.get("entities"), list)
    assert isinstance(parse_end.get("edges"), list)
    assert "file" in parse_end and "parser" in parse_end


def test_ingest_document_artifact_via_unified_file_endpoint():
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    job_id = _post_text_doc(client, "hello world body", file_name="note.md")
    _wait_for_terminal(client, job_id)

    r = client.get(f"/ingest/{job_id}/file", params={"path": "note.md"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["file"] == "note.md"
    assert payload["language"] == "markdown"
    assert "hello world body" in payload["source"]
    assert "parsed" in payload and "sections" in payload["parsed"]
    assert isinstance(payload["entities"], list)
    assert isinstance(payload["edges"], list)


def test_ingest_document_legacy_git_alias_still_works_for_git_jobs():
    """The /ingest/git/{job_id}/* endpoints must keep working untouched."""
    from fastapi.testclient import TestClient
    from services import event_bus
    from services.artifact_store import store as _artifact_store
    import main

    # Fabricate a "git" job entry + push artifacts so we don't need a real clone.
    job_id = "git-test-123"
    main._GIT_INGEST_JOBS[job_id] = {"status": "complete"}
    _artifact_store.put(job_id, "src/x.py", {
        "file": "src/x.py", "parser": "python-ast", "language": "python",
        "source": "x = 1\n", "parsed": {}, "entities": [], "edges": [],
    })
    event_bus.publish(job_id, "complete", {"summary": {"files_processed": 1}})
    event_bus.close(job_id)

    client = TestClient(main.app)
    # Legacy alias
    r = client.get(f"/ingest/git/{job_id}/file", params={"path": "src/x.py"})
    assert r.status_code == 200
    assert r.json()["file"] == "src/x.py"
    # New unified path
    r2 = client.get(f"/ingest/{job_id}/file", params={"path": "src/x.py"})
    assert r2.status_code == 200
    assert r2.json()["file"] == "src/x.py"


def test_ingest_document_pdf_raw_endpoint_returns_bytes():
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    pdf_bytes = b"%PDF-1.4\n%fake test pdf\n"
    r = client.post(
        "/ingest/document",
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    _wait_for_terminal(client, job_id)

    raw = client.get(f"/ingest/{job_id}/file/raw", params={"path": "paper.pdf"})
    assert raw.status_code == 200, raw.text
    assert raw.headers["content-type"].startswith("application/pdf")
    assert raw.content == pdf_bytes


def test_ingest_document_unknown_job_returns_404():
    from fastapi.testclient import TestClient
    import main

    client = TestClient(main.app)
    r = client.get("/ingest/does-not-exist/file", params={"path": "x"})
    assert r.status_code == 404
    r2 = client.get("/ingest/does-not-exist/file/raw", params={"path": "x"})
    assert r2.status_code == 404
