"""Architectural-debt report: import graph, cycles, god files, layering, real-repo wiring."""

from __future__ import annotations

from pathlib import Path

from autocto.architectural_debt import (
    ArchitecturalDebtReport,
    GodFile,
    LayeringViolation,
    analyze_repo,
    build_import_graph,
    find_cycles,
    find_god_files,
    find_layering_violations,
)


def test_build_import_graph_resolves_names_to_paths():
    imports_by_file = {
        "a.py": {"b"},
        "b.py": set(),
    }
    graph = build_import_graph(imports_by_file)
    assert graph == {"a.py": {"b.py"}, "b.py": set()}


def test_build_import_graph_excludes_self_edges():
    imports_by_file = {"a.py": {"a"}}
    assert build_import_graph(imports_by_file) == {"a.py": set()}


def test_build_import_graph_unmatched_name_yields_no_edge():
    imports_by_file = {"a.py": {"nonexistent"}, "b.py": set()}
    graph = build_import_graph(imports_by_file)
    assert graph == {"a.py": set(), "b.py": set()}


def test_build_import_graph_every_file_is_a_key_even_with_no_edges():
    imports_by_file = {"a.py": set()}
    assert build_import_graph(imports_by_file) == {"a.py": set()}


def test_find_cycles_detects_a_real_cycle():
    graph = {
        "a.py": {"b.py"},
        "b.py": {"c.py"},
        "c.py": {"a.py"},
    }
    cycles = find_cycles(graph)
    assert cycles == [["a.py", "b.py", "c.py"]]


def test_find_cycles_acyclic_graph_returns_empty():
    graph = {
        "a.py": {"b.py"},
        "b.py": {"c.py"},
        "c.py": set(),
    }
    assert find_cycles(graph) == []


def test_find_cycles_ignores_isolated_nodes_and_single_edges():
    graph = {"a.py": {"b.py"}, "b.py": set(), "c.py": set()}
    assert find_cycles(graph) == []


def test_find_cycles_two_separate_cycles_both_reported_sorted():
    graph = {
        "a.py": {"b.py"},
        "b.py": {"a.py"},
        "x.py": {"y.py"},
        "y.py": {"x.py"},
    }
    cycles = find_cycles(graph)
    assert cycles == [["a.py", "b.py"], ["x.py", "y.py"]]


def test_find_cycles_empty_graph():
    assert find_cycles({}) == []


def test_find_god_files_includes_file_at_the_threshold_boundary():
    size = {"a.py": 250}
    fan_in = {"a.py": 2}
    fan_out = {"a.py": 2}
    god_files = find_god_files(size, fan_in, fan_out, size_threshold=250, connections_threshold=4)
    assert god_files == [GodFile("a.py", 250, 2, 2)]


def test_find_god_files_excludes_file_just_below_size_threshold():
    size = {"a.py": 249}
    fan_in = {"a.py": 10}
    fan_out = {"a.py": 10}
    god_files = find_god_files(size, fan_in, fan_out, size_threshold=250, connections_threshold=4)
    assert god_files == []


def test_find_god_files_excludes_file_just_below_connections_threshold():
    size = {"a.py": 1000}
    fan_in = {"a.py": 2}
    fan_out = {"a.py": 1}
    god_files = find_god_files(size, fan_in, fan_out, size_threshold=250, connections_threshold=4)
    assert god_files == []


def test_find_god_files_large_but_isolated_file_excluded():
    size = {"a.py": 5000}
    fan_in = {"a.py": 0}
    fan_out = {"a.py": 0}
    assert find_god_files(size, fan_in, fan_out) == []


def test_find_god_files_ranked_descending_by_size_times_connections():
    size = {"a.py": 300, "b.py": 1000}
    fan_in = {"a.py": 5, "b.py": 2}
    fan_out = {"a.py": 5, "b.py": 2}
    god_files = find_god_files(size, fan_in, fan_out, size_threshold=250, connections_threshold=4)
    assert [g.path for g in god_files] == ["b.py", "a.py"]


def test_find_god_files_ties_break_on_path():
    size = {"a.py": 300, "b.py": 300}
    fan_in = {"a.py": 2, "b.py": 2}
    fan_out = {"a.py": 2, "b.py": 2}
    god_files = find_god_files(size, fan_in, fan_out, size_threshold=250, connections_threshold=4)
    assert [g.path for g in god_files] == ["a.py", "b.py"]


def test_find_god_files_empty_input():
    assert find_god_files({}, {}, {}) == []


def test_find_layering_violations_catches_a_real_violation():
    # router (foundational) importing interfaces (top-level) is the classic violation.
    graph = {"router/core.py": {"interfaces/api.py"}, "interfaces/api.py": set()}
    violations = find_layering_violations(graph, layer_order=["router", "memory", "interfaces"])
    assert violations == [
        LayeringViolation("router/core.py", "interfaces/api.py", "router", "interfaces")
    ]


def test_find_layering_violations_does_not_flag_a_compliant_import():
    # interfaces (top-level) importing router (foundational) is the correct direction.
    graph = {"interfaces/api.py": {"router/core.py"}, "router/core.py": set()}
    violations = find_layering_violations(graph, layer_order=["router", "memory", "interfaces"])
    assert violations == []


def test_find_layering_violations_none_layer_order_returns_empty():
    graph = {"router/core.py": {"interfaces/api.py"}, "interfaces/api.py": set()}
    assert find_layering_violations(graph, layer_order=None) == []


def test_find_layering_violations_default_layer_order_is_none():
    graph = {"router/core.py": {"interfaces/api.py"}, "interfaces/api.py": set()}
    assert find_layering_violations(graph) == []


def test_find_layering_violations_excludes_files_outside_the_given_layers():
    graph = {"scripts/tool.py": {"interfaces/api.py"}, "interfaces/api.py": set()}
    violations = find_layering_violations(graph, layer_order=["router", "memory", "interfaces"])
    assert violations == []


def test_find_layering_violations_empty_layer_order_returns_empty():
    graph = {"router/core.py": {"interfaces/api.py"}, "interfaces/api.py": set()}
    assert find_layering_violations(graph, layer_order=[]) == []


def test_analyze_repo_end_to_end_detects_a_cycle_and_god_file(tmp_path):
    repo = tmp_path / "repo"
    (repo / "router").mkdir(parents=True)
    (repo / "interfaces").mkdir(parents=True)

    # router/a.py <-> router/b.py forms a real, self-contained import cycle.
    (repo / "router" / "a.py").write_text("from router.b import x\n", encoding="utf-8")
    (repo / "router" / "b.py").write_text("from router.a import y\n", encoding="utf-8")

    # A big file that imports both cycle files (fan_out=2) but nothing imports it
    # back (fan_in=0) - large and connected, but not itself part of the cycle.
    big_body = "\n".join(f"line_{i} = {i}" for i in range(300))
    (repo / "interfaces" / "big.py").write_text(
        "from router.a import x\nfrom router.b import y\n" + big_body + "\n",
        encoding="utf-8",
    )

    report = analyze_repo(repo, size_threshold=250, connections_threshold=2)

    assert isinstance(report, ArchitecturalDebtReport)
    assert report.cycles == [[str(Path("router", "a.py")), str(Path("router", "b.py"))]]
    assert [g.path for g in report.god_files] == [str(Path("interfaces", "big.py"))]


def test_analyze_repo_layering_violations_wired_through(tmp_path):
    repo = tmp_path / "repo"
    (repo / "router").mkdir(parents=True)
    (repo / "interfaces").mkdir(parents=True)
    (repo / "router" / "core.py").write_text("from interfaces.api import x\n", encoding="utf-8")
    (repo / "interfaces" / "api.py").write_text("x = 1\n", encoding="utf-8")

    report = analyze_repo(repo, layer_order=["router", "interfaces"])

    assert report.layering_violations == [
        LayeringViolation(
            str(Path("router", "core.py")), str(Path("interfaces", "api.py")), "router", "interfaces"
        )
    ]


def test_analyze_repo_no_layer_order_gives_no_layering_violations(tmp_path):
    repo = tmp_path / "repo"
    (repo / "router").mkdir(parents=True)
    (repo / "interfaces").mkdir(parents=True)
    (repo / "router" / "core.py").write_text("from interfaces.api import x\n", encoding="utf-8")
    (repo / "interfaces" / "api.py").write_text("x = 1\n", encoding="utf-8")

    report = analyze_repo(repo)

    assert report.layering_violations == []


def test_analyze_repo_ignores_extensions_outside_the_default_set(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "notes.md").write_text("# hello\n", encoding="utf-8")

    report = analyze_repo(repo)

    assert report == ArchitecturalDebtReport(cycles=[], god_files=[], layering_violations=[])


def test_analyze_repo_no_git_subprocess_needed(tmp_path):
    # Not a real git repo at all - proves this analyzer needs no churn/subprocess.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")

    report = analyze_repo(repo)

    assert report.cycles == []
    assert report.god_files == []
