# Architecture

System-design note for autocto. `README.md` covers install and usage; this covers how the analyzers are built and what their honest limits are.

## Problem

Tell someone which parts of an unfamiliar repository are risky to change, using only what the repository already contains: its git history and its source files. No LLM calls, no network, no services to run, and output a human can audit line by line.

## Requirements

- Five analyzers over one repo: bug hotspots, duplicated logic, maintenance cost, architectural debt, and a migration plan.
- Deterministic: the same repo state gives the same ranking, including ties.
- Zero runtime dependencies, so `pipx install` is instant and works anywhere Python and `git` exist.
- Usable as a CLI (`autocto report`) and as a library of pure functions.
- Each formula is documented in the module that computes it, so a score is explainable.

## Constraints

- Python 3.12 or newer, and `git` on the PATH. Nothing else.
- No real parser per language, by design: analysis has to stay dependency-free. The cost is that several signals are heuristics, and the code says so.
- Source scanning covers `.py`, `.js`, `.jsx`, `.ts` and `.tsx` by default.

## Architecture

```
autocto CLI  (hotspots | duplicates | maintenance | architecture | report, --json)
     |
     |-- hotspots.py          git log --numstat -> churn per file; complexity proxy per file
     |                        risk = churn x complexity
     |-- duplicates.py        token shingles per file; Jaccard similarity for every pair
     |-- maintenance_cost.py  cost = size x churn x (1 + fan_in)
     |-- architectural_debt.py import graph -> cycles, god files, layering violations
     `-- migration_plan.py    proposed changes -> dependency-ordered, verifiable plan (markdown)
```

Every module exposes pure functions plus one `analyze_repo` that does the file and git I/O and wires them together. The pure functions take plain dicts and lists, which is what makes them testable without a repository.

## Data flow: `autocto report`

1. Hotspots and maintenance cost each run `git log --numstat` once; every analyzer walks the working tree for the configured extensions. Duplicates and architectural debt use the source files only.
2. Hotspots counts commits per file as churn, not lines touched, and scores complexity as 1 plus the number of branch keywords and operators. Only files that have both a churn value and a complexity value are scored.
3. Duplicates tokenises each file, builds shingle sets and ranks file pairs by Jaccard similarity above a threshold.
4. Maintenance cost reuses size and churn, and adds fan-in: how many other files reference a file by module name. It multiplies by `(1 + fan_in)` so a file nobody imports still carries its own size times churn.
5. Architectural debt builds an import graph with the same name-matching that fan-in uses, then reports import cycles, files that are both large and highly connected, and layering violations against an optional `--layers a,b,c` ordering.
6. The migration planner is separate: it takes a set of proposed changes with dependencies and returns a topologically ordered plan, raising `CycleError` if the changes depend on each other in a loop.
7. The CLI prints a table per analyzer, or JSON with `--json`.

## Components

| Component | File | Responsibility |
|---|---|---|
| Hotspots | `hotspots.py` | parse the numstat log, churn, complexity proxy, ranking |
| Duplicates | `duplicates.py` | tokenise, shingle, Jaccard, pair ranking |
| Maintenance cost | `maintenance_cost.py` | size, churn, fan-in, the documented cost formula |
| Architectural debt | `architectural_debt.py` | import graph, cycles, god files, layering |
| Migration plan | `migration_plan.py` | ordering proposed changes, markdown rendering |
| CLI | `cli.py` | argument parsing, table and JSON output |
| Tests | `tests/` | 107 tests, including end to end against a real temporary git repo |

## Failure modes

| Failure | Effect | Mitigation |
|---|---|---|
| Not a git repository | `git log` exits 128 and the analyzer raises an unhandled `CalledProcessError` with a traceback | a known gap: there is no friendly message yet (see `ROADMAP.md`) |
| A file has churn but no readable source | cannot be scored honestly | excluded from the ranking rather than given a made-up score |
| Two unrelated files share a name stem | fan-in and import edges are over-counted | documented as a known trade-off of name matching; fine for a relative ranking inside one repo, wrong as an absolute number |
| Languages outside py, js, ts | those files are ignored | the extension set is a parameter |
| Proposed migration changes form a cycle | no valid order exists | `CycleError` names the problem instead of returning a wrong plan |
| Ties in a ranking | order would depend on dict iteration | ties break on path, so output is stable |

## Tradeoffs

- **Heuristic complexity over an AST:** dependency-free and good enough to rank files against each other within one repo. It is not cyclomatic complexity, and it should not be compared across repositories.
- **Name-matching over real import resolution:** one scan covers both Python and JS or TS repos with no per-language resolver. It can over-count when stems collide.
- **Churn as commit count, not line count:** a file touched in many small commits is riskier than one large rewrite, which matches the research the hotspot idea comes from.
- **Pure functions plus a thin I/O wrapper:** more code than one script, but each formula is testable in isolation and the ordering is deterministic.

## Scaling

The cost is one `git log` per history-based analyzer plus one pass over the source files per analyzer, and shingling or pairwise duplicate comparison is the expensive part: it grows with the square of the file count. The first thing to change on a very large repository is to bucket files before comparing them, and to cache the `git log` result across the two analyzers that read it instead of running it twice.

## Security

The tool reads a repository and prints a report. It never executes repository code, opens no network connection, and writes nothing unless you redirect its output. Releases are published to PyPI with trusted publishing (OIDC), so no upload token is stored anywhere.

## Observability

Output is the observability: the report itself, with `--json` for machines. The deterministic ordering means two runs on the same commit can be diffed. Errors are not yet polished: a failing `git` call surfaces as a raw traceback.

## Cost

$0 to run and $0 to distribute. It has no dependencies to keep patched.

## Future

See `ROADMAP.md`. The main open questions are real import resolution and a language-aware complexity measure, both of which trade away the zero-dependency property.
