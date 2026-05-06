"""Unit tests for the Go AST parser."""
import re

from services.ast_parsers.go import parse
from services.ast_to_archimate import to_graph

_NODE_RE = re.compile(r"^([A-Za-z]+):(.+)$")
_EDGE_RE = re.compile(
    r"^([A-Za-z]+):(.+?)->([A-Za-z]+)(?:\[([^\]]*)\])?->([A-Za-z]+):(.+)$"
)

SAMPLE = """\
package server

import (
  "net/http"
  "fmt"
)

type User struct {
  ID int
  Name string
}

func (u *User) Greet() string { return "hi" }
func (u *User) internalThing() {}

func PublicFunc() int { return 1 }
func privateFunc() {}

func main() {
  http.HandleFunc("/users", handleUsers)
  http.HandleFunc("/items", handleItems)
}
"""


def test_parse_package_and_module_name():
    pf = parse(SAMPLE, "cmd/server/main.go")
    assert pf.module_name == "server.main"


def test_parse_imports():
    pf = parse(SAMPLE, "cmd/server/main.go")
    assert "net/http" in pf.imports
    assert "fmt" in pf.imports


def test_parse_struct_and_methods():
    pf = parse(SAMPLE, "cmd/server/main.go")
    names = {c.name for c in pf.classes}
    assert "User" in names
    user = next(c for c in pf.classes if c.name == "User")
    method_names = {m.name for m in user.methods}
    # Only exported methods (UpperCamel) should be present.
    assert "Greet" in method_names
    assert "internalThing" not in method_names


def test_parse_exported_funcs_only():
    pf = parse(SAMPLE, "cmd/server/main.go")
    fnames = {f.name for f in pf.functions}
    assert "PublicFunc" in fnames
    assert "privateFunc" not in fnames


def test_parse_handlefunc_routes():
    pf = parse(SAMPLE, "cmd/server/main.go")
    paths = {r.path for r in pf.routes}
    assert "/users" in paths
    assert "/items" in paths


def test_to_graph_writer_compatible():
    pf = parse(SAMPLE, "cmd/server/main.go")
    g = to_graph(pf, doc_id="x")
    for n in g["extracted_nodes"]:
        assert _NODE_RE.match(n), f"node failed: {n!r}"
    for e in g["extracted_edges"]:
        assert _EDGE_RE.match(e), f"edge failed: {e!r}"
    assert "ApplicationComponent:server.main.User" in g["extracted_nodes"]
    assert "ApplicationService:server.main.PublicFunc" in g["extracted_nodes"]
