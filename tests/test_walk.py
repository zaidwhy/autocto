"""Which directories a source walk skips."""

from __future__ import annotations

from pathlib import Path

import pytest

from autocto import architectural_debt, duplicates, maintenance_cost
from autocto.walk import is_skipped_dir


@pytest.mark.parametrize("name", [
    "venv", ".venv", "venv3", ".venv312", "venv-3.14", ".venv_old", "venv.bak",
    "node_modules", "__pycache__", "site-packages", ".git", ".tox", "dist", "build",
])
def test_skipped(name):
    assert is_skipped_dir(name)


@pytest.mark.parametrize("name", ["venues", "venvironment", "src", "environment", "env", "lib", "ventures"])
def test_not_skipped(name):
    assert not is_skipped_dir(name)


def test_walkers_ignore_an_oddly_named_virtualenv(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    pkg = tmp_path / ".venv312" / "Lib" / "site-packages" / "dep"
    pkg.mkdir(parents=True)
    (pkg / "dep.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "venues").mkdir()
    (tmp_path / "venues" / "hall.py").write_text("z = 3\n", encoding="utf-8")

    ext = frozenset({".py"})
    for module in (duplicates, maintenance_cost, architectural_debt):
        found = {p.name for p in module._iter_source_files(tmp_path, ext)}
        assert found == {"app.py", "hall.py"}, module.__name__
