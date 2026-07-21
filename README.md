# autocto

[![CI](https://github.com/syzayd/autocto/actions/workflows/ci.yml/badge.svg)](https://github.com/syzayd/autocto/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-77%20passing-brightgreen)](tests/)

Automated CTO: repository health analyzers that read a codebase and its git
history and report where the real engineering risk lives.

Status: analyzers land one PR at a time via the ai-ecosystem Night Shift queue
(PROJECT-GENESIS.md section 9). Four of five are shipped (hotspots,
duplicates, maintenance-cost, architectural-debt); the rest are tracked in
[Roadmap](#roadmap).

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
3. **Maintenance-cost estimator** (`src/autocto/maintenance_cost.py`) - size x
   churn x dependency fan-in; `analyze_repo(repo_dir)` ranks a real repo's
   tracked files by `size x churn x (1 + fan_in)`.
4. **Architectural-debt report** (`src/autocto/architectural_debt.py`) - three
   independent signals over one same-repo import graph: import cycles (Tarjan
   strongly-connected components), god files (large AND highly-connected),
   and layering violations (only checked when the caller supplies an
   explicit layer order - see [Architecture](#architecture)).
   `analyze_repo(repo_dir)` returns all three for a real repo.
5. **Migration-plan generator** - turns a redesign proposal into an ordered,
   verifiable migration plan.

All analyzers are pure functions over repo data: offline, deterministic,
testable without API keys.

## Demo

Real, captured output - not invented numbers. Three runs below, all against
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

### Maintenance-cost estimator against `recall` (same repo as the hotspot demo,
for a like-for-like comparison)

Command:

```bash
python -c "
from pathlib import Path
from autocto.maintenance_cost import analyze_repo

for cost in analyze_repo(Path('/path/to/recall'))[:5]:
    print(cost)
"
```

Output:

```
MaintenanceCost(path='frontend/src/App.jsx', size=772, churn=29, fan_in=1, cost=44776)
MaintenanceCost(path='backend/main.py', size=461, churn=14, fan_in=1, cost=12908)
MaintenanceCost(path='backend/memory.py', size=262, churn=4, fan_in=0, cost=1048)
MaintenanceCost(path='backend/live.py', size=125, churn=4, fan_in=1, cost=1000)
MaintenanceCost(path='eval/benchmark.py', size=309, churn=3, fan_in=0, cost=927)
```

`App.jsx` tops both this ranking and the hotspot one - it is large, the
most-changed file in the repo, AND imported elsewhere, which is exactly what
"maintenance cost" should mean: not just churn x complexity, but the size of
the file and the blast radius of touching it.

### Architectural-debt report against `personal-llm` (a bigger, more layered
codebase than recall or autocto itself - more likely to actually show
something)

Command:

```bash
python -c "
from pathlib import Path
from autocto.architectural_debt import analyze_repo

report = analyze_repo(Path('/path/to/personal-llm'))
print(f'{len(report.cycles)} import cycle(s)')
print(f'{len(report.god_files)} god file(s)')
for god_file in report.god_files:
    print(' ', god_file)

layered = analyze_repo(
    Path('/path/to/personal-llm'),
    layer_order=['router', 'memory', 'rag', 'interfaces'],
)
print(f'{len(layered.layering_violations)} layering violation(s) under router -> memory -> rag -> interfaces')
"
```

Output:

```
0 import cycle(s)
3 god file(s)
  GodFile(path='src/personal_llm/memory/store.py', size=287, fan_in=14, fan_out=1)
  GodFile(path='src/personal_llm/interfaces/cli.py', size=302, fan_in=1, fan_out=11)
  GodFile(path='src/personal_llm/interfaces/api.py', size=257, fan_in=0, fan_out=9)
0 layering violation(s) under router -> memory -> rag -> interfaces
```

Real, captured, honest results, including the zeroes - same "a clean result
is a correct result, not a suppressed one" rule duplicates.py's demo already
follows. `personal-llm` has no import cycles and no layering violations under
that ordering (its `router` package genuinely never reaches up into
`interfaces`, by inspection of the real source), which is a legitimate,
useful thing to report about a codebase: this project's dependency
discipline is holding. `memory/store.py` is flagged as a god file because
fourteen other files reference it by name (the SQLite-backed
`MemoryStore` class is the one shared persistence layer) on top of nearly
300 lines - exactly the "big and everyone depends on it" combination this
signal exists to surface.

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
3. `src/autocto/maintenance_cost.py` - size (line count) x churn (reuses
   `hotspots.parse_numstat_log`) x dependency fan-in (import-statement
   name-matching against file stems, Python and JS/TS). Pure functions
   `count_lines`, `extract_referenced_names`, `compute_fan_in`,
   `estimate_costs` (formula: `size x churn x (1 + fan_in)` - see that
   function's docstring for why `1 + fan_in`, not bare `fan_in`) wired
   together by `analyze_repo(repo_dir, *, extensions=..., git_log_fn=...)`,
   which returns `list[MaintenanceCost]` (`path`, `size`, `churn`, `fan_in`,
   `cost`).
4. `src/autocto/architectural_debt.py` - three independent signals over one
   same-repo import graph, built by reusing
   `maintenance_cost.extract_referenced_names` per file and resolving names
   to real files the same stem-matching way `maintenance_cost.compute_fan_in`
   does (pure function `build_import_graph`). Import cycles: `find_cycles`
   runs an iterative Tarjan strongly-connected-components pass over the
   graph and reports each component of size > 1 (a documented simplification
   versus enumerating every elementary cycle - see the function's
   docstring for why). God files: `find_god_files` flags files that clear
   BOTH a size threshold (line count, via `maintenance_cost.count_lines`)
   AND a connections threshold (`fan_in + fan_out`, `fan_in` from
   `compute_fan_in`, `fan_out` from the same import graph), returning
   `list[GodFile]` (`path`, `size`, `fan_in`, `fan_out`) ranked by
   `size x (fan_in + fan_out)`. Layering violations: `find_layering_violations`
   only runs when the caller passes an explicit `layer_order` (an ordered
   list of top-level package names, most-foundational first) - there is no
   universal default across arbitrary repos, so `None` (the default) means
   "skip the check", never a fabricated ordering; a violation is an import
   edge pointing from a more-foundational layer up into a less-foundational
   one, returned as `list[LayeringViolation]` (`importer`, `importee`,
   `importer_layer`, `importee_layer`). All three are wired together by the
   one effectful entry point,
   `analyze_repo(repo_dir, *, extensions=..., layer_order=None, size_threshold=..., connections_threshold=...)`,
   which returns one `ArchitecturalDebtReport` (`cycles`, `god_files`,
   `layering_violations`). No git, no subprocess anywhere in this module -
   none of its three signals need churn.
5. Migration-plan generator - not yet built. See [Roadmap](#roadmap).

All shipped modules follow the same shape: filesystem/subprocess access is
isolated to `analyze_repo`, everything else is a pure function over strings
and dicts. Where a module has a genuinely effectful operation (`git log` in
hotspots/maintenance_cost) it is an injectable seam (`git_log_fn`) so tests
never shell out to real git; architectural_debt.py needs no such seam at all,
since none of its three signals depend on git history. See `CONTRIBUTING.md`
for the pattern in detail.

## Roadmap

Tier 4 items in the ai-ecosystem Night Shift queue (PROJECT-GENESIS.md
section 9), still open and not part of this repo yet:

- **#32 Migration-plan generator** - turns a redesign proposal into an
  ordered, verifiable migration plan.

There is also no CLI entry point yet (no `[project.scripts]` in
`pyproject.toml`); analyzers are called as Python functions, per the
[Quickstart](#quickstart) above.
