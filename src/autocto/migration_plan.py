"""Migration-plan generator: turns a redesign proposal into an ordered, verifiable plan.

README.md "Planned analyzers" item 5 / PROJECT-GENESIS.md section 9 Tier 4 item 32.
PROJECT-GENESIS.md section 5: AutoCTO "proposes redesigns with migration plans" - the
other four analyzers (hotspots, duplicates, maintenance-cost, architectural-debt) only
detect problems; this is the first module that turns a stated intent (a redesign
proposal: a set of changes, each with what it touches and what it depends on) into a
document a human can actually execute and verify against, one step at a time.

This is a template generator, not a code-writer: it takes a `ProposedChange` list a human
(or an LLM step upstream of this, out of scope here) has already authored, orders it by
dependency (each change's `depends_on` must land first), and renders a numbered markdown
plan with a per-step verification instruction derived from the change's declared risk. It
never edits, generates, or applies any code itself - same detect/propose-only contract as
every other autocto analyzer and second-brain's merge_proposals.py/idea_collisions.py.

No git, no subprocess, no filesystem walk: unlike hotspots.py/duplicates.py/
maintenance_cost.py/architectural_debt.py, this module has no "real repo" half at all -
its only input is the proposal itself, so it is pure end to end.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

_RISK_VERIFICATION = {
    "low": "Run the affected tests; confirm no other callers reference the old shape.",
    "medium": "Run the full test suite; smoke-test the affected feature manually.",
    "high": "Run the full test suite; stage the change behind a flag or on a branch and "
    "get a second reviewer before merging.",
}
_DEFAULT_RISK = "low"


class CycleError(ValueError):
    """Raised when a proposal's depends_on edges form a cycle - no valid order exists."""


@dataclass(frozen=True)
class ProposedChange:
    id: str
    description: str
    files: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    risk: str = _DEFAULT_RISK


@dataclass(frozen=True)
class MigrationStep:
    change: ProposedChange
    order: int
    verification: str


@dataclass(frozen=True)
class MigrationPlan:
    title: str
    rationale: str
    steps: tuple[MigrationStep, ...]


def order_changes(changes: Sequence[ProposedChange]) -> list[ProposedChange]:
    """Topological sort by `depends_on`, Kahn's algorithm: every dependency lands before
    the change that needs it.

    Ties (multiple changes simultaneously ready) break on `id` ascending, so the order is
    deterministic regardless of input order - the same discipline duplicates.py's
    `find_duplicates` and merge_proposals.py's tie-break rule use. Raises `CycleError`
    listing every change still unresolved if `depends_on` edges form a cycle (or
    reference an id not in `changes` - such a change can never become ready either).
    """
    by_id = {c.id: c for c in changes}
    remaining_deps = {c.id: set(c.depends_on) for c in changes}
    ordered: list[ProposedChange] = []
    resolved: set[str] = set()

    while remaining_deps:
        ready = sorted(
            cid for cid, deps in remaining_deps.items() if deps <= resolved
        )
        if not ready:
            stuck = ", ".join(sorted(remaining_deps))
            raise CycleError(
                f"migration plan has an unresolvable dependency cycle (or a depends_on "
                f"referencing an unknown id) among: {stuck}"
            )
        for cid in ready:
            ordered.append(by_id[cid])
            resolved.add(cid)
            del remaining_deps[cid]

    return ordered


def build_migration_plan(
    title: str, changes: Sequence[ProposedChange], *, rationale: str = ""
) -> MigrationPlan:
    """Order `changes` and attach a numbered, risk-derived verification step to each."""
    ordered = order_changes(changes)
    steps = tuple(
        MigrationStep(
            change=change,
            order=i,
            verification=_RISK_VERIFICATION.get(change.risk, _RISK_VERIFICATION[_DEFAULT_RISK]),
        )
        for i, change in enumerate(ordered, start=1)
    )
    return MigrationPlan(title=title, rationale=rationale, steps=steps)


def render_migration_plan_markdown(plan: MigrationPlan) -> str:
    """Deterministic markdown for one migration plan - no timestamps, no randomness."""
    lines: list[str] = []
    lines.append(f"# Migration Plan: {plan.title}")
    lines.append("")
    if plan.rationale:
        lines.append("## Rationale")
        lines.append("")
        lines.append(plan.rationale)
        lines.append("")
    lines.append("## Steps")
    lines.append("")
    lines.append(
        "Ordered so every change's dependencies land first "
        "(`autocto.migration_plan.order_changes`, topological sort). Execute top to "
        "bottom; do not skip ahead."
    )
    lines.append("")
    for step in plan.steps:
        change = step.change
        lines.append(f"### {step.order}. {change.id} - {change.description}")
        lines.append("")
        lines.append(f"**Risk:** {change.risk}")
        if change.files:
            lines.append(f"**Files:** {', '.join(change.files)}")
        if change.depends_on:
            lines.append(f"**Depends on:** {', '.join(change.depends_on)}")
        lines.append(f"**Verify:** {step.verification}")
        lines.append("")
    lines.append("## Rollback")
    lines.append("")
    lines.append(
        "Each step above should be its own commit (or PR) so any single step can be "
        "reverted independently without undoing steps that landed after it, as long as "
        "later steps did not themselves depend on it - check the \"Depends on\" list "
        "above before reverting a step other changes rely on."
    )
    lines.append("")
    lines.append("## Reviewer instructions")
    lines.append("")
    lines.append(
        "This is a PLAN ONLY - nothing has been changed. A human executes each step, "
        "runs its verification, and only then moves to the next."
    )
    lines.append("")
    return "\n".join(lines)


def generate_migration_plan(
    title: str, changes: Sequence[ProposedChange], *, rationale: str = ""
) -> str:
    """Convenience wrapper: build then render in one call."""
    return render_migration_plan_markdown(build_migration_plan(title, changes, rationale=rationale))
