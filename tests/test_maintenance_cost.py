"""Maintenance-cost estimator: size, fan-in name-matching, cost formula, real-repo wiring."""

from __future__ import annotations

from pathlib import Path

from autocto.maintenance_cost import (
    MaintenanceCost,
    analyze_repo,
    compute_fan_in,
    count_lines,
    estimate_costs,
    extract_referenced_names,
)


def test_count_lines_counts_all_lines():
    assert count_lines("a\nb\nc\n") == 3


def test_count_lines_handles_no_trailing_newline():
    assert count_lines("a\nb") == 2


def test_count_lines_empty_content():
    assert count_lines("") == 0


def test_extract_referenced_names_python_from_import():
    names = extract_referenced_names("from autocto.hotspots import analyze_repo\n")
    assert names == {"hotspots"}


def test_extract_referenced_names_python_plain_import():
    names = extract_referenced_names("import autocto.duplicates\n")
    assert names == {"duplicates"}


def test_extract_referenced_names_python_ignores_stdlib_single_name():
    # A bare `import re` still yields "re" - callers filter via fan-in matching
    # against real repo files, not this function.
    assert extract_referenced_names("import re\n") == {"re"}


def test_extract_referenced_names_js_import_from():
    names = extract_referenced_names("import { foo } from '../hotspots';\n")
    assert names == {"hotspots"}


def test_extract_referenced_names_js_require():
    names = extract_referenced_names("const foo = require('./utils/hotspots.js');\n")
    assert names == {"hotspots"}


def test_extract_referenced_names_no_imports():
    assert extract_referenced_names("x = 1\ny = 2\n") == set()


def test_compute_fan_in_counts_incoming_references():
    imports_by_file = {
        "a.py": {"hotspots"},
        "b.py": {"hotspots"},
        "hotspots.py": set(),
    }
    fan_in = compute_fan_in(imports_by_file)
    assert fan_in == {"a.py": 0, "b.py": 0, "hotspots.py": 2}


def test_compute_fan_in_self_reference_not_counted():
    imports_by_file = {"hotspots.py": {"hotspots"}}
    assert compute_fan_in(imports_by_file) == {"hotspots.py": 0}


def test_compute_fan_in_no_matching_file_is_zero():
    imports_by_file = {"a.py": {"nonexistent_module"}, "b.py": set()}
    fan_in = compute_fan_in(imports_by_file)
    assert fan_in == {"a.py": 0, "b.py": 0}


def test_estimate_costs_formula_is_size_times_churn_times_one_plus_fan_in():
    size = {"a.py": 10}
    churn = {"a.py": 3}
    fan_in = {"a.py": 2}
    costs = estimate_costs(size, churn, fan_in)
    assert costs == [MaintenanceCost("a.py", 10, 3, 2, 90)]


def test_estimate_costs_zero_fan_in_still_scores_size_times_churn():
    size = {"a.py": 10}
    churn = {"a.py": 3}
    fan_in = {"a.py": 0}
    costs = estimate_costs(size, churn, fan_in)
    assert costs[0].cost == 30


def test_estimate_costs_only_scores_files_in_all_three_maps():
    size = {"a.py": 10, "b.py": 5}
    churn = {"a.py": 3}
    fan_in = {"a.py": 1, "b.py": 1}
    costs = estimate_costs(size, churn, fan_in)
    assert [c.path for c in costs] == ["a.py"]


def test_estimate_costs_ranked_descending_ties_break_on_path():
    size = {"a.py": 10, "b.py": 10}
    churn = {"a.py": 2, "b.py": 2}
    fan_in = {"a.py": 0, "b.py": 0}
    costs = estimate_costs(size, churn, fan_in)
    assert [c.path for c in costs] == ["a.py", "b.py"]


def test_estimate_costs_empty_input():
    assert estimate_costs({}, {}, {}) == []


def test_analyze_repo_accepts_an_injected_git_log_fn(tmp_path):
    (tmp_path / "hotspots.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    (tmp_path / "user.py").write_text("from hotspots import x\n", encoding="utf-8")

    def fake_git_log_fn(repo_dir: Path) -> str:
        return "abc1234\n1\t0\thotspots.py\n1\t0\tuser.py\n"

    costs = analyze_repo(tmp_path, git_log_fn=fake_git_log_fn)
    by_path = {c.path: c for c in costs}
    assert by_path["hotspots.py"].fan_in == 1
    assert by_path["user.py"].fan_in == 0
    assert by_path["hotspots.py"].cost == by_path["hotspots.py"].size * 1 * 2


def test_analyze_repo_ignores_extensions_outside_the_default_set(tmp_path):
    (tmp_path / "notes.md").write_text("# hello\n", encoding="utf-8")

    def fake_git_log_fn(repo_dir: Path) -> str:
        return "abc1234\n1\t0\tnotes.md\n"

    assert analyze_repo(tmp_path, git_log_fn=fake_git_log_fn) == []
