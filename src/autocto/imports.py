"""Real import resolution: turn each file's import statements into edges to actual files.

Replaces the stem name-matching that maintenance_cost.compute_fan_in and
architectural_debt.build_import_graph used (`from a.util import x` and `from b.util
import y` both credited every file named `util`). Here an import is resolved to the one
file it names, or to nothing when it names something outside the repo.

Standard library only, so the zero-dependency property holds:

- Python: parsed with `ast` (a regex cannot tell a docstring from a statement). Handles
  `import a.b`, `from a.b import c` (c may be a submodule or a name), relative imports
  (`from . import x`, `from ..pkg import y`), packages (`pkg/__init__.py`) and `src/`
  layouts. Files that do not parse contribute no edges.
- JS/TS: relative specifiers (`./x`, `../x`) resolved against the importing file's
  directory, trying the listed extensions and `index.*` in a directory, and mapping a
  `.js` specifier to its `.ts` source. Bare specifiers (`react`) are external and give
  no edge.

Known limits: tsconfig/webpack path aliases, `sys.path` edits, `__import__` and other
dynamic imports are not followed, and an import that names two same-named top-level
packages in different roots resolves to the first root that has it.

Paths are repo-relative with forward slashes on every platform.
"""

from __future__ import annotations

import ast
import posixpath
import re
import warnings
from collections.abc import Mapping

_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
# `import x from 'p'`, `export { x } from 'p'`, `require('p')`, `import('p')`.
_JS_IMPORT_RE = re.compile(
    r"""(?:\b(?:import|export)\b[^'"\n;]*?\bfrom\s*|\brequire\s*\(\s*|\bimport\s*\(\s*|\bimport\s+)['"]([^'"]+)['"]"""
)
_FALLBACK_ROOTS = ("src", "")


def _python_roots(files: set[str]) -> dict[str, str]:
    """Map every .py file to its import root: the directory above its top-level package.

    Walks up while the parent directory holds an `__init__.py`; a file in no package has
    its own directory as the root (a script's siblings are importable by bare name).
    """
    roots: dict[str, str] = {}
    for path in files:
        if not path.endswith(".py"):
            continue
        directory = posixpath.dirname(path)
        root = directory
        while root and posixpath.join(root, "__init__.py") in files:
            root = posixpath.dirname(root)
        roots[path] = root
    return roots


def _py_module_file(module: str, root: str, files: set[str]) -> str | None:
    """File for dotted `module` under `root`: `m.py`, else the package's `__init__.py`."""
    base = posixpath.join(root, *module.split(".")) if module else root
    for candidate in (base + ".py", posixpath.join(base, "__init__.py")):
        if candidate in files:
            return candidate
    return None


def _py_edges(path: str, source: str, files: set[str], root_of: dict[str, str]) -> set[str]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # the scanned file's own SyntaxWarnings are not ours
            tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()

    own_root = root_of.get(path, "")
    search_roots = [own_root, *(r for r in _FALLBACK_ROOTS if r != own_root)]
    package_dir = posixpath.dirname(path)
    edges: set[str] = set()

    def resolve_absolute(module: str) -> str | None:
        for root in search_roots:
            found = _py_module_file(module, root, files)
            if found:
                return found
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = resolve_absolute(alias.name)
                if target:
                    edges.add(target)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_dir = package_dir
                for _ in range(node.level - 1):
                    base_dir = posixpath.dirname(base_dir)
                module_path = posixpath.join(base_dir, *node.module.split(".")) if node.module else base_dir
                target = None
                for candidate in (module_path + ".py", posixpath.join(module_path, "__init__.py")):
                    if candidate in files:
                        target = candidate
                        break
                submodule_dir = module_path
            else:
                target = resolve_absolute(node.module or "")
                submodule_dir = None
            if target:
                edges.add(target)
            for alias in node.names:
                # `from pkg import sub` may import a submodule file rather than a name.
                if alias.name == "*":
                    continue
                if node.level:
                    sub = _py_module_file(alias.name, submodule_dir or "", files)
                else:
                    sub = resolve_absolute(f"{node.module}.{alias.name}") if node.module else None
                if sub:
                    edges.add(sub)
    edges.discard(path)
    return edges


def _js_resolve(specifier: str, importer: str, files: set[str]) -> str | None:
    if not specifier.startswith("."):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), specifier))
    if base.startswith(".."):
        return None
    stem, ext = posixpath.splitext(base)
    candidates = [base] if ext in _JS_EXTENSIONS else []
    if ext in (".js", ".jsx"):  # TS sources are imported with a .js specifier
        candidates += [stem + ".ts", stem + ".tsx"]
    candidates += [base + e for e in _JS_EXTENSIONS]
    candidates += [posixpath.join(base, "index" + e) for e in _JS_EXTENSIONS]
    for candidate in candidates:
        if candidate in files:
            return candidate
    return None


def _js_edges(path: str, source: str, files: set[str]) -> set[str]:
    edges = {t for m in _JS_IMPORT_RE.finditer(source) if (t := _js_resolve(m.group(1), path, files))}
    edges.discard(path)
    return edges


def resolve_imports(sources: Mapping[str, str]) -> dict[str, set[str]]:
    """Import graph for `sources` (repo-relative path -> file text).

    Every key appears in the result; its value is the set of other keys it imports.
    Imports of anything not in `sources` (stdlib, third-party, missing files) are dropped.
    """
    files = set(sources)
    root_of = _python_roots(files)
    graph: dict[str, set[str]] = {}
    for path, text in sources.items():
        if path.endswith(".py"):
            graph[path] = _py_edges(path, text, files, root_of)
        else:
            graph[path] = _js_edges(path, text, files)
    return graph


def fan_in_from_graph(graph: Mapping[str, set[str]]) -> dict[str, int]:
    """How many other files import each file."""
    fan_in = {path: 0 for path in graph}
    for targets in graph.values():
        for target in targets:
            if target in fan_in:
                fan_in[target] += 1
    return fan_in
