"""Regression tests: graph_writer must NOT swallow Spanner write failures.

Background
----------
A previous version of `_run_git_ingest` would mark the job `complete` even
when every per-file `write_graph_to_spanner` call had failed. The downstream
indicator was that `summary["errors"]` was populated but the job status was
still `"complete"`. These tests pin the contract:

  1. `write_graph_to_spanner` re-raises Spanner errors (does not silently
     return success with empty counts).
  2. `GitIngester.ingest()` collects per-file writer failures into
     `summary["errors"]`.
  3. `_run_git_ingest` flips the job to `status="failed"` whenever
     `summary["errors"]` is non-empty.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.git_ingester import GitIngester


SAMPLE_PY = '''\
"""Sample module."""
class Thing:
    def do(self):
        return 1
'''


# ---------------------------------------------------------------------------
# graph_writer: re-raise on Spanner failure
# ---------------------------------------------------------------------------
def test_write_graph_reraises_on_batch_failure(monkeypatch):
    """Spanner errors during batch_write must propagate, not be swallowed."""
    from services import graph_writer

    # Stub out side-effects: we only want to verify exception propagation.
    monkeypatch.setattr(
        graph_writer, "compute_entity_embeddings",
        lambda items: [[0.0] * 768 for _ in items],
    )

    class _FakeReconciler:
        stats = {"new": 0, "exact": 0, "vector": 0}

        def __init__(self, *a, **kw):
            pass

        def reconcile(self, etype, name, emb):
            return ("id-" + name, True)

    monkeypatch.setattr(graph_writer, "EntityReconciler", _FakeReconciler)
    monkeypatch.setattr(graph_writer, "get_database", lambda: MagicMock())

    def _boom(_mutations):
        raise RuntimeError("Spanner: column doc_id exceeds limit 36")

    monkeypatch.setattr(graph_writer, "batch_write", _boom)

    graph_json = {
        "extracted_nodes": ["ApplicationComponent:Thing"],
        "extracted_edges": [],
    }

    with pytest.raises(RuntimeError, match="exceeds limit"):
        graph_writer.write_graph_to_spanner(
            graph_json,
            doc_id="git:https://example.com/x.git@deadbeef:mod.py",
            doc_title="mod.py",
            doc_summary="",
            doc_embedding=[0.0] * 768,
        )


# ---------------------------------------------------------------------------
# git_ingester: writer failure lands in summary["errors"]
# ---------------------------------------------------------------------------
def _prepare_clone(tmp_path: Path, files: dict[str, str]) -> Path:
    clone = tmp_path / "repo"
    clone.mkdir()
    for rel, content in files.items():
        target = clone / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return clone


def test_git_ingest_records_writer_failure_in_errors(tmp_path):
    clone = _prepare_clone(tmp_path, {"mod.py": SAMPLE_PY})

    def boom_writer(*_a, **_kw):
        raise RuntimeError("Spanner: doc_id size 111 exceeds 36")

    ig = GitIngester(
        repo_url="https://example.com/x.git",
        workdir=tmp_path,
        writer=boom_writer,
        embedder=MagicMock(return_value=[[0.0] * 768]),
    )
    ig._clone_path = clone
    ig._commit_sha = "deadbeef"

    summary = ig.ingest()

    assert summary["files_processed"] == 0
    assert len(summary["errors"]) == 1
    assert "writer error" in summary["errors"][0]
    assert "exceeds 36" in summary["errors"][0]


# ---------------------------------------------------------------------------
# main._run_git_ingest: status must be "failed" when summary has errors
# ---------------------------------------------------------------------------
def test_run_git_ingest_marks_failed_when_summary_has_errors(monkeypatch):
    import main as main_mod

    job_id = "test-job-errors"
    main_mod._GIT_INGEST_JOBS[job_id] = {"status": "queued"}

    fake_summary = {
        "repo_url": "https://example.com/x.git",
        "commit_sha": "deadbeef",
        "files_processed": 0,
        "files_skipped": 0,
        "entities_total": 0,
        "edges_total": 0,
        "errors": [
            "a.py: writer error: Spanner doc_id too long",
            "b.py: writer error: Spanner doc_id too long",
            "c.py: writer error: Spanner doc_id too long",
            "d.py: writer error: Spanner doc_id too long",
        ],
    }

    class _FakeIngester:
        def __init__(self, *a, **kw):
            pass

        def ingest(self):
            return fake_summary

    # GitIngester is imported *inside* _run_git_ingest, so patch the source.
    monkeypatch.setattr(
        "services.git_ingester.GitIngester", _FakeIngester
    )
    monkeypatch.setattr(
        "services.tenant_context.set_tenant", lambda *a, **kw: None
    )

    body = MagicMock()
    body.repo_url = "https://example.com/x.git"
    body.ref = None
    body.include = None
    body.exclude = None

    main_mod._run_git_ingest(job_id, body, tenant_id="__shared__")

    job = main_mod._GIT_INGEST_JOBS[job_id]
    assert job["status"] == "failed"
    assert job["error_count"] == 4
    assert len(job["error_samples"]) == 3  # first 3 only
    assert job["summary"] is fake_summary


def test_run_git_ingest_marks_complete_when_no_errors(monkeypatch):
    import main as main_mod

    job_id = "test-job-ok"
    main_mod._GIT_INGEST_JOBS[job_id] = {"status": "queued"}

    fake_summary = {
        "repo_url": "https://example.com/x.git",
        "commit_sha": "deadbeef",
        "files_processed": 3,
        "files_skipped": 0,
        "entities_total": 12,
        "edges_total": 7,
        "errors": [],
    }

    class _FakeIngester:
        def __init__(self, *a, **kw):
            pass

        def ingest(self):
            return fake_summary

    monkeypatch.setattr("services.git_ingester.GitIngester", _FakeIngester)
    monkeypatch.setattr("services.tenant_context.set_tenant", lambda *a, **kw: None)

    body = MagicMock()
    body.repo_url = "https://example.com/x.git"
    body.ref = None
    body.include = None
    body.exclude = None

    main_mod._run_git_ingest(job_id, body, tenant_id="__shared__")

    job = main_mod._GIT_INGEST_JOBS[job_id]
    assert job["status"] == "complete"
    assert job["summary"] is fake_summary
    assert "error_count" not in job
