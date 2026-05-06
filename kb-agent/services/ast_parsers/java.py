"""Java AST parser using tree-sitter.

Extracts:
  * package declaration (used as module name when present)
  * imports (fully-qualified names)
  * classes (with methods + annotations)
  * Spring REST handlers (`@GetMapping("/x")` etc., or `@RequestMapping(method=...)`)
  * JPA entities (`@Entity`) — flagged as DataObject candidates by adding
    a synthetic `__entity__` marker to the class's `bases` list.

Returns a `ParsedFile`. `module_name` is `<package>.<ClassFileBaseName>` if a
package is declared, else falls back to the file path.
"""
from __future__ import annotations

from pathlib import Path

import tree_sitter_java as tsjava
from tree_sitter import Language, Node, Parser

from .types import ParsedClass, ParsedFile, ParsedFunction, ParsedRoute

_HTTP_MAPPING_ANNOS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "PatchMapping": "PATCH",
    "DeleteMapping": "DELETE",
    "RequestMapping": "REQUEST",  # generic; method may be inside args
}
_ENTITY_ANNOS = {"Entity", "Table"}

_LANG = Language(tsjava.language())


def _text(n: Node) -> str:
    return n.text.decode("utf-8", errors="replace")


def _module_name_from_file(file_path: str) -> str:
    name = Path(file_path).stem
    return name or "unknown_module"


def _annotation_name(anno: Node) -> str | None:
    # marker_annotation: @Foo  -> child identifier
    # annotation: @Foo(args) -> child name + arguments
    name_node = anno.child_by_field_name("name")
    if name_node is not None:
        return _text(name_node)
    for c in anno.children:
        if c.type == "identifier":
            return _text(c)
    return None


def _annotation_first_string_arg(anno: Node) -> str:
    args = anno.child_by_field_name("arguments")
    if args is None:
        for c in anno.children:
            if c.type == "annotation_argument_list":
                args = c
                break
    if args is None:
        return ""
    for a in args.children:
        if a.type == "string_literal":
            inner = ""
            for sub in a.children:
                if sub.type == "string_fragment":
                    inner = _text(sub)
                    break
            return inner
        # named pair: value="..."
        if a.type == "element_value_pair":
            for sub in a.children:
                if sub.type == "string_literal":
                    for ss in sub.children:
                        if ss.type == "string_fragment":
                            return _text(ss)
    return ""


def _modifiers_annotations(decl: Node) -> list[Node]:
    """Return annotation nodes attached to a class/method via its `modifiers` child."""
    out: list[Node] = []
    for c in decl.children:
        if c.type == "modifiers":
            for m in c.children:
                if m.type in ("marker_annotation", "annotation"):
                    out.append(m)
    return out


def _collect_package(root: Node) -> str | None:
    for c in root.children:
        if c.type == "package_declaration":
            for sub in c.children:
                if sub.type in ("scoped_identifier", "identifier"):
                    return _text(sub)
    return None


def _collect_imports(root: Node) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for c in root.children:
        if c.type == "import_declaration":
            for sub in c.children:
                if sub.type in ("scoped_identifier", "identifier"):
                    name = _text(sub)
                    if name not in seen:
                        seen.add(name)
                        out.append(name)
                    break
    return out


def _build_method(
    method: Node, module_name: str, owner_class: str
) -> tuple[ParsedFunction, list[Node]]:
    name_node = method.child_by_field_name("name")
    name = _text(name_node) if name_node is not None else "<anonymous>"
    params = method.child_by_field_name("parameters")
    sig = _text(params) if params is not None else "()"
    ret = method.child_by_field_name("type")
    if ret is not None:
        sig = f"{sig} -> {_text(ret)}"
    annos = _modifiers_annotations(method)
    decorator_strs = [f"@{_annotation_name(a) or _text(a).lstrip('@')}" for a in annos]
    qn = f"{module_name}.{owner_class}.{name}"
    pf = ParsedFunction(
        name=name,
        qualified_name=qn,
        docstring=None,
        signature=sig,
        decorators=decorator_strs,
        is_method=True,
        owner_class=owner_class,
        is_public=not name.startswith("_"),
    )
    return pf, annos


def _route_from_annotations(
    annos: list[Node], handler_qn: str
) -> ParsedRoute | None:
    for a in annos:
        name = _annotation_name(a)
        if name and name in _HTTP_MAPPING_ANNOS:
            method = _HTTP_MAPPING_ANNOS[name]
            path = _annotation_first_string_arg(a)
            return ParsedRoute(
                method=method,
                path=path,
                handler_name=handler_qn,
                decorator_source=_text(a),
            )
    return None


def parse(source: str, file_path: str) -> ParsedFile:
    parser = Parser(_LANG)
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    package = _collect_package(root)
    file_stem = _module_name_from_file(file_path)
    module_name = f"{package}.{file_stem}" if package else file_stem

    classes: list[ParsedClass] = []
    routes: list[ParsedRoute] = []

    for c in root.children:
        if c.type != "class_declaration":
            continue
        name_node = c.child_by_field_name("name")
        if name_node is None:
            continue
        cls_name = _text(name_node)
        cls_qn = f"{module_name}.{cls_name}"
        cls_annos = _modifiers_annotations(c)

        bases: list[str] = []
        sup = c.child_by_field_name("superclass")
        if sup is not None:
            bases.append(_text(sup).replace("extends", "").strip())
        for ch in c.children:
            if ch.type == "super_interfaces":
                bases.append(_text(ch).replace("implements", "").strip())
        if any((_annotation_name(a) or "") in _ENTITY_ANNOS for a in cls_annos):
            bases.append("__entity__")

        methods: list[ParsedFunction] = []
        body = c.child_by_field_name("body")
        if body is not None:
            for sub in body.children:
                if sub.type == "method_declaration":
                    pf, m_annos = _build_method(sub, module_name, cls_name)
                    methods.append(pf)
                    route = _route_from_annotations(m_annos, pf.qualified_name)
                    if route:
                        routes.append(route)

        classes.append(
            ParsedClass(
                name=cls_name,
                qualified_name=cls_qn,
                docstring=None,
                bases=bases,
                methods=methods,
            )
        )

    return ParsedFile(
        module_name=module_name,
        module_doc=None,
        classes=classes,
        functions=[],
        imports=_collect_imports(root),
        routes=routes,
        constants=[],
    )
