"""Shared rule for which directories a source walk skips.

duplicates, maintenance and architecture all walk the working tree. They used to share a
fixed set of names (`venv`, `.venv`, ...), so a virtual environment with any other name
(`.venv312`, `venv-3.14`, `env_old`) was walked and its site-packages polluted every result.
"""

from __future__ import annotations

import re
from pathlib import Path

SKIP_DIR_NAMES = frozenset({
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    "site-packages", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
})

# venv, .venv, venv3, .venv312, venv-3.14, .venv_old: a name that starts with "venv" or ".venv"
# followed by nothing or a digit, dot, dash or underscore. "venues" and "venvironment" stay walked.
_VENV_NAME = re.compile(r"^\.?venv([0-9._-].*)?$")


def is_skipped_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or bool(_VENV_NAME.match(name))


def is_skipped_path(repo_dir: Path, path: Path) -> bool:
    """True when any directory between repo_dir and the file is skipped."""
    return any(is_skipped_dir(part) for part in path.relative_to(repo_dir).parts[:-1])
