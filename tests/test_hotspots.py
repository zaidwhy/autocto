"""Bug-hotspot analyzer: numstat parsing, complexity proxy, ranking, real-repo wiring."""

from __future__ import annotations

import subprocess
from pathlib import Path

from autocto.hotspots import (
    Hotspot,
    analyze_repo,
    complexity_score,
    compute_hotspots,
    parse_numstat_log,
)


def test_parse_numstat_log_counts_commits_per_file():
    log_text = (
        "c81b484a0ff4e39e198a410b2833a363a801362e\n"
        "1\t0\tb.py\n"
        "1\t0\tc.py\n"
        "\n"
        "6467aba25e3f846dfb0c808c8832da6fcacc822b\n"
        "1\t0\ta.py\n"
        "\n"
        "4ecdced762d21c84f4ae676a71ac451b4d7ff6af\n"
        "1\t0\ta.py\n"
        "1\t0\tb.py\n"
    )
    churn = parse_numstat_log(log_text)
    assert churn == {"a.py": 2, "b.py": 2, "c.py": 1}


def test_parse_numstat_log_handles_missing_trailing_blank_line():
    # Real `git log` output has no trailing blank line after the last commit's stats.
    log_text = "abc1234\n1\t0\tonly.py"
    assert parse_numstat_log(log_text) == {"only.py": 1}


def test_parse_numstat_log_counts_binary_file_touches():
    log_text = "abc1234\n-\t-\timage.png\n"
    assert parse_numstat_log(log_text) == {"image.png": 1}


def test_parse_numstat_log_commit_touching_nothing():
    log_text = "abc1234\n\ndef5678\n1\t0\tonly.py\n"
    assert parse_numstat_log(log_text) == {"only.py": 1}


def test_parse_numstat_log_empty_input():
    assert parse_numstat_log("") == {}


def test_complexity_score_baseline_is_one_for_plain_content():
    assert complexity_score("x = 1\ny = 2\n") == 1


def test_complexity_score_counts_branch_keywords():
    content = "if x:\n    pass\nelif y:\n    pass\nelse:\n    pass\nfor i in z:\n    pass\n"
    assert complexity_score(content) == 1 + 4


def test_complexity_score_counts_logical_operators():
    assert complexity_score("if a && b || c:\n    pass\n") == 1 + 1 + 2


def test_compute_hotspots_ranks_by_churn_times_complexity():
    churn = {"hot.py": 10, "cold.py": 10}
    complexity = {"hot.py": 5, "cold.py": 1}
    hotspots = compute_hotspots(churn, complexity)
    assert hotspots[0] == Hotspot("hot.py", 10, 5, 50)
    assert hotspots[1] == Hotspot("cold.py", 10, 1, 10)


def test_compute_hotspots_ties_break_on_path():
    churn = {"b.py": 2, "a.py": 2}
    complexity = {"b.py": 3, "a.py": 3}
    hotspots = compute_hotspots(churn, complexity)
    assert [h.path for h in hotspots] == ["a.py", "b.py"]


def test_compute_hotspots_excludes_files_missing_complexity():
    churn = {"scored.py": 3, "unscored.png": 9}
    complexity = {"scored.py": 2}
    hotspots = compute_hotspots(churn, complexity)
    assert [h.path for h in hotspots] == ["scored.py"]


def test_compute_hotspots_empty_input():
    assert compute_hotspots({}, {}) == []


def _run(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_analyze_repo_end_to_end_against_a_real_git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q")
    _run(repo, "config", "user.email", "a@a.com")
    _run(repo, "config", "user.name", "a")

    hot = repo / "hot.py"
    cold = repo / "cold.py"
    hot.write_text("if a:\n    pass\nelif b:\n    pass\n", encoding="utf-8")
    cold.write_text("x = 1\n", encoding="utf-8")
    _run(repo, "add", ".")
    _run(repo, "commit", "-q", "-m", "first")

    hot.write_text("if a:\n    pass\nelif b:\n    pass\nelse:\n    pass\n", encoding="utf-8")
    _run(repo, "add", ".")
    _run(repo, "commit", "-q", "-m", "second")

    hotspots = analyze_repo(repo)
    assert [h.path for h in hotspots] == ["hot.py", "cold.py"]
    assert hotspots[0].churn == 2
    assert hotspots[1].churn == 1


def test_analyze_repo_ignores_extensions_outside_the_default_set(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q")
    _run(repo, "config", "user.email", "a@a.com")
    _run(repo, "config", "user.name", "a")

    (repo / "notes.md").write_text("# hello\n", encoding="utf-8")
    _run(repo, "add", ".")
    _run(repo, "commit", "-q", "-m", "first")

    assert analyze_repo(repo) == []


def test_analyze_repo_accepts_an_injected_git_log_fn(tmp_path):
    # No real git invocation at all - proves analyze_repo's only effectful seam is
    # `git_log_fn`, so callers (or tests) never need a real git subprocess.
    (tmp_path / "foo.py").write_text("if a:\n    pass\n", encoding="utf-8")
    calls = []

    def fake_git_log_fn(repo_dir: Path) -> str:
        calls.append(repo_dir)
        return "abc1234\n1\t0\tfoo.py\n"

    hotspots = analyze_repo(tmp_path, git_log_fn=fake_git_log_fn)
    assert calls == [tmp_path]
    assert hotspots == [Hotspot("foo.py", 1, 2, 2)]
