"""Maintenance-cost estimator: size x churn x dependency fan-in, documented formula.

README.md "Planned analyzers" item 3 / PROJECT-GENESIS.md section 9 Tier 4 item 30.
hotspots.py already combines churn (how often a file changes) with complexity (how
gnarly it reads). This adds a third, independent maintenance signal - dependency
fan-in: how many OTHER files in the repo reference this one. A file nobody depends on
is safe to change quickly; a file five other files import is a blast-radius risk every
time it changes, regardless of its own complexity. Fan-in is resolved by a name-matching
heuristic (import statements -> referenced module/file stems), not a real import graph -
same "dependency-free, good-enough proxy" bar as hotspots.complexity_score.

Reuses hotspots.parse_numstat_log/GitLogFn for churn (same git-log-text fixture works
for both analyzers) and duplicates.py's file-walking shape for source discovery.
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from autocto.hotspots import GitLogFn, parse_numstat_log

DEFAULT_EXTENSIONS = frozenset({".py", ".js", ".ts", ".jsx", ".tsx"})
_SKIP_DIR_NAMES = frozenset({".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"})

# Python: `from a.b.c import x` or `import a.b.c` - captures the dotted module path.
_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import\b|import\s+([.\w]+))", re.MULTILINE)
# JS/TS: `import ... from '<path>'` or `require('<path>')` - captures the string literal.
_JS_IMPORT_RE = re.compile(r"""(?:\bimport\b[^'"\n]*\bfrom\s*|\brequire\s*\(\s*)['"]([^'"]+)['"]""")
_JS_EXTENSION_RE = re.compile(r"\.(js|jsx|ts|tsx)$")


def count_lines(content: str) -> int:
    """Total line count - the crudest, most language-agnostic size proxy there is."""
    if not content:
        return 0
    return len(content.splitlines())


def extract_referenced_names(content: str) -> set[str]:
    """Bare module/file names this file's import statements reference.

    A heuristic, not a real import resolver: for Python it takes the LAST dotted
    segment of every `import X`/`from X import ...` statement (`from autocto.hotspots
    import analyze_repo` -> `hotspots`); for JS/TS it takes the last path segment
    (extension stripped) of every `import ... from '...'`/`require('...')` call
    (`import x from '../hotspots'` -> `hotspots`). Style-agnostic on purpose so one
    scan covers both this repo and the JS/TS repos in the ecosystem.
    """
    names: set[str] = set()
    for match in _PY_IMPORT_RE.finditer(content):
        module = (match.group(1) or match.group(2) or "").strip(".")
        if module:
            names.add(module.rsplit(".", 1)[-1])
    for match in _JS_IMPORT_RE.finditer(content):
        raw_path = match.group(1).rstrip("/")
        segment = raw_path.rsplit("/", 1)[-1]
        segment = _JS_EXTENSION_RE.sub("", segment)
        if segment and segment != ".":
            names.add(segment)
    return names


def compute_fan_in(imports_by_file: dict[str, set[str]]) -> dict[str, int]:
    """For every file, how many OTHER files reference it by module/stem name.

    Matches referenced names against each file's path stem (`src/x/hotspots.py` and
    `src/x/hotspots.ts` both answer to `hotspots`). If two unrelated files share a
    stem, both get credit for any match - a known over-count risk of name-matching
    instead of real import resolution, acceptable for a same-repo relative ranking.
    """
    stem_to_paths: dict[str, list[str]] = defaultdict(list)
    for path in imports_by_file:
        stem_to_paths[Path(path).stem].append(path)

    fan_in: dict[str, int] = {path: 0 for path in imports_by_file}
    for path, names in imports_by_file.items():
        for name in names:
            for target_path in stem_to_paths.get(name, ()):
                if target_path != path:
                    fan_in[target_path] += 1
    return fan_in


@dataclass(frozen=True)
class MaintenanceCost:
    path: str
    size: int
    churn: int
    fan_in: int
    cost: int


def estimate_costs(
    size: dict[str, int], churn: dict[str, int], fan_in: dict[str, int]
) -> list[MaintenanceCost]:
    """cost = size x churn x (1 + fan_in), for every file present in all three maps.

    Documented formula: size and churn are the same "how much code, how often
    touched" signals hotspots.py already scores; fan_in adds blast-radius as a
    THIRD, independent axis. It multiplies as `(1 + fan_in)` rather than bare
    `fan_in` deliberately - a file with zero dependents (fan_in=0) still costs to
    maintain based on its own size x churn; fan_in should scale that baseline up,
    never zero it out. Ties break on path for a deterministic order.
    """
    paths = size.keys() & churn.keys() & fan_in.keys()
    costs = [
        MaintenanceCost(p, size[p], churn[p], fan_in[p], size[p] * churn[p] * (1 + fan_in[p]))
        for p in paths
    ]
    costs.sort(key=lambda c: (-c.cost, c.path))
    return costs


def _iter_source_files(repo_dir: Path, extensions: frozenset[str]):
    for path in repo_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if _SKIP_DIR_NAMES & set(path.relative_to(repo_dir).parts[:-1]):
            continue
        yield path


def _run_git_numstat_log(repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", "log", "--numstat", "--pretty=format:%H"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def analyze_repo(
    repo_dir: Path,
    *,
    extensions: frozenset[str] = DEFAULT_EXTENSIONS,
    git_log_fn: GitLogFn = _run_git_numstat_log,
) -> list[MaintenanceCost]:
    """Rank a real repo's tracked files by size x churn x dependency fan-in.

    Only files under `extensions` that still exist on disk are sized/scanned for
    imports (same "can't score what's gone" rule as hotspots.analyze_repo); churn
    comes from `git_log_fn`'s numstat text, defaulting to a real `git log` call but
    injectable with a fixture in tests.
    """
    repo_dir = Path(repo_dir)
    churn = parse_numstat_log(git_log_fn(repo_dir))
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
    fan_in = compute_fan_in(imports_by_file)
    return estimate_costs(size, churn, fan_in)
