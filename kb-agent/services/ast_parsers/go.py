"""Go AST parser using tree-sitter.

Extracts:
  * package clause
  * imports (string literal paths)
  * structs -> reported as `ParsedClass` (Components downstream).
  * exported funcs/methods (UpperCamel — Go's export rule) -> `ParsedFunction`.
  * HTTP handlers detected as calls to `http.HandleFunc(path, handler)` and
    `<router>.HandleFunc(path, handler)` patterns. The first string-literal
    argument is the path; the handler name is the second argument's identifier
    (or `<anonymous>` if a function literal).

Returns a `ParsedFile`. `module_name` is `<package>.<file_stem>`.
"""
from __future__ import annotations

from pathlib import Path

import tree_sitter_go as tsgo
from tree_sitter import Language, Node, Parser

from .types import ParsedClass, ParsedFile, ParsedFunction, ParsedRoute

_LANG = Language(tsgo.language())


def _text(n: Node) -> str:
    return n.text.decode("utf-8", errors="replace")


def _is_exported(name: str) -> bool:
    return bool(name) and name[0].isupper()


def _collect_package(root: Node) -> str | None:
    for c in root.children:
        if c.type == "package_clause":
            for sub in c.children:
                if sub.type == "package_identifier":
                    return _text(sub)
    return None


def _string_value(n: Node) -> str:
    if n.type != "interpreted_string_literal":
        return ""
    for c in n.children:
        if c.type == "interpreted_string_literal_content":
            return _text(c)
    return ""


def _collect_imports(root: Node) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def visit(node: Node) -> None:
        if node.type == "import_spec":
            for c in node.children:
                if c.type == "interpreted_string_literal":
                    v = _string_value(c)
                    if v and v not in seen:
                        seen.add(v)
                        out.append(v)
        for c in node.children:
            visit(c)

    visit(root)
    return out


def _build_signature(node: Node) -> str:
    params = node.child_by_field_name("parameters")
    sig = _text(params) if params is not None else "()"
    ret = node.child_by_field_name("result")
    if ret is not None:
        sig = f"{sig} {_text(ret)}"
    return sig


def _route_from_call(call: Node, module_name: str) -> ParsedRoute | None:
    fn = call.child_by_field_name("function")
    if fn is None:
        return None
    if fn.type == "selector_expression":
        field = fn.child_by_field_name("field")
        if field is None or _text(field) != "HandleFunc":
            return None
    elif fn.type == "identifier":
        if _text(fn) != "HandleFunc":
            return None
    else:
        return None
    args = call.child_by_field_name("arguments")
    if args is None:
        return None
    str_args = [a for a in args.children if a.type == "interpreted_string_literal"]
    if not str_args:
        return None
    path = _string_value(str_args[0])
    handler = "<anonymous>"
    # Find second positional argument that is an identifier or selector_expression
    positional = [a for a in args.children if a.is_named]
    if len(positional) >= 2:
        h = positional[1]
        if h.type in ("identifier", "selector_expression"):
            handler = _text(h)
    return ParsedRoute(
        method="ANY",
        path=path,
        handler_name=f"{module_name}.{handler}",
        decorator_source=_text(call),
    )


def parse(source: str, file_path: str) -> ParsedFile:
    parser = Parser(_LANG)
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    package = _collect_package(root)
    file_stem = Path(file_path).stem
    module_name = f"{package}.{file_stem}" if package else file_stem

    classes: list[ParsedClass] = []
    functions: list[ParsedFunction] = []
    routes: list[ParsedRoute] = []

    for c in root.children:
        if c.type == "type_declaration":
            for spec in c.children:
                if spec.type != "type_spec":
                    continue
                name_node = spec.child_by_field_name("name")
                if name_node is None:
                    continue
                struct_name = _text(name_node)
                # Only structs become components; aliases / interfaces ignored for MVP.
                ttype = spec.child_by_field_name("type")
                if ttype is None or ttype.type != "struct_type":
                    continue
                classes.append(
                    ParsedClass(
                        name=struct_name,
                        qualified_name=f"{module_name}.{struct_name}",
                        docstring=None,
                        bases=[],
                        methods=[],
                    )
                )
        elif c.type == "function_declaration":
            name_node = c.child_by_field_name("name")
            if name_node is None:
                continue
            fname = _text(name_node)
            if not _is_exported(fname):
                continue
            functions.append(
                ParsedFunction(
                    name=fname,
                    qualified_name=f"{module_name}.{fname}",
                    docstring=None,
                    signature=_build_signature(c),
                    decorators=[],
                    is_method=False,
                    owner_class=None,
                    is_public=True,
                )
            )
        elif c.type == "method_declaration":
            name_node = c.child_by_field_name("name")
            if name_node is None:
                continue
            mname = _text(name_node)
            if not _is_exported(mname):
                continue
            # Receiver type: parameter_list -> parameter_declaration -> type
            recv = c.child_by_field_name("receiver")
            recv_type = ""
            if recv is not None:
                for pd in recv.children:
                    if pd.type == "parameter_declaration":
                        t = pd.child_by_field_name("type")
                        if t is not None:
                            recv_type = _text(t).lstrip("*").strip()
            owner = recv_type or "<receiver>"
            qn = f"{module_name}.{owner}.{mname}"
            pf = ParsedFunction(
                name=mname,
                qualified_name=qn,
                docstring=None,
                signature=_build_signature(c),
                decorators=[],
                is_method=True,
                owner_class=owner,
                is_public=True,
            )
            # Attach to existing class if present, else create a synthetic one.
            target = next((k for k in classes if k.name == owner), None)
            if target is None:
                target = ParsedClass(
                    name=owner,
                    qualified_name=f"{module_name}.{owner}",
                    docstring=None,
                    bases=[],
                    methods=[],
                )
                classes.append(target)
            target.methods.append(pf)

    def visit_calls(n: Node) -> None:
        if n.type == "call_expression":
            r = _route_from_call(n, module_name)
            if r is not None:
                routes.append(r)
        for c in n.children:
            visit_calls(c)

    visit_calls(root)

    return ParsedFile(
        module_name=module_name,
        module_doc=None,
        classes=classes,
        functions=functions,
        imports=_collect_imports(root),
        routes=routes,
        constants=[],
    )
