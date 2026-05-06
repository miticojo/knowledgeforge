"""Tests for the X-Entity-Scope plumbing.

Covers:
  - tenant_context.set_entity_scope / get_entity_scope round-trip
  - main.TenantMiddleware reads X-Entity-Scope and sets the contextvar
  - tool_query_spanner_graph emits the ChunkMentions JOIN when scope is set,
    and omits it when scope is empty.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import tenant_context  # noqa: E402


def test_set_get_entity_scope_roundtrip():
    tenant_context.reset_context()
    assert tenant_context.get_entity_scope() == []
    tenant_context.set_entity_scope(["a", "b", "c"])
    assert tenant_context.get_entity_scope() == ["a", "b", "c"]
    tenant_context.set_entity_scope([])
    assert tenant_context.get_entity_scope() == []


def test_set_entity_scope_strips_blanks():
    tenant_context.reset_context()
    tenant_context.set_entity_scope(["  e1 ", "", "e2"])
    assert tenant_context.get_entity_scope() == ["e1", "e2"]


def test_middleware_reads_header(monkeypatch):
    """TenantMiddleware should pull X-Entity-Scope into tenant_context."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    tenant_context.reset_context()

    app = FastAPI()
    # Re-use the real middleware
    import main as kf_main
    app.add_middleware(kf_main.TenantMiddleware)

    captured: dict = {}

    @app.get("/probe")
    def probe():
        captured["scope"] = tenant_context.get_entity_scope()
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/probe", headers={"X-Entity-Scope": "id-1, id-2,id-3"})
    assert captured["scope"] == ["id-1", "id-2", "id-3"]


def test_middleware_no_header_means_empty_scope():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    tenant_context.reset_context()
    import main as kf_main

    app = FastAPI()
    app.add_middleware(kf_main.TenantMiddleware)

    captured: dict = {}

    @app.get("/probe2")
    def probe2():
        captured["scope"] = tenant_context.get_entity_scope()
        return {"ok": True}

    with TestClient(app) as client:
        client.get("/probe2")
    assert captured["scope"] == []


# ---------------------------------------------------------------------------
# tool_query_spanner_graph: SQL contains the JOIN when scope present
# ---------------------------------------------------------------------------

class _RecordingSnapshot:
    def __init__(self, sink):
        self.sink = sink

    def execute_sql(self, sql, params=None, param_types=None):
        self.sink.append((sql, params or {}))
        return iter([])


class _RecordingDB:
    def __init__(self):
        self.queries: list[tuple[str, dict]] = []

    def snapshot(self):
        # context manager
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield _RecordingSnapshot(self.queries)
        return _cm()


def _run_search_capture(entity_scope: list[str] | None) -> list[str]:
    """Invoke tool_query_spanner_graph with all heavy deps mocked, return SQL list."""
    from agents import search as search_mod

    db = _RecordingDB()

    # Patch get_database to our recording stub
    fake_emb_client = MagicMock()
    emb_response = MagicMock()
    emb_response.embeddings = [MagicMock(values=[0.1] * 8)]
    fake_emb_client.models.embed_content.return_value = emb_response

    fake_genai_client = MagicMock()
    # Force the JSON expansion to fail-soft so we use only the original query
    fake_genai_client.models.generate_content.side_effect = Exception("skip expansion")

    tool_context = MagicMock()
    tool_context.state = {}

    with patch("services.spanner_client.get_database", return_value=db), \
         patch("services.document_chunker._get_embedding_client", return_value=fake_emb_client), \
         patch("services.qa_cache.search_qa_cache", return_value=None), \
         patch("google.genai.Client", return_value=fake_genai_client):
        try:
            search_mod.tool_query_spanner_graph(
                "find payment service",
                tool_context,
                entity_scope=entity_scope,
            )
        except Exception:
            # Reranker / other downstream steps may fail in unit-mode — we only
            # care about the SQL emitted up to that point.
            pass
    return [s for s, _ in db.queries]


def test_search_emits_chunkmentions_join_when_scope_present():
    tenant_context.reset_context()
    sqls = _run_search_capture(entity_scope=["e1", "e2"])
    joined = "\n---\n".join(sqls)
    assert "ChunkMentions" in joined
    assert "cm.entity_id IN" in joined


def test_search_no_join_when_scope_empty():
    tenant_context.reset_context()
    sqls = _run_search_capture(entity_scope=[])
    joined = "\n---\n".join(sqls)
    # The seed keyword/vector queries should not contain the EXISTS join
    # against ChunkMentions when no scope is active. (Other graph queries
    # may still reference ChunkMentions in the Q3 expansion path, which is
    # not exercised here because we early-fail expansion.)
    assert "EXISTS (SELECT 1 FROM ChunkMentions" not in joined
