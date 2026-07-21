"""Architectural-debt report: import cycles, god files, layering violations.

README.md "Planned analyzers" item 4 / PROJECT-GENESIS.md section 9 Tier 4 item 31.
hotspots.py finds files that are risky because of their own history (churn x
complexity); maintenance_cost.py adds size and blast-radius (fan-in). Neither looks at
the SHAPE of the dependency graph itself. This module does: it builds a same-repo
import graph (reusing maintenance_cost.py's name-matching heuristic, not a real import
resolver) and reports three independent, well-documented signals over that one graph -
cycles, god files, and (optionally) layering violations.

Reuses maintenance_cost.extract_referenced_names (import parsing, Python and JS/TS) and
count_lines/compute_fan_in directly rather than re-implementing them, and follows
duplicates.py's/maintenance_cost.py's file-walking shape (`_iter_source_files`,
`_SKIP_DIR_NAMES`) for source discovery. No git, no subprocess anywhere in this module -
none of the three signals need churn, only the import graph and file size.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from autocto.maintenance_cost import compute_fan_in, count_lines, extract_referenced_names

DEFAULT_EXTENSIONS = frozenset({".py", ".js", ".ts", ".jsx", ".tsx"})
_SKIP_DIR_NAMES = frozenset({".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"})

# God-file thresholds. Reasoned from maintenance_cost.py's own captured README demo
# against `recall` (its most realistic multi-file sample): sizes there run
# App.jsx=772, main.py=461, benchmark.py=309, memory.py=262, live.py=125 lines - a
# threshold of 250 lines picks out the top half of that real sample (the files a
# reviewer would call "big") without also flagging every small utility module.
# fan_in maxes out at 1 in that same demo, because name-matching fan-in is a
# deliberate undercount (see maintenance_cost.compute_fan_in's docstring); fan_out
# (this module's own signal, not shown in that demo) is typically higher since most
# files import more things than they are imported by. A combined "fan_in + fan_out
# >= 4" bar means a file needs real, multi-edge connectivity on top of size before
# it is flagged - big-but-isolated (a data file, a leaf script) and
# small-but-connected (a two-line re-export) files are both excluded on purpose,
# only their intersection is a "god file".
DEFAULT_SIZE_THRESHOLD = 250
DEFAULT_CONNECTIONS_THRESHOLD = 4


def build_import_graph(imports_by_file: dict[str, set[str]]) -> dict[str, set[str]]:
    """Resolve each file's referenced names to real in-repo files, same-repo edges only.

    Uses the exact stem-matching approach maintenance_cost.compute_fan_in already uses
    (`src/x/hotspots.py` and `src/x/hotspots.ts` both answer to the referenced name
    "hotspots") so the two modules' notions of "this file is used by that file" stay
    consistent. A referenced name that matches more than one file's stem gets an edge
    to every match (same over-count risk compute_fan_in documents - a known trade-off
    of name-matching instead of real import resolution). Self-edges are excluded: a
    file importing its own stem (rare, but possible via a package `__init__` re-export
    pattern) is not a dependency on itself. Every file passed in appears as a key in
    the returned graph, even with an empty edge set, so downstream callers never need
    a `.get(path, set())` guard.
    """
    stem_to_paths: dict[str, list[str]] = defaultdict(list)
    for path in imports_by_file:
        stem_to_paths[Path(path).stem].append(path)

    graph: dict[str, set[str]] = {path: set() for path in imports_by_file}
    for path, names in imports_by_file.items():
        for name in names:
            for target_path in stem_to_paths.get(name, ()):
                if target_path != path:
                    graph[path].add(target_path)
    return graph


def find_cycles(import_graph: dict[str, set[str]]) -> list[list[str]]:
    """Group files into cyclic-import clusters via Tarjan strongly-connected components.

    Chose SCC decomposition over enumerating every elementary cycle: a file caught in
    a cyclic-import cluster is almost always part of exactly one group that matters
    for refactoring (you break the cluster, not one particular walk through it), and
    elementary-cycle enumeration is worst-case exponential in cluster size while SCC
    decomposition is linear in nodes and edges - the right trade-off for a
    general-purpose scanner run against a repo it has never seen before. Every
    strongly-connected component of size > 1 is reported as one cycle group. A
    component of size 1 (no cycle, or a self-loop, though `build_import_graph` never
    emits self-edges) is not reported. Implemented iteratively (an explicit work
    stack, not recursion) so it cannot blow Python's recursion limit on a large repo's
    import graph. Deterministic output: each cycle's file list is sorted, and cycles
    are sorted by their first file.
    """
    counter = 0
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    tarjan_stack: list[str] = []
    result: list[list[str]] = []

    for start in sorted(import_graph):
        if start in index:
            continue

        # Each work-stack frame is (node, sorted neighbors, next neighbor index) -
        # an explicit stand-in for a recursive strongconnect(node) call.
        work: list[tuple[str, list[str], int]] = [(start, sorted(import_graph.get(start, ())), 0)]
        index[start] = counter
        lowlink[start] = counter
        counter += 1
        tarjan_stack.append(start)
        on_stack[start] = True

        while work:
            node, neighbors, i = work[-1]
            if i < len(neighbors):
                work[-1] = (node, neighbors, i + 1)
                neighbor = neighbors[i]
                if neighbor not in index:
                    index[neighbor] = counter
                    lowlink[neighbor] = counter
                    counter += 1
                    tarjan_stack.append(neighbor)
                    on_stack[neighbor] = True
                    work.append((neighbor, sorted(import_graph.get(neighbor, ())), 0))
                elif on_stack.get(neighbor, False):
                    lowlink[node] = min(lowlink[node], index[neighbor])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                if lowlink[node] == index[node]:
                    component: list[str] = []
                    while True:
                        member = tarjan_stack.pop()
                        on_stack[member] = False
                        component.append(member)
                        if member == node:
                            break
                    if len(component) > 1:
                        result.append(sorted(component))

    result.sort(key=lambda cycle: cycle[0])
    return result


@dataclass(frozen=True)
class GodFile:
    path: str
    size: int
    fan_in: int
    fan_out: int


def find_god_files(
    size: dict[str, int],
    fan_in: dict[str, int],
    fan_out: dict[str, int],
    *,
    size_threshold: int = DEFAULT_SIZE_THRESHOLD,
    connections_threshold: int = DEFAULT_CONNECTIONS_THRESHOLD,
) -> list[GodFile]:
    """Flag files that are simultaneously large AND highly-connected.

    Size alone just means "long file"; connectivity alone just means "popular
    module" - neither is dangerous by itself. It is the combination that makes a
    file disproportionately risky to touch: a big file few others depend on is
    tedious but contained, and a tiny, heavily-used file (a constants module) is
    easy to reason about even though many files touch it. A file must clear BOTH
    `size_threshold` (line count) AND `connections_threshold` (fan_in + fan_out) to
    be flagged - see the module-level defaults above for how those numbers were
    picked. Only files present in all three maps are considered, matching the other
    analyzers' "can't score what we don't have data for" rule. Ranked descending by
    `size * (fan_in + fan_out)` - the same "bigger blast radius on a bigger file
    ranks higher" idea as maintenance_cost.estimate_costs - ties break on path for a
    deterministic order.
    """
    paths = size.keys() & fan_in.keys() & fan_out.keys()
    god_files = [
        GodFile(p, size[p], fan_in[p], fan_out[p])
        for p in paths
        if size[p] >= size_threshold and (fan_in[p] + fan_out[p]) >= connections_threshold
    ]
    god_files.sort(key=lambda g: (-(g.size * (g.fan_in + g.fan_out)), g.path))
    return god_files


@dataclass(frozen=True)
class LayeringViolation:
    importer: str
    importee: str
    importer_layer: str
    importee_layer: str


def find_layering_violations(
    import_graph: dict[str, set[str]],
    layer_order: Sequence[str] | None = None,
) -> list[LayeringViolation]:
    """Flag imports that reach from a foundational layer up into a higher one.

    There is no universal layer ordering across arbitrary repos - PROJECT-GENESIS.md's
    own item text just says "layering violations" with no further spec, and this
    repo's README/docs have no prior art to lean on either. Rather than fabricate a
    default (e.g. guessing "models before views before controllers"), this function
    only checks layering when the CALLER supplies `layer_order`: an ordered sequence
    of top-level directory/package name prefixes, most-foundational first (e.g.
    `["router", "memory", "rag", "interfaces"]` means `router` must never import from
    `interfaces`). A file's layer is its first path component (`Path(path).parts[0]`);
    a file whose top-level directory is not in `layer_order` is excluded from the
    check entirely - it isn't that its layer is unknown-and-violating, it's simply
    outside the scope of what the caller told us to check. A violation is any import
    edge where the importer's index in `layer_order` is LOWER than the importee's
    (a more-foundational module reaching up into a less-foundational one - the
    classic layering-violation direction: the dependency arrow should only ever point
    down the list, never up). If `layer_order` is None (the default), this returns
    `[]` - the same "we don't invent data we don't have" discipline
    hotspots.py/maintenance_cost.py already apply to churn and fan-in. Deterministic
    output: sorted by (importer, importee).
    """
    if not layer_order:
        return []

    layer_index = {name: i for i, name in enumerate(layer_order)}

    def layer_of(path: str) -> str | None:
        parts = Path(path).parts
        if not parts:
            return None
        top = parts[0]
        return top if top in layer_index else None

    violations: list[LayeringViolation] = []
    for importer, importees in import_graph.items():
        importer_layer = layer_of(importer)
        if importer_layer is None:
            continue
        for importee in importees:
            importee_layer = layer_of(importee)
            if importee_layer is None:
                continue
            if layer_index[importer_layer] < layer_index[importee_layer]:
                violations.append(LayeringViolation(importer, importee, importer_layer, importee_layer))

    violations.sort(key=lambda v: (v.importer, v.importee))
    return violations


@dataclass(frozen=True)
class ArchitecturalDebtReport:
    cycles: list[list[str]]
    god_files: list[GodFile]
    layering_violations: list[LayeringViolation]


def _iter_source_files(repo_dir: Path, extensions: frozenset[str]):
    for path in repo_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if _SKIP_DIR_NAMES & set(path.relative_to(repo_dir).parts[:-1]):
            continue
        yield path


def analyze_repo(
    repo_dir: Path,
    *,
    extensions: frozenset[str] = DEFAULT_EXTENSIONS,
    layer_order: Sequence[str] | None = None,
    size_threshold: int = DEFAULT_SIZE_THRESHOLD,
    connections_threshold: int = DEFAULT_CONNECTIONS_THRESHOLD,
) -> ArchitecturalDebtReport:
    """Build a real repo's same-repo import graph once, run all three debt signals over it.

    Only files under `extensions` are walked (skipping the same non-source
    directories as duplicates.py/maintenance_cost.py: `.git`, `node_modules`,
    `venv`/`.venv`, `__pycache__`, `dist`, `build`). No git, no subprocess - unlike
    hotspots.py/maintenance_cost.py this analyzer needs no churn, so there is nothing
    to inject and no `git_log_fn`-style seam. `layer_order` is forwarded straight to
    `find_layering_violations` and defaults to None (layering check skipped - see that
    function's docstring for why this repo refuses to guess a default ordering).
    """
    repo_dir = Path(repo_dir)
    size: dict[str, int] = {}
    imports_by_file: dict[str, set[str]] = {}
    for path in _iter_source_files(repo_dir, extensions):
        rel = str(path.relative_to(repo_dir))
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        size[rel] = count_lines(content)
        imports_by_file[rel] = extract_referenced_names(content)

    import_graph = build_import_graph(imports_by_file)
    fan_in = compute_fan_in(imports_by_file)
    fan_out = {path: len(targets) for path, targets in import_graph.items()}

    cycles = find_cycles(import_graph)
    god_files = find_god_files(
        size,
        fan_in,
        fan_out,
        size_threshold=size_threshold,
        connections_threshold=connections_threshold,
    )
    layering_violations = find_layering_violations(import_graph, layer_order)

    return ArchitecturalDebtReport(cycles=cycles, god_files=god_files, layering_violations=layering_violations)
