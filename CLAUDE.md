# CLAUDE.md - autocto

Repository-health analyzers from git history alone (bug hotspots, duplicated logic, maintenance cost, architectural debt, migration plan). Library with 93 offline tests; the SWE flagship per `zaid-os/strategy/FLAGSHIPS.md`. Status: all five analyzers shipped; **no CLI yet** - that is the next deliverable (`autocto` console script + PyPI release).
Doc of record: `README.md` (roadmap section) and `CONTRIBUTING.md`.

## Run

| What | Command |
|---|---|
| Activate env | `py -3.12 -m venv .venv` then `.venv\Scripts\activate` (needs Python 3.12+, per `pyproject.toml`) |
| Install | `pip install -e .[dev]` |
| Run | `python -c "from autocto.hotspots import analyze_repo; print(analyze_repo('.'))"` (CLI pending) |
| Tests | `pytest -q` - expected: `93 passed` |
| Lint | `ruff check src tests` |

## Deploy

- Library, not a service. Target: PyPI via trusted publishing (`.github/workflows/publish.yml`, on tag `v*`), `pipx install autocto`. Not published yet.

## Layout

```
src/autocto/   hotspots.py duplication.py maintenance.py architecture.py migration.py (each exposes analyze_repo)
tests/         one file per analyzer, fixtures build throwaway git repos
```

## Definition of done (any change here)

- `pytest -q` green with the count above; new analyzer logic tested against a fixture repo.
- Pure functions stay pure: no network, no global state, input is a repo path.
- README example still runs; CHANGELOG entry if behaviour changed.
- Fetch-first push; `git status -sb` clean.

## Gotchas

- Never the em dash character (U+2014); use " - ". Never add Claude/Anthropic attribution anywhere (commits, PRs, files).
- Fixture repos are created with real `git` commands in tests; on Windows set `PYTHONUTF8=1` (global already) so author names with Unicode do not crash.
