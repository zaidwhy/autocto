---
name: Feature request
about: Propose a new analyzer or a change to an existing one
title: "[feature] "
labels: enhancement
---

## What problem does this solve

What engineering risk or signal is missing today, and why the existing
analyzers (`hotspots.py`, `duplicates.py`) or the roadmap items (maintenance-
cost estimator, architectural-debt report, migration-plan generator) don't
already cover it.

## Proposed approach

Sketch the pure-function-plus-`analyze_repo`-entry-point shape you'd expect
(see `CONTRIBUTING.md` for the pattern this repo follows). Note any inputs
it would need beyond what `git log --numstat` and file contents already
provide.

## Alternatives considered

Any simpler version of this that would get most of the value.

## Scope check

- [ ] This is analysis/reporting logic, not a code-writing or PR-opening
      feature (those belong to the `/github-pr` skill in the
      `github-pr-agent` project, not here).
- [ ] This can be implemented offline, with no API keys and no network
      access.
