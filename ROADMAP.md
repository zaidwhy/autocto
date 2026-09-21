# Roadmap

Direction, not a promise. This project is one person's flagship library, so the list is short and each item names what it costs.

## Shipped

- **v0.1.0 (2026-09-16):** five analyzers, a CLI with `--json`, 107 tests, a GitHub release with wheel and sdist, and PyPI publishing through trusted publishing as `repo-autocto`.

## Candidates, in the order the current limits suggest

1. **A friendly error outside a git repository:** today `autocto hotspots .` in a plain folder ends in a raw `CalledProcessError` traceback. Smallest change on this list, and the first thing a new user can hit.
2. **A CI mode:** a threshold flag that exits non-zero when a file crosses a risk score, so the report can gate a pull request. Cheap, and it turns the tool from a report into a check.
3. **Real import resolution:** replace stem name-matching with an actual resolver per language. Removes the over-count when two files share a name, at the cost of the zero-dependency property or a per-language resolver to maintain.
4. **Language-aware complexity:** a real syntax tree instead of counting branch keywords. More accurate and comparable across repositories, but needs a parser dependency per language.
5. **Cache the git log across analyzers:** `autocto report` runs `git log` separately for hotspots and for maintenance cost. Worth doing when someone runs it on a very large repository.
6. **Bucketed duplicate detection:** avoid the pairwise comparison that grows with the square of the file count.

## Not planned

- Any LLM call inside an analyzer. Determinism and auditability are the point.
- Auto-fixing code. The migration planner orders a change; it does not make one.

## How to influence it

Open an issue with the repository shape that surprised you (the smallest input that shows it). Real reports change the order above.
