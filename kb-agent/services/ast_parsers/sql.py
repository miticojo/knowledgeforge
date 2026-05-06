"""SQL AST parser using `sqlglot`.

SQL files have no module / class / function concept the way OO languages do.
Convention adopted here:

    * `module_name`   = file stem (e.g. "schema" for "db/schema.sql").
    * `classes`       = each `CREATE TABLE` becomes a `ParsedClass` whose
                        `bases` list contains a synthetic `__entity__` marker
                        so the ArchiMate mapping emits `DataObject` nodes.
                        The class's `methods` list is empty.
    * `functions`     = always [].
    * `imports`       = always [].
    * `routes`        = always [].
    * Foreign keys / view dependencies are surfaced via `ParsedClass.bases`:
                        - FK target table names are appended (without the
                          `__entity__` marker semantics getting in the way:
                          they are plain table names, treated as Access edges
                          by the mapping layer).
                        - For `CREATE VIEW`, the referenced tables are
                          appended as bases (mapping layer turns these into
                          Realization edges).

The mapping layer (`ast_to_archimate.to_graph`) was extended to recognize the
`__entity__` marker and SQL-style `bases` so this parser stays decoupled from
graph emission decisions.
"""
from __future__ import annotations

from pathlib import Path

import sqlglot
from sqlglot import exp

from .types import ParsedClass, ParsedFile

# Sentinel marker used to flag DataObject candidates in `ParsedClass.bases`.
ENTITY_MARKER = "__entity__"
# Bases that begin with this prefix are treated as FK access edges.
FK_PREFIX = "__fk__:"
# Bases that begin with this prefix are treated as view -> table realizations.
VIEW_REF_PREFIX = "__view_ref__:"


def _module_name_from_file(file_path: str) -> str:
    return Path(file_path).stem or "unknown_module"


def _table_name(table: exp.Table | exp.Identifier | None) -> str | None:
    if table is None:
        return None
    if isinstance(table, exp.Table):
        return table.name
    if isinstance(table, exp.Identifier):
        return table.name
    return None


def _extract_fk_targets(create: exp.Create) -> list[str]:
    """Return target table names referenced by FOREIGN KEY constraints."""
    out: list[str] = []
    for fk in create.find_all(exp.ForeignKey):
        ref = fk.args.get("reference")
        if ref is None:
            continue
        # ref is typically a Reference whose `this` is a Schema/Table
        target = ref.find(exp.Table)
        if target is not None and target.name:
            out.append(target.name)
    return out


def parse(source: str, file_path: str) -> ParsedFile:
    module_name = _module_name_from_file(file_path)
    classes: list[ParsedClass] = []
    seen_tables: set[str] = set()

    try:
        statements = sqlglot.parse(source)
    except Exception:
        statements = []

    for stmt in statements:
        if stmt is None:
            continue
        if not isinstance(stmt, exp.Create):
            continue
        kind = (stmt.kind or "").upper() if hasattr(stmt, "kind") else ""

        target = stmt.this
        # `target` is typically a Schema (with table+columns) or a Table.
        table_node: exp.Table | None = None
        if isinstance(target, exp.Schema):
            table_node = target.this if isinstance(target.this, exp.Table) else None
        elif isinstance(target, exp.Table):
            table_node = target
        tname = _table_name(table_node)
        if not tname or tname in seen_tables:
            continue

        bases: list[str] = [ENTITY_MARKER]

        if kind == "VIEW":
            # Collect tables referenced in the view's SELECT.
            select = stmt.expression
            if select is not None:
                for t in select.find_all(exp.Table):
                    n = t.name
                    if n and n != tname:
                        bases.append(f"{VIEW_REF_PREFIX}{n}")
        else:
            # TABLE (default). Collect FK targets.
            for fk_target in _extract_fk_targets(stmt):
                bases.append(f"{FK_PREFIX}{fk_target}")

        seen_tables.add(tname)
        classes.append(
            ParsedClass(
                name=tname,
                qualified_name=f"{module_name}.{tname}",
                docstring=None,
                bases=bases,
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
