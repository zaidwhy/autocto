# Roadmap

Direction, not a promise. This project is one person's flagship library, so the list is short and each item names what it costs.

## Shipped

- **v0.1.0 (2026-09-16):** five analyzers, a CLI with `--json`, 107 tests, a GitHub release with wheel and sdist, and PyPI publishing through trusted publishing as `repo-autocto`.
- **Unreleased:** `--fail-over N` on `hotspots` and `maintenance` for CI; walks skip any `venv*` or `.venv*` environment; real import resolution (`imports.py`): fan-in, import cycles and god files now use the file each import names, not stem matching; `autocto plan FILE` runs the migration planner from a JSON proposal; `maintenance` works on Windows; a one-line error instead of a `CalledProcessError` traceback when `hotspots`, `maintenance` or `report` is pointed at a folder that is not a git repository.

## Candidates, in the order the current limits suggest

1. **A CI mode for the other analyzers:** `--fail-over` covers `hotspots` and `maintenance`; `architecture` (any cycle) and `duplicates` (any pair above a similarity) could gate the same way.
3. **Language-aware complexity:** a real syntax tree instead of counting branch keywords. More accurate and comparable across repositories, but needs a parser dependency per language.
4. **Cache the git log across analyzers:** `autocto report` runs `git log` separately for hotspots and for maintenance cost. Worth doing when someone runs it on a very large repository.
5. **Bucketed duplicate detection:** avoid the pairwise comparison that grows with the square of the file count.

## Not planned

- Any LLM call inside an analyzer. Determinism and auditability are the point.
- Auto-fixing code. The migration planner orders a change; it does not make one.

## How to influence it

Open an issue with the repository shape that surprised you (the smallest input that shows it). Real reports change the order above.
