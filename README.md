# autocto

[![CI](https://github.com/syzayd/autocto/actions/workflows/ci.yml/badge.svg)](https://github.com/syzayd/autocto/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-31%20passing-brightgreen)](tests/)

Automated CTO: repository health analyzers that read a codebase and its git
history and report where the real engineering risk lives.

Status: analyzers land one PR at a time via the ai-ecosystem Night Shift queue
(PROJECT-GENESIS.md section 9). Two of five are shipped (hotspots,
duplicates); the rest are tracked in [Roadmap](#roadmap).

## Quickstart

There is no CLI yet (see [Roadmap](#roadmap)) - each analyzer is a pure
`analyze_repo(repo_dir)` function you call directly from Python.

```bash
pip install -e ".[dev]"
```

```bash
python -c "
from pathlib import Path
from autocto.hotspots import analyze_repo

for hotspot in analyze_repo(Path('.'))[:3]:
    print(hotspot)
"
```

This runs the bug-hotspot analyzer against whatever repo you point it at -
here, autocto's own working directory. See [Demo](#demo) below for real
output, and [Architecture](#architecture) for what each module returns.

## Analyzers

1. **Bug-hotspot analyzer** (`src/autocto/hotspots.py`) - churn x complexity
   over `git log`; the files that change often AND are complex are where
   bugs cluster. `analyze_repo(repo_dir)` ranks a real repo's tracked files.
2. **Duplicated-logic detector** (`src/autocto/duplicates.py`) - token-shingle
   (Jaccard) similarity across files; `analyze_repo(repo_dir)` ranks a real repo's
   file pairs by duplication risk.
3. **Maintenance-cost estimator** - size x churn x dependency fan-in, with a
   documented formula.
4. **Architectural-debt report** - import cycles, god files, layering
   violations.
5. **Migration-plan generator** - turns a redesign proposal into an ordered,
   verifiable migration plan.

All analyzers are pure functions over repo data: offline, deterministic,
testable without API keys.

## Demo

Real, captured output - not invented numbers. Two runs below, both against
repos checked out locally at the time this README was written.

### Bug-hotspot analyzer against `recall` (a separate, actively developed repo
with 94 commits of real history - more churn variance than autocto's own
single-commit-per-file history shows)

Command:

```bash
python -c "
from pathlib import Path
from autocto.hotspots import analyze_repo

for hotspot in analyze_repo(Path('/path/to/recall'))[:5]:
    print(hotspot)
"
```

Output:

```
Hotspot(path='frontend/src/App.jsx', churn=29, complexity=129, score=3741)
Hotspot(path='backend/main.py', churn=14, complexity=89, score=1246)
Hotspot(path='backend/memory.py', churn=4, complexity=46, score=184)
Hotspot(path='eval/benchmark.py', churn=3, complexity=40, score=120)
Hotspot(path='backend/live.py', churn=4, complexity=19, score=76)
```

`App.jsx` is both the most-changed file in that repo's history (29 commits)
and its most branch-heavy - exactly the churn x complexity signal this
analyzer is built to surface.

### Duplicated-logic detector against autocto's own tree

Command:

```bash
python -c "
from pathlib import Path
from autocto.duplicates import analyze_repo

pairs = analyze_repo(Path('.'))
print(f'{len(pairs)} pair(s) at or above the default 0.6 similarity threshold')
for pair in pairs:
    print(pair)
"
```

Output:

```
0 pair(s) at or above the default 0.6 similarity threshold
```

autocto's own two analyzer modules and their tests share no duplicated
5-token shingles above the default threshold - a correct negative result on a
small, deliberately non-duplicated codebase, not a bug.

## Architecture

One line per planned analyzer, numbered to match [Analyzers](#analyzers)
above:

1. `src/autocto/hotspots.py` - churn (`git log --numstat` commit-frequency
   count) x complexity (branch-keyword/operator density proxy). Pure
   functions `parse_numstat_log`, `complexity_score`, `compute_hotspots`
   wired together by the one effectful entry point,
   `analyze_repo(repo_dir, *, extensions=..., git_log_fn=...)`, which returns
   `list[Hotspot]` (`path`, `churn`, `complexity`, `score`).
2. `src/autocto/duplicates.py` - token-shingle Jaccard similarity across
   files. Pure functions `tokenize`, `shingle`, `jaccard_similarity`,
   `find_duplicates` wired together by
   `analyze_repo(repo_dir, *, extensions=..., shingle_size=..., threshold=...)`,
   which returns `list[DuplicatePair]` (`path_a`, `path_b`, `similarity`).
3. Maintenance-cost estimator - not yet built. See [Roadmap](#roadmap).
4. Architectural-debt report - not yet built. See [Roadmap](#roadmap).
5. Migration-plan generator - not yet built. See [Roadmap](#roadmap).

Both shipped modules follow the same shape: filesystem/subprocess access is
isolated to `analyze_repo`, everything else is a pure function over strings
and dicts, and the effectful seam (`git_log_fn` in hotspots) is injectable so
tests never shell out to real git. See `CONTRIBUTING.md` for the pattern in
detail.

## Roadmap

Tier 4 items in the ai-ecosystem Night Shift queue (PROJECT-GENESIS.md
section 9), still open and not part of this repo yet:

- **#30 Maintenance-cost estimator** - size x churn x dependency fan-in,
  with a documented formula.
- **#31 Architectural-debt report** - import cycles, god files, layering
  violations.
- **#32 Migration-plan generator** - turns a redesign proposal into an
  ordered, verifiable migration plan.

There is also no CLI entry point yet (no `[project.scripts]` in
`pyproject.toml`); analyzers are called as Python functions, per the
[Quickstart](#quickstart) above.
