"""Map a `ParsedFile` (AST output) into ArchiMate nodes and edges.

Returns a dict shaped like the existing `extract_graph` output that
`services.graph_writer.write_graph_to_spanner` already consumes:

    {
      "extracted_nodes": ["ApplicationComponent:mypkg.users", ...],
      "extracted_edges": [
          "ApplicationComponent:mypkg.users->Composition[EXTRACTED]->"
          "ApplicationComponent:mypkg.users.UserService",
          ...
      ],
    }

Node/edge string formats follow the regexes `_NODE_RE` and `_EDGE_RE` in
`services.graph_writer`. All edges are tagged `EXTRACTED` (deterministic AST
output). Import edges additionally carry the qualifier `placeholder` so the
target stub `ApplicationComponent` entities can be audited via the edge
`details` column once persisted.

Mapping rules (Python MVP):

    Module                       -> ApplicationComponent:<dotted.module>
    Class                        -> ApplicationComponent:<dotted.module.Class>
    Public function (module)     -> ApplicationService:<dotted.module.func>
    Public method (class)        -> ApplicationService:<dotted.module.Class.method>
    FastAPI route                -> ApplicationInterface:<METHOD> <path>: <handler>
    Class -> module              :: Composition (class composed in module)
    Service -> Component         :: Realization (service realizes its owning component)
    Interface -> Service         :: Realization (route interface realized by handler)
    Module -> imported module    :: Composition with qualifier "placeholder"

TODO (follow-up): cross-module function-call -> Triggering. Requires a two-pass
build of a global symbol table; deferred.

TODO (follow-up): the existing `compute_entity_embeddings` helper embeds only
the entity *name*, not its docstring. To improve retrieval for code entities,
extend that helper (or add a code-specific one) to embed docstrings as well.
"""
from __future__ import annotations

from .ast_parsers.types import ParsedFile

# Confidence label for all AST-derived edges. AST output is deterministic.
_CONFIDENCE = "EXTRACTED"

# Markers used by non-Python parsers to signal mapping intent via the
# `ParsedClass.bases` field (which is otherwise just a list of superclass
# names). Keeping these as bases (rather than expanding the dataclass) avoids
# breaking the shared `ParsedClass` schema.
_ENTITY_MARKER = "__entity__"          # JPA @Entity, TypeORM @Entity, SQL CREATE TABLE
_FK_PREFIX = "__fk__:"                 # SQL foreign-key target table
_VIEW_REF_PREFIX = "__view_ref__:"     # SQL view -> referenced table


def _node(entity_type: str, name: str) -> str:
    return f"{entity_type}:{name}"


def _edge(
    src_type: str,
    src_name: str,
    rel: str,
    tgt_type: str,
    tgt_name: str,
    qualifier: str = "",
    confidence: str = _CONFIDENCE,
) -> str:
    """Format an edge per `graph_writer._EDGE_RE`.

    Bracket payload is `qualifier,confidence` (either alone is also valid).
    `_parse_qualifier_confidence` in graph_writer.py recognizes any of:
       [EXTRACTED]  [Read,EXTRACTED]  [placeholder,EXTRACTED]
    """
    if qualifier:
        bracket = f"{qualifier},{confidence}"
    else:
        bracket = confidence
    return (
        f"{src_type}:{src_name}->{rel}[{bracket}]->{tgt_type}:{tgt_name}"
    )


def _route_node_name(method: str, path: str, handler: str) -> str:
    """Compose a route node name that carries retrieval signal in its name.

    `compute_entity_embeddings` embeds entity *names*, so we pack the HTTP method,
    path, and handler (short form) into the name. Decision recorded in plan rev 2.
    """
    short_handler = handler.rsplit(".", 1)[-1] if handler else ""
    if short_handler:
        return f"{method} {path}: {short_handler}"
    return f"{method} {path}"


def to_graph(parsed: ParsedFile, doc_id: str) -> dict:
    """Convert a ParsedFile into a graph_json dict.

    `doc_id` is accepted for forward compatibility (e.g. namespacing entity names
    per repo) but is not currently used; graph_writer records source via the
    Documents table.
    """
    nodes: list[str] = []
    edges: list[str] = []
    seen_nodes: set[str] = set()

    def add_node(s: str) -> None:
        if s not in seen_nodes:
            seen_nodes.add(s)
            nodes.append(s)

    module_name = parsed.module_name or "unknown_module"
    module_node = _node("ApplicationComponent", module_name)
    add_node(module_node)

    # Classes -> ApplicationComponent (or DataObject if flagged as @Entity / SQL table)
    # + Composition from module. FK / view-ref bases produce extra edges.
    for cls in parsed.classes:
        class_name = cls.qualified_name
        is_entity = _ENTITY_MARKER in cls.bases
        cls_type = "DataObject" if is_entity else "ApplicationComponent"
        class_node = _node(cls_type, class_name)
        add_node(class_node)
        edges.append(
            _edge(
                "ApplicationComponent", module_name,
                "Composition",
                cls_type, class_name,
            )
        )
        # SQL foreign keys -> Access edge between this DataObject and the
        # placeholder DataObject for the referenced table (same module scope).
        for base in cls.bases:
            if base.startswith(_FK_PREFIX):
                target_name = f"{module_name}.{base[len(_FK_PREFIX):]}"
                target_node = _node("DataObject", target_name)
                add_node(target_node)
                edges.append(
                    _edge(
                        cls_type, class_name,
                        "Access",
                        "DataObject", target_name,
                    )
                )
            elif base.startswith(_VIEW_REF_PREFIX):
                target_name = f"{module_name}.{base[len(_VIEW_REF_PREFIX):]}"
                target_node = _node("DataObject", target_name)
                add_node(target_node)
                edges.append(
                    _edge(
                        cls_type, class_name,
                        "Realization",
                        "DataObject", target_name,
                    )
                )
        # Public methods -> ApplicationService + Realization from class
        for method in cls.methods:
            if not method.is_public:
                continue
            svc_node = _node("ApplicationService", method.qualified_name)
            add_node(svc_node)
            edges.append(
                _edge(
                    cls_type, class_name,
                    "Realization",
                    "ApplicationService", method.qualified_name,
                )
            )

    # Module-level public functions -> ApplicationService + Realization from module
    for fn in parsed.functions:
        if not fn.is_public:
            continue
        svc_node = _node("ApplicationService", fn.qualified_name)
        add_node(svc_node)
        edges.append(
            _edge(
                "ApplicationComponent", module_name,
                "Realization",
                "ApplicationService", fn.qualified_name,
            )
        )

    # Routes -> ApplicationInterface + Realization from owning service
    for route in parsed.routes:
        iface_name = _route_node_name(route.method, route.path, route.handler_name)
        iface_node = _node("ApplicationInterface", iface_name)
        add_node(iface_node)
        # Owning service must already exist (we created it above for public fns/methods).
        # If the handler was private and skipped, fall back to its module/class component.
        svc_qn = route.handler_name
        svc_node = _node("ApplicationService", svc_qn)
        if svc_node in seen_nodes:
            edges.append(
                _edge(
                    "ApplicationService", svc_qn,
                    "Realization",
                    "ApplicationInterface", iface_name,
                )
            )
        else:
            # Handler not exposed as a Service (private). Realize from module component.
            edges.append(
                _edge(
                    "ApplicationComponent", module_name,
                    "Realization",
                    "ApplicationInterface", iface_name,
                )
            )

    # Imports -> placeholder ApplicationComponent + Composition (placeholder qualifier)
    for imp in parsed.imports:
        if not imp:
            continue
        target_node = _node("ApplicationComponent", imp)
        add_node(target_node)
        edges.append(
            _edge(
                "ApplicationComponent", module_name,
                "Composition",
                "ApplicationComponent", imp,
                qualifier="placeholder",
            )
        )

    return {"extracted_nodes": nodes, "extracted_edges": edges}
