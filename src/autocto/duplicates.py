"""Duplicated-logic detector: token-shingle similarity across files.

README.md "Planned analyzers" item 2 / PROJECT-GENESIS.md section 9 Tier 2. Copy-pasted
logic (a function cloned into three files instead of extracted once) is a maintenance
risk hotspots.py can't see - two files can each be low-churn and low-complexity and
still be a duplication problem. This looks for it directly: tokenize each file, build a
set of overlapping k-token "shingles", and rank file pairs by Jaccard similarity of
their shingle sets.

Shingling (not embeddings) is deliberate: it needs no model, no vector store, and no
network - same "pure, dependency-free, offline-testable" bar as hotspots.py. It is also
whitespace/formatting-tolerant (renaming a variable shifts few shingles) but still
catches near-identical blocks, which a naive line-diff would miss on reformatted code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

DEFAULT_EXTENSIONS = frozenset({".py", ".js", ".ts", ".jsx", ".tsx"})
DEFAULT_SHINGLE_SIZE = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.6
_SKIP_DIR_NAMES = frozenset({".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"})

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?|\S")


def tokenize(content: str) -> list[str]:
    """Split source text into a flat token stream (identifiers/numbers/punctuation).

    Comments and string contents are not stripped - the goal is cheap, language-agnostic
    tokenization good enough to compare files, not a real lexer.
    """
    return _TOKEN_RE.findall(content)


def shingle(content: str, k: int = DEFAULT_SHINGLE_SIZE) -> set[str]:
    """Build the set of overlapping k-token shingles ("windows") from source text.

    Each shingle is k consecutive tokens joined by a single space, so two files share a
    shingle only if they contain the same k-token sequence verbatim. Files shorter than
    k tokens produce an empty set (too little content to compare meaningfully).
    """
    tokens = tokenize(content)
    if len(tokens) < k:
        return set()
    return {" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)}


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two shingle sets: |intersection| / |union|, 0.0 if both empty."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


@dataclass(frozen=True)
class DuplicatePair:
    path_a: str
    path_b: str
    similarity: float


def find_duplicates(
    file_shingles: dict[str, set[str]],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[DuplicatePair]:
    """Rank every file pair by shingle-set Jaccard similarity, keeping only pairs at or
    above `threshold`. Highest similarity first; ties break on (path_a, path_b) for a
    deterministic order regardless of dict iteration order.
    """
    pairs = []
    for path_a, path_b in combinations(sorted(file_shingles), 2):
        similarity = jaccard_similarity(file_shingles[path_a], file_shingles[path_b])
        if similarity >= threshold:
            pairs.append(DuplicatePair(path_a, path_b, similarity))
    pairs.sort(key=lambda p: (-p.similarity, p.path_a, p.path_b))
    return pairs


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
    shingle_size: int = DEFAULT_SHINGLE_SIZE,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[DuplicatePair]:
    """Rank a real repo's source files by pairwise duplication risk.

    Walks `repo_dir` for files under `extensions` (skipping common non-source
    directories: `.git`, `node_modules`, `venv`/`.venv`, `__pycache__`, `dist`,
    `build`), shingles each one, and returns `find_duplicates` over the result. Paths
    in the returned pairs are relative to `repo_dir` for stable, portable output.
    """
    repo_dir = Path(repo_dir)
    file_shingles: dict[str, set[str]] = {}
    for path in _iter_source_files(repo_dir, extensions):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        file_shingles[str(path.relative_to(repo_dir))] = shingle(content, k=shingle_size)
    return find_duplicates(file_shingles, threshold=threshold)
