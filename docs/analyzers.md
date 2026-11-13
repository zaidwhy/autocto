# Analyzer reference

One section per module in `src/autocto/`. Every module has pure functions plus one
`analyze_repo` that does the file and git I/O. Design rationale and failure modes are in
[ARCHITECTURE.md](ARCHITECTURE.md); captured output is in [demos.md](demos.md).

Library use:

```bash
pip install -e ".[dev]"
python -c "
from pathlib import Path
from autocto.hotspots import analyze_repo
for hotspot in analyze_repo(Path('.'))[:3]:
    print(hotspot)
"
```

## Hotspots (`hotspots.py`)

Churn is the commit count per file from `git log --numstat`. Complexity is a branch-keyword and
operator density proxy. Score is churn x complexity. Pure functions: `parse_numstat_log`,
`complexity_score`, `compute_hotspots`. Entry point:
`analyze_repo(repo_dir, *, extensions=..., git_log_fn=...)` returns `list[Hotspot]` (`path`,
`churn`, `complexity`, `score`).

## Duplicates (`duplicates.py`)

Token-shingle Jaccard similarity across files. Pure functions: `tokenize`, `shingle`,
`jaccard_similarity`, `find_duplicates`. Entry point:
`analyze_repo(repo_dir, *, extensions=..., shingle_size=..., threshold=...)` returns
`list[DuplicatePair]` (`path_a`, `path_b`, `similarity`). Default threshold 0.6.

## Maintenance cost (`maintenance_cost.py`)

`size x churn x (1 + fan_in)`: size is line count, churn reuses `hotspots.parse_numstat_log`,
fan-in is how many other files import the file, from the real import graph built by `imports.py`
(Python and JS/TS). The `1 +` keeps a file nobody imports from scoring zero; see the
`estimate_costs` docstring. Pure functions: `count_lines`, `estimate_costs`, and the older stem
name-matching helpers `extract_referenced_names` and `compute_fan_in`, kept for callers that
have only bare names. Entry point: `analyze_repo(repo_dir, *, extensions=..., git_log_fn=...)`
returns `list[MaintenanceCost]` (`path`, `size`, `churn`, `fan_in`, `cost`).

## Architectural debt (`architectural_debt.py`)

Three independent signals over one same-repo import graph from `imports.resolve_imports`:

- **Import cycles:** `find_cycles` runs an iterative Tarjan strongly-connected-components pass
  and reports each component of size above 1. This is a documented simplification versus
  enumerating every elementary cycle.
- **God files:** `find_god_files` flags files that clear both a size threshold and a
  connections threshold (`fan_in + fan_out`), ranked by `size x (fan_in + fan_out)`.
- **Layering violations:** `find_layering_violations` runs only when the caller passes
  `layer_order` (top-level package names, most foundational first; CLI `--layers a,b,c`). A
  violation is an import edge from a more foundational layer up into a less foundational one.
  `None` means skip, never a guessed order.

`analyze_repo(repo_dir, *, extensions=..., layer_order=None, size_threshold=...,
connections_threshold=...)` returns one `ArchitecturalDebtReport` (`cycles`, `god_files`,
`layering_violations`). No git and no subprocess in this module.

## Import resolution (`imports.py`)

Resolves each import statement to the one file it names. Python through `ast` (packages,
relative imports, `src/` layouts, `from pkg import submodule`); JS/TS relative specifiers,
`index.*`, `.js` to `.ts`, `export ... from`, `require`, dynamic `import()`. Imports of anything
outside the repo give no edge; tsconfig path aliases, `sys.path` edits and dynamic Python
imports are not followed. `build_import_graph` is the older stem name-matching variant.

## Source walk (`walk.py`)

One rule for which directories a walk skips: `.git`, `node_modules`, `dist`, `build`, caches,
`site-packages`, `.tox`, and any virtual environment whose name starts with `venv` or `.venv`.

## Migration planner (`migration_plan.py`)

Takes a human-written `Sequence[ProposedChange]` (`id`, `description`, `files`, `depends_on`,
`risk`) and orders it with `order_changes` (Kahn's algorithm, ties broken by `id` ascending;
`CycleError` on a dependency cycle or an unknown id). `build_migration_plan(title, changes)`
attaches a risk-derived verification instruction to each step; `generate_migration_plan` builds
and renders markdown in one call. It never reads a repo. From the CLI: `autocto plan FILE`,
where FILE is JSON with `title`, optional `rationale`, and `changes`.

## Injectable seams

`hotspots` and `maintenance_cost` take `git_log_fn` so tests never shell out to real git.
`architectural_debt` and `migration_plan` need no git seam. See `CONTRIBUTING.md` for the
pattern.
