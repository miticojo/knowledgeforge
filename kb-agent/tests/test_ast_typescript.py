"""Unit tests for the TypeScript AST parser."""
import re

from services.ast_parsers.typescript import parse
from services.ast_to_archimate import to_graph

_NODE_RE = re.compile(r"^([A-Za-z]+):(.+)$")
_EDGE_RE = re.compile(
    r"^([A-Za-z]+):(.+?)->([A-Za-z]+)(?:\[([^\]]*)\])?->([A-Za-z]+):(.+)$"
)


SAMPLE = """\
import { Router } from "express";
import * as utils from "./utils";
const log = require("loglib");

export class UserService {
  greet(name: string): string {
    return "hi " + name;
  }
  _internal() {}
}

const app = Router();
app.get('/users/:id', (req, res) => { res.send(); });
app.post('/users', handler);

export function publicFn() {}
"""


def test_parse_imports():
    pf = parse(SAMPLE, "src/users/service.ts")
    assert "express" in pf.imports
    assert "./utils" in pf.imports
    assert "loglib" in pf.imports


def test_parse_class_and_methods():
    pf = parse(SAMPLE, "src/users/service.ts")
    names = [c.name for c in pf.classes]
    assert "UserService" in names
    cls = next(c for c in pf.classes if c.name == "UserService")
    method_names = {m.name for m in cls.methods}
    assert "greet" in method_names
    greet = next(m for m in cls.methods if m.name == "greet")
    assert greet.is_public
    assert greet.qualified_name == "users.service.UserService.greet"
    internal = next(m for m in cls.methods if m.name == "_internal")
    assert internal.is_public is False


def test_parse_module_function():
    pf = parse(SAMPLE, "src/users/service.ts")
    names = {f.name for f in pf.functions}
    assert "publicFn" in names


def test_parse_express_routes():
    pf = parse(SAMPLE, "src/users/service.ts")
    methods_paths = {(r.method, r.path) for r in pf.routes}
    assert ("GET", "/users/:id") in methods_paths
    assert ("POST", "/users") in methods_paths


def test_parse_nestjs_decorator_route():
    src = """
class CatsController {
  @Get('/cats')
  findAll() {}
}
"""
    pf = parse(src, "src/cats.ts")
    assert any(r.method == "GET" and r.path == "/cats" for r in pf.routes)


def test_parse_typeorm_entity_marked():
    src = """
@Entity()
class User {
  id: number;
}
"""
    pf = parse(src, "src/user.ts")
    cls = pf.classes[0]
    assert "__entity__" in cls.bases


def test_to_graph_writer_compatible():
    pf = parse(SAMPLE, "src/users/service.ts")
    g = to_graph(pf, doc_id="git:test:service.ts")
    for n in g["extracted_nodes"]:
        assert _NODE_RE.match(n), f"node failed: {n!r}"
    for e in g["extracted_edges"]:
        assert _EDGE_RE.match(e), f"edge failed: {e!r}"


def test_to_graph_entity_becomes_dataobject():
    src = "@Entity()\nclass User { id: number; }\n"
    pf = parse(src, "src/user.ts")
    g = to_graph(pf, doc_id="x")
    assert "DataObject:user.User" in g["extracted_nodes"]
