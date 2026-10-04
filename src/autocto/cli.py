"""Command-line entrypoint for autocto.

    autocto hotspots [REPO] [--limit N] [--json]
    autocto duplicates [REPO] [--threshold F] [--limit N] [--json]
    autocto maintenance [REPO] [--limit N] [--json]
    autocto architecture [REPO] [--layers a,b,c] [--json]
    autocto report [REPO] [--json]      # all four analyzers in one pass
    autocto plan FILE [--json]          # order a proposed redesign into a migration plan

REPO defaults to the current directory. Every analyzer is read-only: it inspects git
history and file contents, never writes to the target repo. `--json` prints one JSON
object per command instead of the human-readable table, for piping into other tools.

`plan` is the exception: it reads a JSON proposal (title, optional rationale, and a list
of changes with id, description, files, depends_on, risk), orders the changes so every
dependency lands first, and prints markdown (or the ordered steps with --json). It never
touches a repo.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

from . import architectural_debt, duplicates, hotspots, maintenance_cost, migration_plan

DEFAULT_LIMIT = 10


def _to_jsonable(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def _print_json(obj) -> None:
    print(json.dumps(_to_jsonable(obj), indent=2))


def _print_table(rows: list, columns: list[str]) -> None:
    if not rows:
        print("(no results)")
        return
    widths = [max(len(c), max(len(str(getattr(r, c))) for r in rows)) for c in columns]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(getattr(r, c)).ljust(w) for c, w in zip(columns, widths)))


def cmd_hotspots(args: argparse.Namespace) -> int:
    results = hotspots.analyze_repo(args.repo)[: args.limit]
    if args.json:
        _print_json(results)
    else:
        _print_table(results, ["path", "churn", "complexity", "score"])
    return 0


def cmd_duplicates(args: argparse.Namespace) -> int:
    results = duplicates.analyze_repo(args.repo, threshold=args.threshold)[: args.limit]
    if args.json:
        _print_json(results)
    else:
        _print_table(results, ["path_a", "path_b", "similarity"])
    return 0


def cmd_maintenance(args: argparse.Namespace) -> int:
    results = maintenance_cost.analyze_repo(args.repo)[: args.limit]
    if args.json:
        _print_json(results)
    else:
        _print_table(results, ["path", "size", "churn", "fan_in", "cost"])
    return 0


def cmd_architecture(args: argparse.Namespace) -> int:
    layer_order = args.layers.split(",") if args.layers else None
    report = architectural_debt.analyze_repo(args.repo, layer_order=layer_order)
    if args.json:
        _print_json(report)
        return 0
    print(f"Cycles: {len(report.cycles)}")
    for cycle in report.cycles[:5]:
        print("  " + " -> ".join(cycle))
    print(f"\nGod files: {len(report.god_files)}")
    _print_table(report.god_files[:10], ["path", "size", "fan_in", "fan_out"])
    print(f"\nLayering violations: {len(report.layering_violations)}"
          + ("" if layer_order else " (pass --layers a,b,c to check)"))
    _print_table(report.layering_violations[:10], ["importer", "importee", "importer_layer", "importee_layer"])
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    layer_order = args.layers.split(",") if args.layers else None
    result = {
        "hotspots": hotspots.analyze_repo(args.repo)[:5],
        "duplicates": duplicates.analyze_repo(args.repo)[:5],
        "maintenance": maintenance_cost.analyze_repo(args.repo)[:5],
        "architecture": architectural_debt.analyze_repo(args.repo, layer_order=layer_order),
    }
    if args.json:
        _print_json(result)
        return 0
    print(f"=== autocto report: {args.repo} ===\n")
    print("Top 5 hotspots (churn x complexity):")
    _print_table(result["hotspots"], ["path", "churn", "complexity", "score"])
    print("\nTop 5 duplicate pairs:")
    _print_table(result["duplicates"], ["path_a", "path_b", "similarity"])
    print("\nTop 5 by maintenance cost:")
    _print_table(result["maintenance"], ["path", "size", "churn", "fan_in", "cost"])
    arch = result["architecture"]
    print(f"\nArchitecture: {len(arch.cycles)} cycle(s), {len(arch.god_files)} god file(s), "
          f"{len(arch.layering_violations)} layering violation(s)")
    return 0


class _ProposalError(ValueError):
    """The proposal file is not a valid migration proposal."""


def _load_proposal(path: Path) -> tuple[str, str, list[migration_plan.ProposedChange]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _ProposalError(f"{path} is not valid JSON ({exc})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("title"), str) or not data["title"]:
        raise _ProposalError('the proposal needs a "title" string')
    raw_changes = data.get("changes")
    if not isinstance(raw_changes, list) or not raw_changes:
        raise _ProposalError('the proposal needs a non-empty "changes" list')

    changes: list[migration_plan.ProposedChange] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_changes, start=1):
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            raise _ProposalError(f'change {i} needs an "id" string')
        if raw["id"] in seen:
            raise _ProposalError(f'duplicate change id "{raw["id"]}"')
        seen.add(raw["id"])
        if not isinstance(raw.get("description"), str) or not raw["description"]:
            raise _ProposalError(f'change "{raw["id"]}" needs a "description" string')
        risk = raw.get("risk", migration_plan.DEFAULT_RISK)
        if risk not in migration_plan.RISK_LEVELS:
            raise _ProposalError(
                f'change "{raw["id"]}" has risk {risk!r}; use one of {", ".join(migration_plan.RISK_LEVELS)}'
            )
        lists = {}
        for key in ("files", "depends_on"):
            value = raw.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise _ProposalError(f'change "{raw["id"]}": "{key}" must be a list of strings')
            lists[key] = tuple(value)
        changes.append(
            migration_plan.ProposedChange(
                id=raw["id"],
                description=raw["description"],
                files=lists["files"],
                depends_on=lists["depends_on"],
                risk=risk,
            )
        )
    rationale = data.get("rationale", "")
    if not isinstance(rationale, str):
        raise _ProposalError('"rationale" must be a string')
    return data["title"], rationale, changes


def cmd_plan(args: argparse.Namespace) -> int:
    try:
        title, rationale, changes = _load_proposal(args.proposal)
        plan = migration_plan.build_migration_plan(title, changes, rationale=rationale)
    except (_ProposalError, migration_plan.CycleError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        _print_json(plan)
    else:
        print(migration_plan.render_migration_plan_markdown(plan), end="")
    return 0


def _add_repo_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("repo", nargs="?", type=Path, default=Path("."), help="Path to the repo (default: current directory)")
    p.add_argument("--json", action="store_true", help="print JSON instead of a table")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autocto", description=(__doc__ or "").split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("hotspots", help="rank files by churn x complexity")
    _add_repo_arg(p)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.set_defaults(func=cmd_hotspots)

    p = sub.add_parser("duplicates", help="rank file pairs by token-shingle similarity")
    _add_repo_arg(p)
    p.add_argument("--threshold", type=float, default=duplicates.DEFAULT_SIMILARITY_THRESHOLD)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.set_defaults(func=cmd_duplicates)

    p = sub.add_parser("maintenance", help="rank files by size x churn x (1 + fan_in)")
    _add_repo_arg(p)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.set_defaults(func=cmd_maintenance)

    p = sub.add_parser("architecture", help="cycles, god files, and (with --layers) layering violations")
    _add_repo_arg(p)
    p.add_argument("--layers", help="comma-separated top-level dirs, most-foundational first")
    p.set_defaults(func=cmd_architecture)

    p = sub.add_parser("report", help="run all four analyzers and print a summary")
    _add_repo_arg(p)
    p.add_argument("--layers", help="comma-separated top-level dirs, most-foundational first")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("plan", help="order a JSON redesign proposal into a migration plan (markdown)")
    p.add_argument("proposal", type=Path, help="JSON file: title, rationale, changes[id, description, files, depends_on, risk]")
    p.add_argument("--json", action="store_true", help="print the ordered steps as JSON instead of markdown")
    p.set_defaults(func=cmd_plan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    target = getattr(args, "repo", None) or getattr(args, "proposal", None)
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 2
    try:
        return args.func(args)
    except subprocess.CalledProcessError as exc:
        if exc.cmd and exc.cmd[0] != "git":
            raise
        print(f"error: {args.repo} is not a git repository ({args.command} reads git history)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
