"""Dataclasses describing the structured output of an AST parser.

Each language-specific parser in this package returns a `ParsedFile`, which is then
fed to `services.ast_to_archimate.to_graph` to produce ArchiMate nodes/edges
consumable by `services.graph_writer.write_graph_to_spanner`.
"""
from dataclasses import dataclass, field


@dataclass
class ParsedRoute:
    """An HTTP route discovered from a framework decorator (e.g. FastAPI)."""
    method: str             # "GET", "POST", ...
    path: str               # "/users/{id}"
    handler_name: str       # qualified handler name owning the route
    decorator_source: str   # raw "@router.post(...)" for traceability


@dataclass
class ParsedFunction:
    name: str
    qualified_name: str     # "module.Class.method" or "module.func"
    docstring: str | None
    signature: str          # "(self, x: int) -> str"
    decorators: list[str]
    is_method: bool
    owner_class: str | None
    is_public: bool         # not name.startswith("_")


@dataclass
class ParsedClass:
    name: str
    qualified_name: str     # "module.Class"
    docstring: str | None
    bases: list[str]
    methods: list[ParsedFunction]


@dataclass
class ParsedFile:
    module_name: str        # dotted path inferred from file_path
    module_doc: str | None
    classes: list[ParsedClass] = field(default_factory=list)
    functions: list[ParsedFunction] = field(default_factory=list)  # module-level only
    imports: list[str] = field(default_factory=list)               # fully-qualified module names
    routes: list[ParsedRoute] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)             # module-level UPPER_SNAKE assignments
