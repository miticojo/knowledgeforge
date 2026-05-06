"""Unit tests for the Java AST parser."""
import re

from services.ast_parsers.java import parse
from services.ast_to_archimate import to_graph

_NODE_RE = re.compile(r"^([A-Za-z]+):(.+)$")
_EDGE_RE = re.compile(
    r"^([A-Za-z]+):(.+?)->([A-Za-z]+)(?:\[([^\]]*)\])?->([A-Za-z]+):(.+)$"
)

SAMPLE = """\
package com.example.app;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import javax.persistence.Entity;

@Entity
public class User {
  private Long id;
  public String getName() { return "x"; }
}

@RestController
public class UserController {
  @GetMapping("/users/{id}")
  public User get() { return null; }

  @PostMapping("/users")
  public User create() { return null; }
}
"""


def test_parse_package_and_imports():
    pf = parse(SAMPLE, "User.java")
    assert pf.module_name.startswith("com.example.app.")
    assert "javax.persistence.Entity" in pf.imports
    assert "org.springframework.web.bind.annotation.RestController" in pf.imports


def test_parse_classes_and_methods():
    pf = parse(SAMPLE, "User.java")
    names = {c.name for c in pf.classes}
    assert names == {"User", "UserController"}
    user = next(c for c in pf.classes if c.name == "User")
    assert "__entity__" in user.bases
    ctrl = next(c for c in pf.classes if c.name == "UserController")
    m_names = {m.name for m in ctrl.methods}
    assert m_names == {"get", "create"}


def test_parse_routes():
    pf = parse(SAMPLE, "User.java")
    routes = {(r.method, r.path) for r in pf.routes}
    assert ("GET", "/users/{id}") in routes
    assert ("POST", "/users") in routes


def test_to_graph_entity_is_dataobject():
    pf = parse(SAMPLE, "User.java")
    g = to_graph(pf, doc_id="x")
    nodes = set(g["extracted_nodes"])
    user_qn = next(c.qualified_name for c in pf.classes if c.name == "User")
    assert f"DataObject:{user_qn}" in nodes
    ctrl_qn = next(c.qualified_name for c in pf.classes if c.name == "UserController")
    assert f"ApplicationComponent:{ctrl_qn}" in nodes


def test_to_graph_writer_compatible():
    pf = parse(SAMPLE, "User.java")
    g = to_graph(pf, doc_id="x")
    for n in g["extracted_nodes"]:
        assert _NODE_RE.match(n), f"node failed: {n!r}"
    for e in g["extracted_edges"]:
        assert _EDGE_RE.match(e), f"edge failed: {e!r}"
