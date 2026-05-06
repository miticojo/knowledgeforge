"""Python AST parser using stdlib `ast`.

Extracts module docstring, classes (with docstrings + bases + methods),
module-level functions (with docstrings + signature + decorators), imports,
top-level UPPER_SNAKE constants, and FastAPI-style HTTP route decorators.
"""
from __future__ import annotations

import ast
import re

from .types import ParsedClass, ParsedFile, ParsedFunction, ParsedRoute

# Decorator HTTP verbs we recognize as a "route". Covers FastAPI / Flask / Starlette
# / APIRouter style decorators where the verb is the attribute access:
#   @app.get(...), @router.post(...), @api_router.delete(...)
_HTTP_VERBS = {"get", "post", "put", "patch", "delete", "head", "options"}

# Common source-root prefixes to strip when deriving a dotted module name.
_SOURCE_ROOT_PREFIXES = ("src/", "lib/", "kb-agent/", "app/")

_CONST_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _module_name_from_path(file_path: str) -> str:
    """Convert a file path like 'src/mypkg/users.py' to dotted 'mypkg.users'."""
    p = file_path.replace("\\", "/")
    for prefix in _SOURCE_ROOT_PREFIXES:
        if p.startswith(prefix):
            p = p[len(prefix):]
            break
    if p.endswith(".py"):
        p = p[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".").strip(".")


def _safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _build_signature(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Reconstruct a readable signature string."""
    try:
        args_src = ast.unparse(func.args)
    except Exception:
        args_src = ", ".join(a.arg for a in func.args.args)
    ret = _safe_unparse(func.returns)
    return f"({args_src}) -> {ret}" if ret else f"({args_src})"


def _decorator_strings(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    out = []
    for d in func.decorator_list:
        s = _safe_unparse(d)
        if s:
            out.append(f"@{s}")
    return out


def _extract_route(
    func: ast.FunctionDef | ast.AsyncFunctionDef, qualified_name: str
) -> ParsedRoute | None:
    """Detect a FastAPI/Flask-style HTTP decorator on `func` and return a ParsedRoute."""
    for d in func.decorator_list:
        # Decorator must be a Call: @router.post("/x")
        if not isinstance(d, ast.Call):
            continue
        verb_name = None
        if isinstance(d.func, ast.Attribute):
            verb_name = d.func.attr
        if verb_name is None or verb_name.lower() not in _HTTP_VERBS:
            continue
        # First positional arg expected to be a string literal path
        path = ""
        if d.args and isinstance(d.args[0], ast.Constant) and isinstance(d.args[0].value, str):
            path = d.args[0].value
        return ParsedRoute(
            method=verb_name.upper(),
            path=path,
            handler_name=qualified_name,
            decorator_source=f"@{_safe_unparse(d)}",
        )
    return None


def _build_function(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    module_name: str,
    owner_class: str | None,
) -> ParsedFunction:
    if owner_class:
        qn = f"{module_name}.{owner_class}.{func.name}"
    else:
        qn = f"{module_name}.{func.name}"
    return ParsedFunction(
        name=func.name,
        qualified_name=qn,
        docstring=ast.get_docstring(func),
        signature=_build_signature(func),
        decorators=_decorator_strings(func),
        is_method=owner_class is not None,
        owner_class=owner_class,
        is_public=not func.name.startswith("_"),
    )


def _collect_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    seen: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name and name not in seen:
                    seen.add(name)
                    imports.append(name)
        elif isinstance(node, ast.ImportFrom):
            # Skip relative imports (no module) — they don't yield a stable dotted name
            if node.module:
                if node.module not in seen:
                    seen.add(node.module)
                    imports.append(node.module)
    return imports


def _collect_constants(tree: ast.Module) -> list[str]:
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and _CONST_NAME_RE.match(target.id):
                    out.append(target.id)
    return out


def parse(source: str, file_path: str) -> ParsedFile:
    """Parse a Python source string into a ParsedFile."""
    tree = ast.parse(source)
    module_name = _module_name_from_path(file_path)

    classes: list[ParsedClass] = []
    functions: list[ParsedFunction] = []
    routes: list[ParsedRoute] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods: list[ParsedFunction] = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    pf = _build_function(sub, module_name, owner_class=node.name)
                    methods.append(pf)
                    route = _extract_route(sub, pf.qualified_name)
                    if route:
                        routes.append(route)
            bases = [_safe_unparse(b) for b in node.bases if _safe_unparse(b)]
            classes.append(
                ParsedClass(
                    name=node.name,
                    qualified_name=f"{module_name}.{node.name}",
                    docstring=ast.get_docstring(node),
                    bases=bases,
                    methods=methods,
                )
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pf = _build_function(node, module_name, owner_class=None)
            functions.append(pf)
            route = _extract_route(node, pf.qualified_name)
            if route:
                routes.append(route)

    return ParsedFile(
        module_name=module_name,
        module_doc=ast.get_docstring(tree),
        classes=classes,
        functions=functions,
        imports=_collect_imports(tree),
        routes=routes,
        constants=_collect_constants(tree),
    )
