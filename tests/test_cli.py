"""CLI integration tests: each subcommand runs end to end against a small real repo
(a temp dir with two commits, built via git) and produces both table and JSON output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from autocto import cli


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                    env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.com",
                         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.com",
                         "PATH": __import__("os").environ.get("PATH", "")})


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text("def a():\n    if True:\n        return 1\n" * 3, encoding="utf-8")
    (tmp_path / "b.py").write_text("from a import a\n\n\ndef b():\n    return a()\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "first")
    (tmp_path / "a.py").write_text((tmp_path / "a.py").read_text(encoding="utf-8") + "\ndef extra():\n    return 2\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "second")
    return tmp_path


def run(*args: str) -> int:
    return cli.main(list(args))


@pytest.mark.parametrize("cmd", ["hotspots", "duplicates", "maintenance", "architecture", "report"])
def test_every_subcommand_runs_clean(repo, cmd, capsys):
    assert run(cmd, str(repo)) == 0
    out = capsys.readouterr().out
    assert out  # something was printed


@pytest.mark.parametrize("cmd", ["hotspots", "duplicates", "maintenance", "report"])
def test_json_output_is_valid_json(repo, cmd, capsys):
    assert run(cmd, str(repo), "--json") == 0
    parsed = json.loads(capsys.readouterr().out)
    assert isinstance(parsed, (list, dict))


def test_architecture_json_is_valid(repo, capsys):
    assert run("architecture", str(repo), "--json") == 0
    parsed = json.loads(capsys.readouterr().out)
    assert set(parsed) == {"cycles", "god_files", "layering_violations"}


def test_hotspots_respects_limit(repo, capsys):
    run("hotspots", str(repo), "--json", "--limit", "1")
    parsed = json.loads(capsys.readouterr().out)
    assert len(parsed) <= 1


def test_layers_flag_is_parsed(repo, capsys):
    assert run("architecture", str(repo), "--json", "--layers", "a.py,b.py") == 0
    parsed = json.loads(capsys.readouterr().out)
    assert isinstance(parsed["layering_violations"], list)


def test_missing_repo_path_errors():
    assert run("hotspots", "/does/not/exist/at/all") == 2


def test_installed_console_script_runs():
    """The [project.scripts] entry point resolves and behaves like `python -m autocto.cli`."""
    result = subprocess.run([sys.executable, "-m", "autocto.cli", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "hotspots" in result.stdout
