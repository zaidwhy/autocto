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


@pytest.mark.parametrize("cmd", ["hotspots", "maintenance", "report"])
def test_non_git_folder_errors_cleanly(tmp_path, cmd, capsys):
    """The git-history analyzers print one error line instead of a CalledProcessError traceback."""
    (tmp_path / "a.py").write_text("x = 1\n")
    assert run(cmd, str(tmp_path)) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_installed_console_script_runs():
    """The [project.scripts] entry point resolves and behaves like `python -m autocto.cli`."""
    result = subprocess.run(
        [sys.executable, "-m", "autocto.cli", "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "hotspots" in result.stdout


def _proposal(tmp_path: Path, data) -> Path:
    path = tmp_path / "proposal.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


_GOOD_PROPOSAL = {
    "title": "Split engine",
    "rationale": "too big",
    "changes": [
        {"id": "B", "description": "move callers", "depends_on": ["A"], "risk": "medium"},
        {"id": "A", "description": "extract module", "files": ["engine.py"], "risk": "high"},
    ],
}


def test_plan_prints_markdown_in_dependency_order(tmp_path, capsys):
    assert run("plan", str(_proposal(tmp_path, _GOOD_PROPOSAL))) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Migration Plan: Split engine")
    assert out.index("### 1. A - extract module") < out.index("### 2. B - move callers")


def test_plan_json_lists_ordered_steps(tmp_path, capsys):
    assert run("plan", str(_proposal(tmp_path, _GOOD_PROPOSAL)), "--json") == 0
    plan = json.loads(capsys.readouterr().out)
    assert [s["change"]["id"] for s in plan["steps"]] == ["A", "B"]


@pytest.mark.parametrize(
    "bad, message",
    [
        ("not json", "not valid JSON"),
        ({"changes": []}, '"title"'),
        ({"title": "t", "changes": []}, "non-empty"),
        ({"title": "t", "changes": [{"id": "A", "description": "d", "risk": "extreme"}]}, "risk"),
        ({"title": "t", "changes": [{"id": "A", "description": "d"}, {"id": "A", "description": "d"}]}, "duplicate"),
        ({"title": "t", "changes": [{"id": "A", "description": "d", "depends_on": ["A"]}]}, "cycle"),
        ({"title": "t", "changes": [{"id": "A", "description": "d", "depends_on": ["Z"]}]}, "unknown id"),
    ],
)
def test_plan_rejects_a_bad_proposal_with_one_line_error(tmp_path, capsys, bad, message):
    assert run("plan", str(_proposal(tmp_path, bad))) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and message in err and "Traceback" not in err


def test_plan_missing_file_is_a_clean_error(tmp_path, capsys):
    assert run("plan", str(tmp_path / "nope.json")) == 2
    assert "does not exist" in capsys.readouterr().err


def _top(cmd: str, repo: Path, capsys, field: str) -> float:
    run(cmd, str(repo), "--json", "--limit", "1")
    return json.loads(capsys.readouterr().out)[0][field]


@pytest.mark.parametrize("cmd,field", [("hotspots", "score"), ("maintenance", "cost")])
def test_fail_over_exits_one_naming_the_file(repo, cmd, field, capsys):
    top = _top(cmd, repo, capsys, field)
    assert top > 0
    assert run(cmd, str(repo), "--fail-over", str(top - 1)) == 1
    err = capsys.readouterr().err
    assert "a.py" in err and field in err


@pytest.mark.parametrize("cmd,field", [("hotspots", "score"), ("maintenance", "cost")])
def test_fail_over_at_or_above_the_top_passes(repo, cmd, field, capsys):
    top = _top(cmd, repo, capsys, field)
    # the gate is strictly "above": a threshold equal to the worst file is not a failure
    assert run(cmd, str(repo), "--fail-over", str(top)) == 0
    assert capsys.readouterr().err == ""


def test_fail_over_checks_files_past_the_display_limit(repo, capsys):
    # b.py ranks below a.py; --limit 1 hides it, the gate must still see every file
    run("maintenance", str(repo), "--json")
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) >= 2
    second = sorted(r["cost"] for r in rows)[-2]
    assert run("maintenance", str(repo), "--limit", "1", "--fail-over", str(second - 1)) == 1
