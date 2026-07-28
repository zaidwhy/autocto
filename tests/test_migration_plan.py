"""Migration-plan generator: topological ordering, cycle detection, deterministic markdown."""

from __future__ import annotations

import pytest

from autocto.migration_plan import (
    CycleError,
    MigrationPlan,
    ProposedChange,
    build_migration_plan,
    generate_migration_plan,
    order_changes,
    render_migration_plan_markdown,
)


def test_order_changes_empty_returns_empty():
    assert order_changes([]) == []


def test_order_changes_no_dependencies_keeps_id_order():
    changes = [ProposedChange("b", "do b"), ProposedChange("a", "do a")]
    ordered = order_changes(changes)
    assert [c.id for c in ordered] == ["a", "b"]


def test_order_changes_respects_a_simple_dependency():
    changes = [
        ProposedChange("second", "do second", depends_on=("first",)),
        ProposedChange("first", "do first"),
    ]
    ordered = order_changes(changes)
    assert [c.id for c in ordered] == ["first", "second"]


def test_order_changes_respects_a_chain():
    changes = [
        ProposedChange("c", "do c", depends_on=("b",)),
        ProposedChange("a", "do a"),
        ProposedChange("b", "do b", depends_on=("a",)),
    ]
    ordered = order_changes(changes)
    assert [c.id for c in ordered] == ["a", "b", "c"]


def test_order_changes_ties_break_on_id_ascending():
    # x, y both ready immediately (no deps); z depends on both.
    changes = [
        ProposedChange("z", "do z", depends_on=("x", "y")),
        ProposedChange("y", "do y"),
        ProposedChange("x", "do x"),
    ]
    ordered = order_changes(changes)
    assert [c.id for c in ordered] == ["x", "y", "z"]


def test_order_changes_raises_cycle_error_on_direct_cycle():
    changes = [
        ProposedChange("a", "do a", depends_on=("b",)),
        ProposedChange("b", "do b", depends_on=("a",)),
    ]
    with pytest.raises(CycleError):
        order_changes(changes)


def test_order_changes_raises_cycle_error_on_unknown_dependency():
    changes = [ProposedChange("a", "do a", depends_on=("nonexistent",))]
    with pytest.raises(CycleError):
        order_changes(changes)


def test_build_migration_plan_assigns_sequential_order():
    changes = [ProposedChange("a", "do a"), ProposedChange("b", "do b", depends_on=("a",))]
    plan = build_migration_plan("Test plan", changes)
    assert [s.order for s in plan.steps] == [1, 2]
    assert [s.change.id for s in plan.steps] == ["a", "b"]


def test_build_migration_plan_verification_derived_from_risk():
    changes = [
        ProposedChange("a", "low risk change", risk="low"),
        ProposedChange("b", "high risk change", risk="high"),
    ]
    plan = build_migration_plan("Test plan", changes)
    assert "affected tests" in plan.steps[0].verification
    assert "second reviewer" in plan.steps[1].verification


def test_build_migration_plan_unknown_risk_falls_back_to_low():
    changes = [ProposedChange("a", "mystery risk", risk="unknown-level")]
    plan = build_migration_plan("Test plan", changes)
    assert plan.steps[0].verification == build_migration_plan(
        "x", [ProposedChange("a", "y", risk="low")]
    ).steps[0].verification


def test_render_includes_title_rationale_and_steps():
    changes = [ProposedChange("a", "rename module", files=("src/a.py",), risk="medium")]
    plan = build_migration_plan("Rename module", changes, rationale="Clearer naming.")
    markdown = render_migration_plan_markdown(plan)
    assert "Migration Plan: Rename module" in markdown
    assert "Clearer naming." in markdown
    assert "1. a - rename module" in markdown
    assert "src/a.py" in markdown
    assert "Risk:** medium" in markdown
    assert "PLAN ONLY" in markdown


def test_render_omits_rationale_section_when_empty():
    plan = build_migration_plan("No rationale", [ProposedChange("a", "do a")])
    markdown = render_migration_plan_markdown(plan)
    assert "## Rationale" not in markdown


def test_render_shows_depends_on_when_present():
    changes = [ProposedChange("a", "do a"), ProposedChange("b", "do b", depends_on=("a",))]
    plan = build_migration_plan("Test plan", changes)
    markdown = render_migration_plan_markdown(plan)
    assert "Depends on:** a" in markdown


def test_render_omits_depends_on_when_absent():
    plan = build_migration_plan("Test plan", [ProposedChange("a", "do a")])
    markdown = render_migration_plan_markdown(plan)
    assert "Depends on:**" not in markdown


def test_generate_migration_plan_is_build_then_render():
    changes = [ProposedChange("a", "do a")]
    assert generate_migration_plan("Test plan", changes) == render_migration_plan_markdown(
        build_migration_plan("Test plan", changes)
    )


def test_render_is_deterministic_across_calls():
    changes = [
        ProposedChange("b", "do b", depends_on=("a",), risk="high"),
        ProposedChange("a", "do a", files=("x.py", "y.py")),
    ]
    plan1 = build_migration_plan("Determinism check", changes, rationale="because")
    plan2 = build_migration_plan("Determinism check", changes, rationale="because")
    assert render_migration_plan_markdown(plan1) == render_migration_plan_markdown(plan2)
