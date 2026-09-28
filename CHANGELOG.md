# Changelog

## Unreleased

### Changed
- CI runs `ruff check .`; ruff is pinned to 0.16.9 in the `dev` extra so local and CI lint agree (an unpinned CI install pulled 0.16.9 and found 5 issues that local 0.15.17 passed). Fixed them: `collections.abc.Sequence` imports in three modules, explicit `check=False` in one test. 110 tests pass.

### Added
- `docs/autocto-pipeline.svg`: hand-authored one-diagram README hero (inputs, five analyzers, real sample output against recall).
- `docs/ARCHITECTURE.md`: components, data flow, failure modes and tradeoffs, including the honest limits (heuristic complexity, name-matched imports, and the unhandled error outside a git repository).
- `ROADMAP.md`: candidate directions in the order the current limits suggest.

### Fixed
- CLI: `hotspots`, `maintenance` and `report` outside a git repository print `error: <path> is not a git repository` and exit 2 instead of a `CalledProcessError` traceback (3 regression tests; 110 total). `.venv/` is now gitignored, matching the setup in CLAUDE.md.
- README quickstart sample: it showed churn 12/9/7 for `autocto hotspots .`, which no longer reproduces (every file in this repo's history has churn 1). Replaced with a captured 2026-09-27 run against recall.

## v0.1.0 - 2026-09-16

### Added
- `autocto` CLI (`src/autocto/cli.py`) with five subcommands: `hotspots`,
  `duplicates`, `maintenance`, `architecture`, `report`. Each takes a repo
  path (default: current directory), prints a human-readable table by
  default, and supports `--json` for machine-readable output.
- `[project.scripts]` entry point so `pip install repo-autocto` (or
  `pipx install repo-autocto`) puts `autocto` on PATH.
- 14 CLI tests (end-to-end against a real temporary git repo, JSON-shape
  checks, the installed console script itself) - 107 tests total, up from 93.
- `.github/workflows/release.yml`: builds the sdist/wheel and creates a
  GitHub Release with them attached on every `v*` tag.
- `.github/workflows/publish-pypi.yml`: publishes to PyPI via trusted
  publishing, run manually once the PyPI project is configured (see the
  note in that file - a one-time step only Zaid can do, since it needs a
  PyPI account).
- `.devcontainer/devcontainer.json` for one-click Codespaces.

### Changed
- README: quickstart now leads with `pipx install repo-autocto`; badges
  reflect the PyPI package and the current test count.

No changes to the five analyzers themselves in this release - the CLI is a
thin wrapper over `analyze_repo(repo_dir)` in each module.
