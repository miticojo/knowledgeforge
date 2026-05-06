"""Unit tests for services.artifact_store."""
from __future__ import annotations

import time

import pytest

from services import artifact_store as mod


@pytest.fixture(autouse=True)
def _reset_store():
    mod.store._reset_for_tests()
    yield
    mod.store._reset_for_tests()


def test_put_and_get_roundtrip():
    mod.store.put("job1", "a/b.py", {
        "file": "a/b.py",
        "parser": "python-ast",
        "language": "python",
        "source": "print(1)\n",
        "parsed": {"module_name": "b"},
        "entities": [{"id": "x", "type": "ApplicationComponent", "name": "b"}],
        "edges": [],
    })
    out = mod.store.get("job1", "a/b.py")
    assert out is not None
    assert out["file"] == "a/b.py"
    assert out["source"] == "print(1)\n"
    assert out["entities"][0]["id"] == "x"


def test_get_unknown_returns_none():
    assert mod.store.get("nope", "x.py") is None
    mod.store.put("job1", "a.py", {"source": "x"})
    assert mod.store.get("job1", "missing.py") is None


def test_source_truncated_past_max():
    big = "a" * (mod.MAX_SOURCE_BYTES + 1024)
    mod.store.put("job1", "huge.py", {"source": big})
    out = mod.store.get("job1", "huge.py")
    assert out is not None
    assert out["source"].endswith("...truncated...")
    # Body before suffix is roughly the byte budget.
    assert len(out["source"]) <= mod.MAX_SOURCE_BYTES + len("\n...truncated...") + 1


def test_eviction_past_max_files(monkeypatch):
    monkeypatch.setattr(mod, "MAX_FILES_PER_JOB", 3)
    for i in range(5):
        mod.store.put("job1", f"f{i}.py", {"source": "x"})
    files = mod.store.list_files("job1")
    assert len(files) == 3
    # First three should be the ones retained (later puts dropped).
    assert files == ["f0.py", "f1.py", "f2.py"]


def test_overwrite_existing_file_does_not_count_as_new():
    # Even with cap = 2, overwriting an existing key must succeed.
    import services.artifact_store as m
    m.store._reset_for_tests()
    orig_max = m.MAX_FILES_PER_JOB
    try:
        m.MAX_FILES_PER_JOB = 2
        m.store.put("j", "a.py", {"source": "v1"})
        m.store.put("j", "b.py", {"source": "v1"})
        m.store.put("j", "a.py", {"source": "v2"})  # overwrite, not new
        assert m.store.get("j", "a.py")["source"] == "v2"
        assert m.store.get("j", "b.py")["source"] == "v1"
    finally:
        m.MAX_FILES_PER_JOB = orig_max


def test_gc_after_ttl(monkeypatch):
    monkeypatch.setattr(mod, "TTL_SECONDS", 0.05)
    mod.store.put("job1", "a.py", {"source": "x"})
    mod.store.mark_closed("job1")
    assert mod.store.get("job1", "a.py") is not None
    time.sleep(0.1)
    # Trigger GC via any op.
    mod.store.put("job2", "z.py", {"source": "x"})
    assert mod.store.get("job1", "a.py") is None


def test_upload_pdf_artifact_shape_roundtrips():
    """Upload-style entries (PDF/DOCX/MD/TXT) share the git artifact schema.

    Verifies the inspector-payload contract for the new POST /ingest/document
    path: same keys, same nested shapes, just a different `language`.
    """
    mod.store.put("upload-job", "paper.pdf", {
        "file": "paper.pdf",
        "parser": "liteparse",
        "language": "pdf",
        "source": "Extracted text from the PDF, page 1...",
        "parsed": {"title": "Paper", "sections": ["Intro", "Method"], "image_count": 0},
        "entities": [{
            "id": "e-1", "type": "ApplicationComponent",
            "name": "Foo", "layer": "Application", "confidence": "EXTRACTED",
        }],
        "edges": [{
            "source": "e-1", "target": "e-2",
            "rel": "Composition", "confidence": "EXTRACTED",
        }],
    })
    out = mod.store.get("upload-job", "paper.pdf")
    assert out is not None
    assert out["language"] == "pdf"
    assert out["parsed"]["sections"] == ["Intro", "Method"]
    assert out["entities"][0]["type"] == "ApplicationComponent"
    assert out["edges"][0]["rel"] == "Composition"


def test_upload_text_artifact_truncates_large_source_like_git():
    """A long extracted-text body from liteparse must be truncated identically."""
    big = "x" * (mod.MAX_SOURCE_BYTES + 4096)
    mod.store.put("upload-job", "big.md", {
        "file": "big.md", "parser": "text", "language": "markdown",
        "source": big, "parsed": {"title": "big", "sections": [], "image_count": 0},
        "entities": [], "edges": [],
    })
    out = mod.store.get("upload-job", "big.md")
    assert out is not None
    assert out["source"].endswith("...truncated...")


def test_raw_artifact_store_roundtrip_and_close():
    """Sanity-check the sibling raw-bytes store used for PDF originals."""
    from services import raw_artifact_store
    raw_artifact_store._reset_for_tests()
    fp = raw_artifact_store.put("rj1", "paper.pdf", b"%PDF-1.4\nhello\n")
    assert fp.exists()
    got = raw_artifact_store.get_path("rj1", "paper.pdf")
    assert got is not None
    assert got.read_bytes().startswith(b"%PDF")
    raw_artifact_store.mark_closed("rj1")  # idempotent / no-throw
    raw_artifact_store._reset_for_tests()


def test_mark_closed_idempotent_and_unaffects_open_jobs():
    mod.store.put("open_job", "a.py", {"source": "x"})
    mod.store.put("closed_job", "a.py", {"source": "x"})
    mod.store.mark_closed("closed_job")
    mod.store.mark_closed("closed_job")  # idempotent
    assert mod.store.get("open_job", "a.py") is not None
    assert mod.store.get("closed_job", "a.py") is not None
