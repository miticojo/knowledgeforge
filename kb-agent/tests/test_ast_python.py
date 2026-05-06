"""Unit tests for services.ast_parsers.python and services.ast_to_archimate."""
import re

import pytest

from services.ast_parsers.python import parse
from services.ast_to_archimate import to_graph

# Mirror the regexes used by graph_writer to verify our output shape is writable.
_NODE_RE = re.compile(r"^([A-Za-z]+):(.+)$")
_EDGE_RE = re.compile(
    r"^([A-Za-z]+):(.+?)->"
    r"([A-Za-z]+)"
    r"(?:\[([^\]]*)\])?"
    r"->"
    r"([A-Za-z]+):(.+)$"
)


SAMPLE = '''\
"""Sample module for AST tests."""
from fastapi import APIRouter
from services.helpers import do_thing
import os

router = APIRouter()

CONSTANT_X = 42
OTHER_CONST = "y"


class UserService:
    """Manages users."""

    def create_user(self, name: str) -> dict:
        """Create a user."""
        return {"name": name}

    def _internal(self):
        pass


@router.get("/users/{uid}")
def get_user(uid: str):
    """Fetch a user."""
    return UserService().create_user(uid)
'''


# ---------------------------------------------------------------- parse() tests

def test_parse_module_metadata():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    assert pf.module_name == "mypkg.users"
    assert pf.module_doc == "Sample module for AST tests."


def test_parse_imports():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    assert "fastapi" in pf.imports
    assert "services.helpers" in pf.imports
    assert "os" in pf.imports


def test_parse_constants():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    assert "CONSTANT_X" in pf.constants
    assert "OTHER_CONST" in pf.constants


def test_parse_class_and_methods():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    assert len(pf.classes) == 1
    cls = pf.classes[0]
    assert cls.name == "UserService"
    assert cls.qualified_name == "mypkg.users.UserService"
    assert cls.docstring == "Manages users."
    method_names = {m.name for m in cls.methods}
    assert method_names == {"create_user", "_internal"}
    create = next(m for m in cls.methods if m.name == "create_user")
    assert create.is_public is True
    assert create.is_method is True
    assert create.owner_class == "UserService"
    assert create.qualified_name == "mypkg.users.UserService.create_user"
    assert "name: str" in create.signature
    internal = next(m for m in cls.methods if m.name == "_internal")
    assert internal.is_public is False


def test_parse_module_level_function_and_route():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    assert len(pf.functions) == 1
    fn = pf.functions[0]
    assert fn.name == "get_user"
    assert fn.qualified_name == "mypkg.users.get_user"
    assert fn.is_public is True
    assert any(d.startswith("@router.get") for d in fn.decorators)

    assert len(pf.routes) == 1
    route = pf.routes[0]
    assert route.method == "GET"
    assert route.path == "/users/{uid}"
    assert route.handler_name == "mypkg.users.get_user"


# ----------------------------------------------------------- to_graph() tests

def test_to_graph_nodes_present():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    g = to_graph(pf, doc_id="git:test:users.py")
    nodes = set(g["extracted_nodes"])

    assert "ApplicationComponent:mypkg.users" in nodes
    assert "ApplicationComponent:mypkg.users.UserService" in nodes
    assert "ApplicationService:mypkg.users.UserService.create_user" in nodes
    assert "ApplicationService:mypkg.users.get_user" in nodes
    assert "ApplicationInterface:GET /users/{uid}: get_user" in nodes


def test_to_graph_excludes_private():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    g = to_graph(pf, doc_id="git:test:users.py")
    nodes = set(g["extracted_nodes"])
    assert "ApplicationService:mypkg.users.UserService._internal" not in nodes


def test_to_graph_includes_import_placeholders():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    g = to_graph(pf, doc_id="git:test:users.py")
    nodes = set(g["extracted_nodes"])
    # imports become placeholder ApplicationComponent nodes
    assert "ApplicationComponent:fastapi" in nodes
    assert "ApplicationComponent:services.helpers" in nodes
    assert "ApplicationComponent:os" in nodes


def test_to_graph_edges_have_expected_shapes():
    pf = parse(SAMPLE, "src/mypkg/users.py")
    g = to_graph(pf, doc_id="git:test:users.py")
    edges = g["extracted_edges"]

    # Composition module -> class
    assert any(
        "ApplicationComponent:mypkg.users->Composition[EXTRACTED]->"
        "ApplicationComponent:mypkg.users.UserService" == e
        for e in edges
    )
    # Realization class -> service
    assert any(
        "ApplicationComponent:mypkg.users.UserService->Realization[EXTRACTED]->"
        "ApplicationService:mypkg.users.UserService.create_user" == e
        for e in edges
    )
    # Realization service -> interface
    assert any(
        "ApplicationService:mypkg.users.get_user->Realization[EXTRACTED]->"
        "ApplicationInterface:GET /users/{uid}: get_user" == e
        for e in edges
    )
    # Import composition with placeholder qualifier
    assert any(
        e == "ApplicationComponent:mypkg.users->Composition[placeholder,EXTRACTED]->"
             "ApplicationComponent:fastapi"
        for e in edges
    )


def test_to_graph_output_is_writer_compatible():
    """Every node and edge must match graph_writer's regexes."""
    pf = parse(SAMPLE, "src/mypkg/users.py")
    g = to_graph(pf, doc_id="git:test:users.py")
    for n in g["extracted_nodes"]:
        assert _NODE_RE.match(n), f"node failed regex: {n!r}"
    for e in g["extracted_edges"]:
        assert _EDGE_RE.match(e), f"edge failed regex: {e!r}"


def test_module_name_handles_init_and_no_src_prefix():
    pf = parse('"""x"""\n', "kb-agent/services/foo.py")
    assert pf.module_name == "services.foo"
    pf2 = parse('"""x"""\n', "mypkg/__init__.py")
    assert pf2.module_name == "mypkg"


def test_parse_handles_empty_module():
    pf = parse("", "src/empty.py")
    assert pf.module_name == "empty"
    assert pf.module_doc is None
    assert pf.classes == []
    assert pf.functions == []
