# Worked examples

Captured output for each analyzer. Commands use the installed CLI; the library calls are in
[analyzers.md](analyzers.md). Subjects are other repositories on the author's machine, so a re-run
on a later commit gives different numbers.

## Hotspots on recall

Captured 2026-11-13 against a local checkout of [recall](https://github.com/zaidwhy/recall)
(227 commits):

```
$ autocto hotspots ../recall --limit 5
path                  churn  complexity  score
--------------------  -----  ----------  -----
frontend/src/App.jsx  41     129         5289
backend/main.py       42     90          3780
backend/memory.py     11     49          539
eval/benchmark.py     5      40          200
backend/live.py       9      19          171
```

`App.jsx` is both the most-changed file in that history and among its most branch-heavy, which
is the signal the analyzer is built to surface. Run against autocto's own tree the ranking is
flat: the top file, `src/autocto/cli.py`, scores 335 (churn 5, complexity 67), measured the
same day.

## Maintenance cost on recall

Captured 2026-11-13, same checkout:

```
$ autocto maintenance ../recall --limit 5
path                   size  churn  fan_in  cost
---------------------  ----  -----  ------  -----
frontend/src/App.jsx   772   41     1       63304
backend/main.py        483   42     2       60858
backend/memory.py      329   11     3       14476
eval/benchmark.py      320   5      1       3200
backend/perception.py  91    7      3       2548
```

Cost is `size x churn x (1 + fan_in)`, so a large, often-changed file that others import ranks
above one that is only churned.

## Duplicates on autocto itself

Captured 2026-11-13:

```
$ autocto duplicates .
(no results)
```

No file pair reaches the default 0.6 shingle similarity. A clean result is reported as clean,
not suppressed.

## Architectural debt on personal-llm

Captured 2026-11-13 against `ai-ecosystem/personal-llm` (61 commits):

```
$ autocto architecture ../ai-ecosystem/personal-llm
Cycles: 0

God files: 5
path                                size  fan_in  fan_out
----------------------------------  ----  ------  -------
src/personal_llm/memory/store.py    427   20      2
src/personal_llm/interfaces/cli.py  318   2       18
src/personal_llm/interfaces/api.py  257   1       14
evals/run_evals.py                  386   1       7
scripts/merge_stores.py             358   0       4

Layering violations: 0 (pass --layers a,b,c to check)
```

`memory/store.py` is flagged because twenty files import it and it is over 400 lines: big, and
everyone depends on it. The layering check only runs when you pass `--layers`; there is no
universal default order, so without it the tool skips the check instead of inventing one.

## Migration planner on a worked proposal

Unlike the other four analyzers, this one has no "scan a real repo" mode -
its input is a proposal you write, not something `analyze_repo` discovers.
So instead of pointing it at a repo, this worked example describes a
duplication that existed in autocto's own tree when it was captured
(2026-09): `duplicates.py`, `maintenance_cost.py`, and `architectural_debt.py`
each defined an identical `_iter_source_files`/`_SKIP_DIR_NAMES` pair. Since
then the constant moved to `src/autocto/walk.py` (v0.2.0), while each module
still has its own `_iter_source_files` (checked 2026-11-13 with
`grep -n _iter_source_files src/autocto/*.py`). Treat the proposal as an
illustration of the input and output shape, not as a plan still to be applied.

Command:

```bash
python -c "
from autocto.migration_plan import ProposedChange, generate_migration_plan

changes = [
    ProposedChange(
        id='extract-shared-file-walker',
        description='Extract the duplicated _iter_source_files/_SKIP_DIR_NAMES pair out of duplicates.py, maintenance_cost.py, and architectural_debt.py into one shared module',
        files=('src/autocto/_repo_walk.py',),
        risk='medium',
    ),
    ProposedChange(
        id='migrate-duplicates',
        description='Point duplicates.py at the shared walker instead of its own copy',
        files=('src/autocto/duplicates.py',),
        depends_on=('extract-shared-file-walker',),
        risk='low',
    ),
    ProposedChange(
        id='migrate-maintenance-cost',
        description='Point maintenance_cost.py at the shared walker',
        files=('src/autocto/maintenance_cost.py',),
        depends_on=('extract-shared-file-walker',),
        risk='low',
    ),
    ProposedChange(
        id='migrate-architectural-debt',
        description='Point architectural_debt.py at the shared walker',
        files=('src/autocto/architectural_debt.py',),
        depends_on=('extract-shared-file-walker', 'migrate-maintenance-cost'),
        risk='medium',
    ),
    ProposedChange(
        id='delete-dead-walkers',
        description='Delete the now-unused per-module _iter_source_files/_SKIP_DIR_NAMES copies',
        depends_on=('migrate-duplicates', 'migrate-maintenance-cost', 'migrate-architectural-debt'),
        risk='high',
    ),
]

print(generate_migration_plan('Consolidate duplicated file-walking logic', changes,
    rationale='duplicates.py, maintenance_cost.py, and architectural_debt.py each define an '
              'identical _iter_source_files/_SKIP_DIR_NAMES pair today (verified by grep) - this '
              'plan removes the duplication for real.'))
"
```

Output (real, generated by the command above, not hand-written):

```
# Migration Plan: Consolidate duplicated file-walking logic

## Rationale

duplicates.py, maintenance_cost.py, and architectural_debt.py each define an identical _iter_source_files/_SKIP_DIR_NAMES pair today (verified by grep) - this plan removes the duplication for real.

## Steps

Ordered so every change's dependencies land first (`autocto.migration_plan.order_changes`, topological sort). Execute top to bottom; do not skip ahead.

### 1. extract-shared-file-walker - Extract the duplicated _iter_source_files/_SKIP_DIR_NAMES pair out of duplicates.py, maintenance_cost.py, and architectural_debt.py into one shared module

**Risk:** medium
**Files:** src/autocto/_repo_walk.py
**Verify:** Run the full test suite; smoke-test the affected feature manually.

### 2. migrate-duplicates - Point duplicates.py at the shared walker instead of its own copy

**Risk:** low
**Files:** src/autocto/duplicates.py
**Depends on:** extract-shared-file-walker
**Verify:** Run the affected tests; confirm no other callers reference the old shape.

### 3. migrate-maintenance-cost - Point maintenance_cost.py at the shared walker

**Risk:** low
**Files:** src/autocto/maintenance_cost.py
**Depends on:** extract-shared-file-walker
**Verify:** Run the affected tests; confirm no other callers reference the old shape.

### 4. migrate-architectural-debt - Point architectural_debt.py at the shared walker

**Risk:** medium
**Files:** src/autocto/architectural_debt.py
**Depends on:** extract-shared-file-walker, migrate-maintenance-cost
**Verify:** Run the full test suite; smoke-test the affected feature manually.

### 5. delete-dead-walkers - Delete the now-unused per-module _iter_source_files/_SKIP_DIR_NAMES copies

**Risk:** high
**Depends on:** migrate-duplicates, migrate-maintenance-cost, migrate-architectural-debt
**Verify:** Run the full test suite; stage the change behind a flag or on a branch and get a second reviewer before merging.

## Rollback

Each step above should be its own commit (or PR) so any single step can be reverted independently without undoing steps that landed after it, as long as later steps did not themselves depend on it - check the "Depends on" list above before reverting a step other changes rely on.

## Reviewer instructions

This is a PLAN ONLY - nothing has been changed. A human executes each step, runs its verification, and only then moves to the next.
```

The topological sort put `extract-shared-file-walker` first (nothing depends
on it) and `delete-dead-walkers` last (it depends on all three migrations),
exactly as declared - not hand-ordered. This plan itself is not applied by
this repo; it is only a worked demonstration of the generator.
