"""Conservative fallback parser for unknown languages.

Strategy: avoid garbage in the graph. We do NOT instantiate a tree-sitter
language we don't have a binding for; instead we extract a flat list of
top-level identifier-looking tokens from the source via a simple regex and
emit them as `ParsedClass` entries (which become `ApplicationComponent`
nodes downstream). This is deliberately minimal — better to extract less
than to pollute the graph with noise.
"""
from __future__ import annotations

import re
from pathlib import Path

from .types import ParsedClass, ParsedFile

# Match common top-level declaration keywords across many languages.
_TOPLEVEL_RE = re.compile(
    r"^\s*(?:export\s+)?"
    r"(?:public\s+|private\s+|protected\s+|static\s+|async\s+|abstract\s+|final\s+)*"
    r"(?:class|struct|interface|enum|trait|object|module|fn|func|function|def)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


def parse(source: str, file_path: str) -> ParsedFile:
    module_name = Path(file_path).stem or "unknown_module"
    seen: set[str] = set()
    classes: list[ParsedClass] = []
    for m in _TOPLEVEL_RE.finditer(source):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        classes.append(
            ParsedClass(
                name=name,
                qualified_name=f"{module_name}.{name}",
                docstring=None,
                bases=[],
                methods=[],
            )
        )
    return ParsedFile(
        module_name=module_name,
        module_doc=None,
        classes=classes,
        functions=[],
        imports=[],
        routes=[],
        constants=[],
    )
