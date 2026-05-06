"""TypeScript / JavaScript AST parser using tree-sitter.

Extracts:
  * imports (`import ... from "x"`, `require("x")`)
  * classes (with methods and decorators)
  * exported / module-level functions
  * REST routes:
      - Express-style: `app.get('/path', handler)` / `router.post(...)`, etc.
      - NestJS-style: `@Get('/path')` / `@Post('/path')` on class methods.
  * Interfaces / classes flagged as DataObject candidates only when they look
    like ORM model definitions: classes decorated with `@Entity` (TypeORM) or
    extending `Model` (heuristic). Conservative: we do NOT promote plain
    `interface` declarations to DataObjects to avoid graph noise.

Returns a `ParsedFile`. ORM-model classes are signalled via the class's
`bases` field (we add a synthetic `__entity__` marker base) so the existing
`ast_to_archimate.to_graph` mapping can choose to emit `DataObject` instead
of `ApplicationComponent` for them.
"""
from __future__ import annotations

from typing import Iterable

import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Node, Parser

from .types import ParsedClass, ParsedFile, ParsedFunction, ParsedRoute

_HTTP_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "all", "use"}
_NEST_DECORATORS = {"Get", "Post", "Put", "Patch", "Delete", "Head", "Options", "All"}
_ENTITY_DECORATORS = {"Entity", "Table", "Model"}

_SOURCE_ROOT_PREFIXES = ("src/", "lib/", "app/")


def _module_name_from_path(file_path: str) -> str:
    p = file_path.replace("\\", "/")
    for prefix in _SOURCE_ROOT_PREFIXES:
        if p.startswith(prefix):
            p = p[len(prefix):]
            break
    for ext in (".tsx", ".ts", ".jsx", ".js"):
        if p.endswith(ext):
            p = p[: -len(ext)]
            break
    if p.endswith("/index"):
        p = p[: -len("/index")]
    return p.replace("/", ".").strip(".")


def _get_parser(file_path: str) -> Parser:
    if file_path.endswith(".tsx") or file_path.endswith(".jsx"):
        lang = Language(tstypescript.language_tsx())
    else:
        lang = Language(tstypescript.language_typescript())
    return Parser(lang)


def _text(n: Node) -> str:
    return n.text.decode("utf-8", errors="replace")


def _child_by_field(n: Node, field: str) -> Node | None:
    return n.child_by_field_name(field)


def _string_literal_value(n: Node) -> str | None:
    """Return the inner value of a `string` node, else None."""
    if n.type != "string":
        return None
    for c in n.children:
        if c.type == "string_fragment":
            return _text(c)
    # Empty string literal "" has no fragment; return ""
    return ""


def _decorators_text(decorators: list[Node]) -> list[str]:
    return [f"@{_text(d).lstrip('@').strip()}" for d in decorators]


def _decorator_call_name(dec: Node) -> str | None:
    """Given a `decorator` node, return the decorator's call name (e.g. "Get")."""
    # decorator children: [@] [call_expression | identifier | member_expression]
    for c in dec.children:
        if c.type == "call_expression":
            fn = c.child_by_field_name("function")
            if fn is None and c.children:
                fn = c.children[0]
            if fn is None:
                continue
            if fn.type == "identifier":
                return _text(fn)
            if fn.type == "member_expression":
                prop = fn.child_by_field_name("property")
                if prop is not None:
                    return _text(prop)
        if c.type == "identifier":
            return _text(c)
    return None


def _decorator_first_string_arg(dec: Node) -> str:
    for c in dec.children:
        if c.type == "call_expression":
            args = c.child_by_field_name("arguments")
            if args is None:
                continue
            for a in args.children:
                if a.type == "string":
                    v = _string_literal_value(a)
                    return v or ""
    return ""


def _collect_imports(root: Node) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def visit(node: Node) -> None:
        if node.type == "import_statement":
            src = node.child_by_field_name("source")
            if src is not None:
                v = _string_literal_value(src)
                if v and v not in seen:
                    seen.add(v)
                    out.append(v)
        elif node.type == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "identifier" and _text(fn) == "require":
                args = node.child_by_field_name("arguments")
                if args is not None:
                    for a in args.children:
                        if a.type == "string":
                            v = _string_literal_value(a)
                            if v and v not in seen:
                                seen.add(v)
                                out.append(v)
        for c in node.children:
            visit(c)

    visit(root)
    return out


def _node_decorators(node: Node) -> list[Node]:
    """Return decorator children attached to a class or method node."""
    return [c for c in node.children if c.type == "decorator"]


def _build_function(
    name: str,
    node: Node,
    module_name: str,
    owner_class: str | None,
    decorators: list[Node],
) -> ParsedFunction:
    qn = f"{module_name}.{owner_class}.{name}" if owner_class else f"{module_name}.{name}"
    params = node.child_by_field_name("parameters")
    sig = _text(params) if params is not None else "()"
    ret = node.child_by_field_name("return_type")
    if ret is not None:
        sig = f"{sig} {_text(ret)}"
    return ParsedFunction(
        name=name,
        qualified_name=qn,
        docstring=None,
        signature=sig,
        decorators=_decorators_text(decorators),
        is_method=owner_class is not None,
        owner_class=owner_class,
        is_public=not name.startswith("_"),
    )


def _extract_route_from_call(call: Node, handler_qn: str) -> ParsedRoute | None:
    """Detect Express-style `app.get('/p', handler)` calls. Returns route or None."""
    fn = call.child_by_field_name("function")
    if fn is None or fn.type != "member_expression":
        return None
    prop = fn.child_by_field_name("property")
    if prop is None:
        return None
    verb = _text(prop).lower()
    if verb not in _HTTP_VERBS or verb == "use":
        return None
    args = call.child_by_field_name("arguments")
    if args is None:
        return None
    path = ""
    for a in args.children:
        if a.type == "string":
            path = _string_literal_value(a) or ""
            break
    return ParsedRoute(
        method=verb.upper(),
        path=path,
        handler_name=handler_qn,
        decorator_source=_text(call),
    )


def _route_from_method_decorators(
    decorators: list[Node], handler_qn: str
) -> ParsedRoute | None:
    for d in decorators:
        name = _decorator_call_name(d)
        if name and name in _NEST_DECORATORS:
            path = _decorator_first_string_arg(d)
            return ParsedRoute(
                method=name.upper(),
                path=path,
                handler_name=handler_qn,
                decorator_source=_text(d),
            )
    return None


def _is_entity_class(decorators: list[Node]) -> bool:
    for d in decorators:
        name = _decorator_call_name(d)
        if name and name in _ENTITY_DECORATORS:
            return True
    return False


def _iter_top_level(root: Node) -> Iterable[tuple[Node, list[Node]]]:
    """Yield (node, decorators) for each top-level declaration.

    Handles `export_statement` wrappers and accumulates leading `decorator`
    children into the wrapped declaration.
    """
    for c in root.children:
        if c.type == "export_statement":
            # children: [export] [decorator]* [declaration]
            decs = [x for x in c.children if x.type == "decorator"]
            for x in c.children:
                if x.type in ("class_declaration", "function_declaration", "lexical_declaration"):
                    yield x, decs + _node_decorators(x)
        else:
            yield c, _node_decorators(c)


def parse(source: str, file_path: str) -> ParsedFile:
    parser = _get_parser(file_path)
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    module_name = _module_name_from_path(file_path) or "unknown_module"

    classes: list[ParsedClass] = []
    functions: list[ParsedFunction] = []
    routes: list[ParsedRoute] = []

    for node, decs in _iter_top_level(root):
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            cls_name = _text(name_node)
            cls_qn = f"{module_name}.{cls_name}"
            methods: list[ParsedFunction] = []
            body = node.child_by_field_name("body")
            if body is not None:
                pending_decs: list[Node] = []
                for sub in body.children:
                    if sub.type == "decorator":
                        pending_decs.append(sub)
                        continue
                    if sub.type == "method_definition":
                        # Decorators may be attached directly to the method
                        # OR appear as preceding siblings in class_body.
                        m_decs = pending_decs + _node_decorators(sub)
                        pending_decs = []
                        m_name_node = sub.child_by_field_name("name")
                        if m_name_node is None:
                            continue
                        m_name = _text(m_name_node)
                        pf = _build_function(m_name, sub, module_name, cls_name, m_decs)
                        methods.append(pf)
                        route = _route_from_method_decorators(m_decs, pf.qualified_name)
                        if route:
                            routes.append(route)
                    elif sub.is_named:
                        # Any other named node resets pending decorators.
                        pending_decs = []
            bases: list[str] = []
            heritage = None
            for c in node.children:
                if c.type == "class_heritage":
                    heritage = c
                    break
            if heritage is not None:
                bases.append(_text(heritage).replace("extends", "").strip())
            if _is_entity_class(decs):
                bases.append("__entity__")
            classes.append(
                ParsedClass(
                    name=cls_name,
                    qualified_name=cls_qn,
                    docstring=None,
                    bases=bases,
                    methods=methods,
                )
            )
        elif node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            fname = _text(name_node)
            pf = _build_function(fname, node, module_name, None, decs)
            functions.append(pf)

    # Express-style routes from any top-level call expressions.
    def visit_calls(n: Node) -> None:
        if n.type == "call_expression":
            r = _extract_route_from_call(n, f"{module_name}.<anonymous>")
            if r is not None:
                routes.append(r)
        for c in n.children:
            visit_calls(c)

    visit_calls(root)

    imports = _collect_imports(root)

    return ParsedFile(
        module_name=module_name,
        module_doc=None,
        classes=classes,
        functions=functions,
        imports=imports,
        routes=routes,
        constants=[],
    )
