"""Tests for the AST parser registry: dispatch by file extension."""
from pathlib import Path

from services.ast_parsers import (
    PARSERS,
    get_parser,
    parse_generic,
    parse_go,
    parse_java,
    parse_python,
    parse_sql,
    parse_typescript,
)


def test_dispatch_python():
    assert get_parser(Path("foo.py")) is parse_python


def test_dispatch_typescript_family():
    assert get_parser(Path("a.ts")) is parse_typescript
    assert get_parser(Path("a.tsx")) is parse_typescript
    assert get_parser(Path("a.js")) is parse_typescript
    assert get_parser(Path("a.jsx")) is parse_typescript


def test_dispatch_java():
    assert get_parser(Path("Foo.java")) is parse_java


def test_dispatch_go():
    assert get_parser(Path("main.go")) is parse_go


def test_dispatch_sql():
    assert get_parser(Path("schema.sql")) is parse_sql


def test_dispatch_unknown_returns_none():
    """Unknown extensions are skipped (None) so git_ingester increments files_skipped.

    The generic fallback is intentionally NOT auto-dispatched — see
    services/ast_parsers/__init__.py docstring.
    """
    assert get_parser(Path("foo.rs")) is None
    assert get_parser(Path("foo.unknownext")) is None
    assert get_parser(Path("README.md")) is None


def test_case_insensitive_extension():
    assert get_parser(Path("Foo.PY")) is parse_python
    assert get_parser(Path("Foo.JAVA")) is parse_java


def test_generic_parser_callable_directly():
    """The generic parser is exported and works on arbitrary text."""
    src = "class Alpha {}\nfunc Beta() {}\ndef gamma(): pass\n"
    pf = parse_generic(src, "weird.xyz")
    names = {c.name for c in pf.classes}
    assert {"Alpha", "Beta", "gamma"}.issubset(names)


def test_registry_contains_expected_extensions():
    expected = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".sql"}
    assert expected.issubset(set(PARSERS.keys()))
