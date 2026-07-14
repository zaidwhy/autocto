# autocto

[![CI](https://github.com/syzayd/autocto/actions/workflows/ci.yml/badge.svg)](https://github.com/syzayd/autocto/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Automated CTO: repository health analyzers that read a codebase and its git
history and report where the real engineering risk lives.

Status: analyzers land one PR at a time via the ai-ecosystem Night Shift queue
(PROJECT-GENESIS.md section 9).

## Analyzers

1. **Bug-hotspot analyzer** (`src/autocto/hotspots.py`) - churn x complexity
   over `git log`; the files that change often AND are complex are where
   bugs cluster. `analyze_repo(repo_dir)` ranks a real repo's tracked files.
2. **Duplicated-logic detector** (`src/autocto/duplicates.py`) - token-shingle
   (Jaccard) similarity across files; `analyze_repo(repo_dir)` ranks a real repo's
   file pairs by duplication risk.
3. **Maintenance-cost estimator** - size x churn x dependency fan-in, with a
   documented formula.
4. **Architectural-debt report** - import cycles, god files, layering
   violations.
5. **Migration-plan generator** - turns a redesign proposal into an ordered,
   verifiable migration plan.

All analyzers are pure functions over repo data: offline, deterministic,
testable without API keys.
