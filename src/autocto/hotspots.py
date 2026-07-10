"""Bug-hotspot analyzer: churn x complexity over `git log`.

README.md "Planned analyzers" item 1 / PROJECT-GENESIS.md section 9 Tier 2: the files
that change often AND are complex are where bugs cluster (the core finding behind
Tornhill's "Your Code as a Crime Scene"). Churn is commit frequency, not line count - a
file touched in 40 small commits is riskier than one touched twice with a big diff.
Complexity is a dependency-free proxy (branch keyword/operator density), not a real
per-language AST-based cyclomatic-complexity parser.

The parsing and scoring functions are pure text/data in, data out - no filesystem, no
subprocess - so they're fully offline-testable with fixture strings. `analyze_repo` is
the one effectful entry point, and it takes `git_log_fn` as an injectable callable (same
DI pattern as second_brain.vault.ingest_vault's `ingest_fn`) so tests can supply a real
git repo fixture without mocking subprocess internals.
"""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_EXTENSIONS = frozenset({".py", ".js", ".ts", ".jsx", ".tsx"})

_COMMIT_HASH_RE = re.compile(r"^[0-9a-f]{7,40}$")
_BRANCH_KEYWORD_RE = re.compile(r"\b(if|elif|else|for|while|case|catch|except|switch)\b")


def parse_numstat_log(log_text: str) -> dict[str, int]:
    """Count commits touching each file from `git log --numstat --pretty=format:%H` text.

    Each commit block is a hash line followed by zero or more "<added>\\t<deleted>\\t<path>"
    lines, blocks separated by a blank line. A file gets +1 per commit it appears in,
    regardless of how many lines changed - churn here means change *frequency*.
    """
    churn: dict[str, int] = defaultdict(int)
    current_files: set[str] = set()

    def flush() -> None:
        for path in current_files:
            churn[path] += 1
        current_files.clear()

    for raw_line in log_text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        parts = raw_line.split("\t")
        if len(parts) == 3:
            current_files.add(parts[2])
        elif _COMMIT_HASH_RE.match(line):
            flush()
    flush()
    return dict(churn)


def complexity_score(content: str) -> int:
    """Cheap complexity proxy: 1 (baseline) + branch keyword/operator occurrences.

    Counts branching constructs common to Python/JS/TS-like syntax (if/elif/else/for/
    while/case/catch/except/switch, &&, ||) as a stand-in for "how many paths does a
    reader have to hold in their head". Not a real cyclomatic-complexity parser - no
    per-language AST - but dependency-free and good enough to rank files relative to
    each other within one repo.
    """
    keyword_hits = len(_BRANCH_KEYWORD_RE.findall(content))
    operator_hits = content.count("&&") + content.count("||")
    return 1 + keyword_hits + operator_hits


@dataclass(frozen=True)
class Hotspot:
    path: str
    churn: int
    complexity: int
    score: int


def compute_hotspots(churn: dict[str, int], complexity: dict[str, int]) -> list[Hotspot]:
    """Rank files by churn x complexity, highest risk first.

    Only files present in both maps are scored - a file with churn but no known
    complexity (deleted, binary, outside the scanned extensions) can't be scored
    honestly. Ties break on path for a deterministic order.
    """
    hotspots = [
        Hotspot(path, churn[path], complexity[path], churn[path] * complexity[path])
        for path in churn.keys() & complexity.keys()
    ]
    hotspots.sort(key=lambda h: (-h.score, h.path))
    return hotspots


GitLogFn = Callable[[Path], str]


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
) -> list[Hotspot]:
    """Rank a real repo's tracked files by churn x complexity.

    `git_log_fn` defaults to a real `git log --numstat` subprocess call but can be
    injected with a fixture in tests. Files outside `extensions`, or that no longer
    exist on disk (deleted since their last commit), are excluded from complexity
    scoring and therefore from the ranking.
    """
    repo_dir = Path(repo_dir)
    churn = parse_numstat_log(git_log_fn(repo_dir))
    complexity: dict[str, int] = {}
    for path in churn:
        full_path = repo_dir / path
        if full_path.suffix.lower() not in extensions or not full_path.is_file():
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        complexity[path] = complexity_score(content)
    return compute_hotspots(churn, complexity)
