"""Command-line entrypoint for autocto.

    autocto hotspots [REPO] [--limit N] [--json]
    autocto duplicates [REPO] [--threshold F] [--limit N] [--json]
    autocto maintenance [REPO] [--limit N] [--json]
    autocto architecture [REPO] [--layers a,b,c] [--json]
    autocto report [REPO] [--json]      # all four analyzers in one pass

REPO defaults to the current directory. Every analyzer is read-only: it inspects git
history and file contents, never writes to the target repo. `--json` prints one JSON
object per command instead of the human-readable table, for piping into other tools.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from . import architectural_debt, duplicates, hotspots, maintenance_cost

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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.repo.exists():
        print(f"error: {args.repo} does not exist", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
