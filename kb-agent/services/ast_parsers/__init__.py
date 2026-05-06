"""AST parser registry: dispatches by file extension to the right language parser.

Registered languages:
    Python      .py
    TypeScript  .ts .tsx
    JavaScript  .js .jsx       (uses the TypeScript grammar; superset)
    Java        .java
    Go          .go
    SQL         .sql

Unknown extensions return None from `get_parser`, which causes
`git_ingester` to skip the file (files_skipped counter). The
`generic.parse` fallback is intentionally NOT auto-dispatched — it exists
for callers that want best-effort symbol extraction for unsupported
languages but do not want to pollute the default graph with noisy
heuristic results. To opt in, call `generic.parse(source, path)` directly
or merge it into PARSERS in your own configuration.
"""
from pathlib import Path
from typing import Callable

from .generic import parse as parse_generic
from .markdown import parse as parse_markdown
from .go import parse as parse_go
from .java import parse as parse_java
from .python import parse as parse_python
from .sql import parse as parse_sql
from .typescript import parse as parse_typescript
from .types import ParsedClass, ParsedFile, ParsedFunction, ParsedRoute

# extension -> callable(source: str, file_path: str) -> ParsedFile
PARSERS: dict[str, Callable[[str, str], ParsedFile]] = {
    ".py": parse_python,
    ".ts": parse_typescript,
    ".tsx": parse_typescript,
    ".js": parse_typescript,
    ".jsx": parse_typescript,
    ".java": parse_java,
    ".go": parse_go,
    ".sql": parse_sql,
    # Markdown returns graph_json directly (not ParsedFile); git_ingester
    # detects this shape and bypasses ast_to_archimate.to_graph.
    ".md": parse_markdown,
    ".markdown": parse_markdown,
}


def get_parser(path: Path) -> Callable[[str, str], ParsedFile] | None:
    """Return the parser for `path` based on extension, or None if unsupported."""
    return PARSERS.get(path.suffix.lower())


__all__ = [
    "PARSERS",
    "get_parser",
    "ParsedFile",
    "ParsedClass",
    "ParsedFunction",
    "ParsedRoute",
    "parse_python",
    "parse_typescript",
    "parse_java",
    "parse_go",
    "parse_sql",
    "parse_generic",
    "parse_markdown",
]
