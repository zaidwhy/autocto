"""Duplicated-logic detector: tokenizer, shingling, Jaccard ranking, real-repo wiring."""

from __future__ import annotations

from pathlib import Path

from autocto.duplicates import (
    DuplicatePair,
    analyze_repo,
    find_duplicates,
    jaccard_similarity,
    shingle,
    tokenize,
)


def test_tokenize_splits_identifiers_numbers_and_punctuation():
    assert tokenize("total = a1 + 2.5") == ["total", "=", "a1", "+", "2.5"]


def test_tokenize_empty_input():
    assert tokenize("") == []


def test_shingle_returns_empty_set_when_fewer_tokens_than_k():
    assert shingle("a b c", k=5) == set()


def test_shingle_produces_overlapping_windows():
    # 4 tokens, k=2 -> 3 windows
    assert shingle("a b c d", k=2) == {"a b", "b c", "c d"}


def test_shingle_identical_content_yields_identical_shingles():
    text = "def add(x, y):\n    return x + y\n"
    assert shingle(text, k=3) == shingle(text, k=3)


def test_jaccard_similarity_identical_sets_is_one():
    s = {"a b", "b c"}
    assert jaccard_similarity(s, s) == 1.0


def test_jaccard_similarity_disjoint_sets_is_zero():
    assert jaccard_similarity({"a b"}, {"c d"}) == 0.0


def test_jaccard_similarity_both_empty_is_zero():
    assert jaccard_similarity(set(), set()) == 0.0


def test_jaccard_similarity_partial_overlap():
    a = {"a b", "b c", "c d"}
    b = {"b c", "c d", "d e"}
    # intersection {b c, c d} = 2, union = 4
    assert jaccard_similarity(a, b) == 0.5


def test_find_duplicates_filters_by_threshold():
    shingles = {
        "a.py": {"x y", "y z"},
        "b.py": {"x y", "y z"},  # identical to a.py -> similarity 1.0
        "c.py": {"p q", "q r"},  # disjoint from both -> similarity 0.0
    }
    pairs = find_duplicates(shingles, threshold=0.6)
    assert pairs == [DuplicatePair("a.py", "b.py", 1.0)]


def test_find_duplicates_orders_by_similarity_then_path():
    shingles = {
        "a.py": {"x y", "y z", "z w"},
        "b.py": {"x y", "y z"},  # 2/3 overlap with a.py
        "c.py": {"x y", "y z", "z w"},  # identical to a.py
    }
    pairs = find_duplicates(shingles, threshold=0.5)
    assert [(p.path_a, p.path_b) for p in pairs] == [("a.py", "c.py"), ("a.py", "b.py"), ("b.py", "c.py")]
    assert pairs[0].similarity == 1.0


def test_find_duplicates_empty_input():
    assert find_duplicates({}) == []


def test_analyze_repo_flags_a_near_duplicate_pair(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    shared_body = "\n".join(f"    step{i}()" for i in range(10))
    (repo / "a.py").write_text(f"def run():\n{shared_body}\n", encoding="utf-8")
    (repo / "b.py").write_text(f"def run():\n{shared_body}\n    extra()\n", encoding="utf-8")
    (repo / "c.py").write_text("def totally_different():\n    return 42\n", encoding="utf-8")

    pairs = analyze_repo(repo, shingle_size=5, threshold=0.5)

    assert len(pairs) == 1
    assert {pairs[0].path_a, pairs[0].path_b} == {"a.py", "b.py"}
    assert pairs[0].similarity > 0.5


def test_analyze_repo_ignores_extensions_outside_the_default_set(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "notes.md").write_text("hello " * 20, encoding="utf-8")
    (repo / "notes2.md").write_text("hello " * 20, encoding="utf-8")

    assert analyze_repo(repo) == []


def test_analyze_repo_skips_common_non_source_directories(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    node_modules = repo / "node_modules" / "pkg"
    node_modules.mkdir(parents=True)
    body = "\n".join(f"const step{i} = () => {i};" for i in range(10))
    (repo / "real.js").write_text(body, encoding="utf-8")
    (node_modules / "vendored.js").write_text(body, encoding="utf-8")

    pairs = analyze_repo(repo, threshold=0.5)

    assert pairs == []


def test_analyze_repo_relative_paths_are_repo_relative(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    body = "\n".join(f"def step{i}(): pass" for i in range(10))
    (repo / "sub" / "a.py").write_text(body, encoding="utf-8")
    (repo / "sub" / "b.py").write_text(body, encoding="utf-8")

    pairs = analyze_repo(repo, threshold=0.5)

    assert {pairs[0].path_a, pairs[0].path_b} == {str(Path("sub", "a.py")), str(Path("sub", "b.py"))}
