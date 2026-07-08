# autocto

Automated CTO: repository health analyzers that read a codebase and its git
history and report where the real engineering risk lives.

Status: scaffold - the analyzers below are queued in the ai-ecosystem Night
Shift queue (PROJECT-GENESIS.md section 9) and land one PR at a time.

## Planned analyzers

1. **Bug-hotspot analyzer** - churn x complexity over `git log`; the files
   that change often AND are complex are where bugs cluster.
2. **Duplicated-logic detector** - token-shingle similarity across files.
3. **Maintenance-cost estimator** - size x churn x dependency fan-in, with a
   documented formula.
4. **Architectural-debt report** - import cycles, god files, layering
   violations.
5. **Migration-plan generator** - turns a redesign proposal into an ordered,
   verifiable migration plan.

All analyzers are pure functions over repo data: offline, deterministic,
testable without API keys.
