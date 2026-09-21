# CLAUDE.md - autocto

Repository-health analyzers from git history alone (bug hotspots, duplicated logic, maintenance cost, architectural debt, migration plan). Library and CLI with 107 offline tests; the SWE flagship per `zaid-os/strategy/FLAGSHIPS.md`. Status: all five analyzers and the `autocto` CLI shipped; v0.1.0 is on PyPI as `repo-autocto`.
Doc of record: `README.md`, `docs/ARCHITECTURE.md` (design and honest limits), `ROADMAP.md` (next steps) and `CONTRIBUTING.md`.

## Run

| What | Command |
|---|---|
| Activate env | `py -3.12 -m venv .venv` then `.venv\Scripts\activate` (needs Python 3.12+, per `pyproject.toml`) |
| Install | `pip install -e .[dev]` |
| Run | `autocto report .` (or `python -m autocto.cli report .`); subcommands `hotspots`, `duplicates`, `maintenance`, `architecture`, `report`, all with `--json` |
| Tests | `pytest -q` - expected: `107 passed` |
| Lint | `ruff check src tests` |

## Deploy

- Library, not a service. Published on PyPI as `repo-autocto` (trusted publishing, `.github/workflows/publish-pypi.yml`); the installed command is `autocto`. Install with `pipx install repo-autocto`. Verify a project exists via the PyPI JSON API (`https://pypi.org/pypi/repo-autocto/json`), never the HTML pages, which return a bot-challenge 200 for any URL.

## Layout

```
src/autocto/   hotspots.py duplicates.py maintenance_cost.py architectural_debt.py migration_plan.py cli.py (each analyzer exposes analyze_repo)
tests/         one file per analyzer plus test_cli.py, fixtures build throwaway git repos
```

## Definition of done (any change here)

- `pytest -q` green with the count above; new analyzer logic tested against a fixture repo.
- Pure functions stay pure: no network, no global state, input is a repo path.
- README example still runs; CHANGELOG entry if behaviour changed.
- Fetch-first push; `git status -sb` clean.

## Gotchas

- Never the em dash character (U+2014); use " - ". Never add Claude/Anthropic attribution anywhere (commits, PRs, files).
- Fixture repos are created with real `git` commands in tests; on Windows set `PYTHONUTF8=1` (global already) so author names with Unicode do not crash.
