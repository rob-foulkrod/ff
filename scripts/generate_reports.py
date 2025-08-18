"""Flexible report generator for Sleeper weekly reports.

Supports generating:
  * A single week (--week 3)
  * A numeric range (--range 1-4)
  * Explicit list of weeks (--weeks 1,3,7)
  * Full regular season (--all)

Delegates to the internal library so output stays consistent with the CLI
(`weekly-report`). This script is targeted for automation / GitHub Actions
where explicit control over weeks is useful.

Examples:
  python scripts/generate_reports.py --season 2024 --range 1-4 --formats markdown,json
  python scripts/generate_reports.py --season 2025 --weeks 1,2,3 --formats json --json-compact
  python scripts/generate_reports.py --season 2025 --all --formats markdown

Exit code is non‑zero if any requested week fails.
"""
from __future__ import annotations

import argparse
import sys

from ff.report.collect import _resolve_league_for_season as resolve_league
from ff.cli.weekly_report import generate_weekly_history_report  # type: ignore


def _parse_weeks(
    *,
    week: int | None,
    weeks_csv: str | None,
    range_expr: str | None,
    all_flag: bool,
    start_week: int,
    last_regular_week: int,
) -> list[int]:
    if all_flag:
        return list(range(start_week, last_regular_week + 1))
    weeks: set[int] = set()
    if week is not None:
        weeks.add(int(week))
    if weeks_csv:
        for part in weeks_csv.split(","):
            part = part.strip()
            if not part:
                continue
            weeks.add(int(part))
    if range_expr:
        if "-" not in range_expr:
            raise ValueError("--range must be like 1-4")
        a, b = range_expr.split("-", 1)
        a_i = int(a.strip())
        b_i = int(b.strip())
        if a_i > b_i:
            a_i, b_i = b_i, a_i
        for w in range(a_i, b_i + 1):
            weeks.add(w)
    filtered = [w for w in weeks if start_week <= w <= last_regular_week]
    return sorted(filtered)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description="Generate one or more weekly reports (automation)")
    p.add_argument("--league-id", default="1180276953741729792")
    p.add_argument("--sport", default="nfl")
    p.add_argument("--season", required=True, type=int)
    p.add_argument("--week", type=int, help="Single week to generate")
    p.add_argument(
        "--weeks", help="Comma separated explicit weeks (e.g., 1,2,5,9)")
    p.add_argument("--range", dest="range_expr", help="Inclusive week range (e.g., 1-4)")
    p.add_argument("--all", action="store_true", help="All regular season weeks")
    p.add_argument(
        "--out-dir", default="reports/weekly", help="Base output directory (default reports/weekly)"
    )
    p.add_argument(
        "--formats", default="markdown", help="Comma separated formats (markdown,json)"
    )
    p.add_argument(
        "--json-compact", action="store_true", help="Emit compact JSON (default pretty)"
    )
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    league = resolve_league(args.league_id, args.season)
    settings = league.get("settings", {}) or {}
    start_week = int(settings.get("start_week", 1) or 1)
    playoff_week_start = int(settings.get("playoff_week_start", 15) or 15)
    last_regular_week = playoff_week_start - 1

    weeks = _parse_weeks(
        week=args.week,
        weeks_csv=args.weeks,
        range_expr=args.range_expr,
        all_flag=args.all,
        start_week=start_week,
        last_regular_week=last_regular_week,
    )
    if not weeks:
        print("No weeks selected (after filtering). Nothing to do.")
        return 0

    fmts = [f.strip() for f in args.formats.split(",") if f.strip()]
    failures = 0
    for w in weeks:
        try:
            summary = generate_weekly_history_report(
                league_id=args.league_id,
                season=args.season,
                report_week=w,
                sport=args.sport,
                out_dir=args.out_dir,
                output_formats=fmts,
                json_pretty=not args.json_compact,
                verbose=args.verbose,
            )
            if args.verbose:
                print(summary)
            else:
                path_info = ", ".join(
                    f"{k}:{v['path']}" for k, v in summary["formats"].items()
                )
                print(f"Week {w:02d} -> {path_info}")
        except Exception as e:  # pragma: no cover - robustness (broad for automation surface)
            failures += 1
            print(f"ERROR week {w}: {e}", file=sys.stderr)
    if failures:
        print(f"Completed with {failures} failure(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
