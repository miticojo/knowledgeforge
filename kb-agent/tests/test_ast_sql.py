"""Unit tests for the SQL AST parser."""
import re

from services.ast_parsers.sql import parse
from services.ast_to_archimate import to_graph

_NODE_RE = re.compile(r"^([A-Za-z]+):(.+)$")
_EDGE_RE = re.compile(
    r"^([A-Za-z]+):(.+?)->([A-Za-z]+)(?:\[([^\]]*)\])?->([A-Za-z]+):(.+)$"
)

SAMPLE = """\
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL
);

CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE VIEW active_orders AS
  SELECT o.id, u.email FROM orders o JOIN users u ON o.user_id = u.id;
"""


def test_parse_tables_and_view():
    pf = parse(SAMPLE, "db/schema.sql")
    names = {c.name for c in pf.classes}
    assert {"users", "orders", "active_orders"}.issubset(names)
    assert pf.functions == []
    assert pf.imports == []
    assert pf.routes == []


def test_parse_marks_entities():
    pf = parse(SAMPLE, "db/schema.sql")
    for c in pf.classes:
        assert "__entity__" in c.bases


def test_parse_fk_target():
    pf = parse(SAMPLE, "db/schema.sql")
    orders = next(c for c in pf.classes if c.name == "orders")
    assert any(b == "__fk__:users" for b in orders.bases)


def test_parse_view_refs():
    pf = parse(SAMPLE, "db/schema.sql")
    view = next(c for c in pf.classes if c.name == "active_orders")
    refs = {b.split(":", 1)[1] for b in view.bases if b.startswith("__view_ref__:")}
    assert "orders" in refs
    assert "users" in refs


def test_to_graph_emits_dataobjects_and_access():
    pf = parse(SAMPLE, "db/schema.sql")
    g = to_graph(pf, doc_id="x")
    nodes = set(g["extracted_nodes"])
    assert "DataObject:schema.users" in nodes
    assert "DataObject:schema.orders" in nodes
    assert "DataObject:schema.active_orders" in nodes
    edges = g["extracted_edges"]
    # Access edge orders -> users from FK
    assert any(
        e.startswith("DataObject:schema.orders->Access[") and e.endswith("DataObject:schema.users")
        for e in edges
    )
    # Realization edge view -> table
    assert any(
        e.startswith("DataObject:schema.active_orders->Realization[")
        and e.endswith("DataObject:schema.orders")
        for e in edges
    )


def test_writer_compatible():
    pf = parse(SAMPLE, "db/schema.sql")
    g = to_graph(pf, doc_id="x")
    for n in g["extracted_nodes"]:
        assert _NODE_RE.match(n), f"node failed: {n!r}"
    for e in g["extracted_edges"]:
        assert _EDGE_RE.match(e), f"edge failed: {e!r}"
