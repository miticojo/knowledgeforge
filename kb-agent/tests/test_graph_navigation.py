"""Unit tests for services.graph_navigation.

Mocks the Spanner database object — verifies that the dynamic SQL builder
respects layer/type/document filters, the hard cap, edge filtering, search
ranking and neighborhood expansion.
"""
from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services import graph_navigation  # noqa: E402


# ---------------------------------------------------------------------------
# Mock Spanner database
# ---------------------------------------------------------------------------

class FakeSnapshot:
    def __init__(self, db):
        self._db = db

    def execute_sql(self, sql, params=None, param_types=None):
        self._db.executed.append((sql, params or {}))
        # Match in order: counts first (SELECT COUNT), then rows
        for matcher, rows in self._db.responses:
            if matcher(sql, params or {}):
                return iter(rows)
        return iter([])


class FakeDB:
    def __init__(self):
        self.executed: list[tuple[str, dict]] = []
        self.responses: list[tuple[callable, list[tuple]]] = []

    def add_response(self, matcher, rows):
        self.responses.append((matcher, rows))

    @contextmanager
    def snapshot(self):
        yield FakeSnapshot(self)


@pytest.fixture(autouse=True)
def _patch_tenant_filter():
    """tenant_sql_filter_for hits Spanner information_schema in production —
    short-circuit it for unit tests so we don't need a real DB."""
    with patch.object(graph_navigation, "tenant_sql_filter_for", return_value="TRUE"):
        yield


# ---------------------------------------------------------------------------
# list_entities
# ---------------------------------------------------------------------------

def _count_match(sql, _p):
    return "COUNT(*)" in sql


def _row_match(sql, _p):
    return "COUNT(*)" not in sql and "SELECT" in sql


def test_list_entities_filters_by_entity_type():
    db = FakeDB()
    db.add_response(_count_match, [(2,)])
    db.add_response(_row_match, [
        ("a1", "Comp A", "desc", "doc1"),
        ("a2", "Comp B", None, None),
    ])
    out = graph_navigation.list_entities(db, entity_types=["ApplicationComponent"], tenant_id="t1")
    assert out["total"] >= 1
    assert all(n["type"] == "ApplicationComponent" for n in out["nodes"])
    # Verify that only the ApplicationComponent table was queried (no BusinessActor)
    assert any("ApplicationComponents" in s for s, _ in db.executed)
    assert not any("BusinessActors" in s for s, _ in db.executed)


def test_list_entities_filters_by_layer():
    db = FakeDB()
    db.add_response(_count_match, [(1,)])
    db.add_response(_row_match, [("g1", "Goal X", "", "")])
    out = graph_navigation.list_entities(db, layers=["Motivation"], tenant_id="t1")
    queried_tables = " ".join(s for s, _ in db.executed)
    assert "Goals" in queried_tables or "Stakeholders" in queried_tables
    assert "ApplicationComponents" not in queried_tables


def test_list_entities_hard_cap_5000():
    db = FakeDB()
    out = graph_navigation.list_entities(db, limit=999_999, tenant_id="t1")
    # No exception, and the hardcoded LIMIT in SQL should be <= 5000
    for sql, _ in db.executed:
        if "LIMIT" in sql and "COUNT(*)" not in sql:
            # Extract last LIMIT N
            tail = sql.rsplit("LIMIT", 1)[-1].strip()
            n = int(tail.split()[0])
            assert n <= 5000


def test_list_entities_document_filter_adds_clause():
    db = FakeDB()
    graph_navigation.list_entities(db, entity_types=["ApplicationComponent"], document_id="doc-7", tenant_id="t1")
    assert any("source_doc_id = @doc_id" in s for s, _ in db.executed)


def test_list_entities_offset_skips_rows():
    db = FakeDB()
    db.add_response(_count_match, [(3,)])
    db.add_response(_row_match, [
        ("a1", "A", "", ""),
        ("a2", "B", "", ""),
        ("a3", "C", "", ""),
    ])
    out = graph_navigation.list_entities(db, entity_types=["ApplicationComponent"], limit=2, offset=1, tenant_id="t1")
    names = [n["name"] for n in out["nodes"]]
    assert "A" not in names
    assert len(out["nodes"]) <= 2


# ---------------------------------------------------------------------------
# list_edges_for_nodes
# ---------------------------------------------------------------------------

def test_list_edges_only_keeps_internal_edges():
    db = FakeDB()
    db.add_response(lambda s, p: "Composition" in s, [
        ("n1", "n2", "EXTRACTED"),  # both in set → kept
        ("n1", "external", "EXTRACTED"),  # target outside → dropped
    ])
    edges = graph_navigation.list_edges_for_nodes(db, ["n1", "n2"], tenant_id="t1")
    assert len(edges) == 1
    assert edges[0]["source_id"] == "n1" and edges[0]["target_id"] == "n2"


def test_list_edges_confidence_filter():
    db = FakeDB()
    db.add_response(lambda s, p: "Composition" in s, [
        ("n1", "n2", "EXTRACTED"),
        ("n2", "n1", "INFERRED"),
    ])
    edges = graph_navigation.list_edges_for_nodes(db, ["n1", "n2"], confidences=["EXTRACTED"], tenant_id="t1")
    assert len(edges) == 1
    assert edges[0]["confidence"] == "EXTRACTED"


def test_list_edges_empty_nodes_returns_empty():
    db = FakeDB()
    assert graph_navigation.list_edges_for_nodes(db, [], tenant_id="t1") == []


# ---------------------------------------------------------------------------
# search_entities
# ---------------------------------------------------------------------------

def test_search_entities_name_match_outranks_desc_match():
    db = FakeDB()
    # Match every SELECT for entity tables
    db.add_response(_row_match, [
        ("e1", "PaymentService", "the payment service component"),
        ("e2", "Other", "PaymentService is mentioned here"),
    ])
    out = graph_navigation.search_entities(db, "payment", entity_types=["ApplicationComponent"], tenant_id="t1")
    # Both rows present; name-match should rank first
    assert out
    assert out[0]["name"] == "PaymentService"
    assert out[0]["score"] >= out[-1]["score"]


def test_search_entities_empty_query_returns_empty():
    db = FakeDB()
    assert graph_navigation.search_entities(db, "", tenant_id="t1") == []


# ---------------------------------------------------------------------------
# get_neighborhood
# ---------------------------------------------------------------------------

def test_get_neighborhood_one_hop_returns_center_plus_neighbors():
    db = FakeDB()
    # Edge query: return one neighbor on Composition for the center
    def edge_match(sql, _p):
        return "Composition" in sql and "source_id IN" in sql
    db.add_response(edge_match, [
        ("center", "ApplicationComponent", "neighbor", "ApplicationComponent", "EXTRACTED"),
    ])
    # Name lookup
    db.add_response(lambda s, p: "ApplicationComponents" in s and "IN (" in s, [
        ("center", "Center App"),
        ("neighbor", "Neighbor App"),
    ])
    out = graph_navigation.get_neighborhood(db, "center", hops=1, tenant_id="t1")
    ids = {n["entity_id"] for n in out["nodes"]}
    assert "center" in ids
    assert out["center_id"] == "center"


def test_get_neighborhood_caps_hops():
    db = FakeDB()
    out = graph_navigation.get_neighborhood(db, "x", hops=99, tenant_id="t1")
    # Should not raise; just returns center with no edges (no responses set)
    assert out["center_id"] == "x"
