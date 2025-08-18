from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests

from ff.report.constants import SCHEMA_VERSION
from ff.report.collect import (
    build_weekly_context as _build_weekly_context_mod,
    _resolve_league_for_season as _resolve_league_for_season_mod,
)
from ff.report.formatters import (
    format_markdown as _format_markdown_mod,
    format_json as _format_json_mod,
)

LEAGUE_ID = os.environ.get("SLEEPER_LEAGUE_ID", "1180276953741729792")
SPORT = os.environ.get("SLEEPER_SPORT", "nfl")


def _pretty(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _iter_weeks(
    *,
    start_week: int,
    last_regular_week: int,
    from_week: int | None,
    to_week: int | None,
    include_all: bool,
) -> Iterable[int]:
    if not (include_all or from_week is not None or to_week is not None):
        return []
    w1 = from_week if from_week is not None else start_week
    w2 = to_week if to_week is not None else last_regular_week
    if w1 > w2:
        w1, w2 = w2, w1
    w1 = max(start_week, w1)
    w2 = min(last_regular_week, w2)
    return range(w1, w2 + 1)


def generate_weekly_history_report(
    *,
    league_id: str = LEAGUE_ID,
    season: str | int | None = None,
    report_week: int | None = None,
    sport: str = SPORT,
    out_dir: str = "reports/weekly",
    output_formats: Sequence[str] | None = None,
    json_pretty: bool = True,
    verbose: bool = False,
    dry_run: bool = False,
) -> dict:
    formats = list(output_formats) if output_formats else ["markdown"]
    ctx = _build_weekly_context_mod(
        league_id=league_id, season=season, report_week=report_week, sport=sport
    )
    dest_dir = Path(out_dir) / ctx.season
    dest_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict[str, Any]] = {}
    for fmt in formats:
        fmt_norm = fmt.lower()
        if fmt_norm in {"md", "markdown"}:
            content = _format_markdown_mod(ctx)
            path = dest_dir / f"week-{ctx.report_week:02d}.md"
        elif fmt_norm == "json":
            content = _format_json_mod(ctx, SCHEMA_VERSION, pretty=json_pretty)
            path = dest_dir / f"week-{ctx.report_week:02d}.json"
        else:
            raise ValueError(f"Unsupported format: {fmt}")
        if not dry_run:
            path.write_text(content, encoding="utf-8")
        if verbose:
            print(f"[weekly_report] wrote {fmt_norm} -> {path} ({len(content)} bytes)")
        key = "markdown" if fmt_norm in {"md", "markdown"} else fmt_norm
        results[key] = {
            "path": str(path),
            "bytes": len(content),
            "league_id": ctx.league_id,
            "season": ctx.season,
            "report_week": ctx.report_week,
            "written": not dry_run,
        }

    primary_fmt = "markdown" if "markdown" in results else next(iter(results))
    return {
        "formats": results,
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "league_id": ctx.league_id,
            "season": ctx.season,
            "report_week": ctx.report_week,
        },
        "path": results[primary_fmt]["path"],
        "written": not dry_run,
        "entries": {
            "standings": len(ctx.standings),
            "head_to_head": len(ctx.h2h),
            "preview": len(ctx.preview),
        },
    }


def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    parser = argparse.ArgumentParser(
        description="Generate Sleeper weekly history report (machine-readable markdown)"
    )
    parser.add_argument(
        "--league-id", default=LEAGUE_ID, help="Sleeper league_id (default from env)"
    )
    parser.add_argument(
        "--season",
        type=str,
        default=None,
        help="Season to generate (e.g., 2024). If omitted, current league season is used.",
    )
    parser.add_argument(
        "--report-week",
        type=int,
        default=None,
        help="Week to report (defaults to last completed regular-season week)",
    )
    parser.add_argument("--sport", default=SPORT, help="Sport key (default nfl)")
    parser.add_argument("--out-dir", default="reports/weekly", help="Output directory")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging to stdout")
    parser.add_argument(
        "--dry-run", action="store_true", help="Build report but do not write files"
    )
    parser.add_argument(
        "--all", action="store_true", help="Generate reports for the entire regular season"
    )
    parser.add_argument(
        "--from-week", type=int, default=None, help="Start week (inclusive) for range generation"
    )
    parser.add_argument(
        "--to-week", type=int, default=None, help="End week (inclusive) for range generation"
    )
    parser.add_argument(
        "--formats",
        default="markdown",
        help="Comma-separated list of output formats (markdown,json)",
    )
    parser.set_defaults(json_pretty=True)
    parser.add_argument(
        "--json-pretty",
        dest="json_pretty",
        action="store_true",
        help="(Default) Pretty-print JSON output when using --formats json",
    )
    parser.add_argument(
        "--json-compact",
        dest="json_pretty",
        action="store_false",
        help="Use compact JSON (no whitespace)",
    )
    args = parser.parse_args(argv)
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]

    if args.all or args.from_week is not None or args.to_week is not None:
        try:
            league = _resolve_league_for_season_mod(args.league_id, args.season)
            settings = league.get("settings", {}) or {}
            start_week = int(settings.get("start_week", 1) or 1)
            playoff_week_start = int(settings.get("playoff_week_start", 15) or 15)
            last_regular = playoff_week_start - 1
            weeks = list(
                _iter_weeks(
                    start_week=start_week,
                    last_regular_week=last_regular,
                    from_week=args.from_week,
                    to_week=args.to_week,
                    include_all=args.all,
                )
            )
            if not weeks:
                print("No weeks selected for generation.")
                return 0
            print(
                f"Generating reports for weeks {weeks[0]}-{weeks[-1]} (season {league.get('season')}) ..."
            )
            failures = 0
            for wk in weeks:
                try:
                    summary = generate_weekly_history_report(
                        league_id=args.league_id,
                        season=args.season,
                        report_week=wk,
                        sport=args.sport,
                        out_dir=args.out_dir,
                        output_formats=formats,
                        json_pretty=args.json_pretty,
                        verbose=args.verbose,
                        dry_run=args.dry_run,
                    )
                    for fmt_name, info in summary["formats"].items():
                        print(f"OK  Week {wk:02d} [{fmt_name}] -> {info['path']}")
                except requests.HTTPError as e:  # pragma: no cover
                    failures += 1
                    print(f"HTTPError on week {wk}: {e}", file=sys.stderr)
                except (OSError, ValueError) as e:  # pragma: no cover
                    failures += 1
                    print(f"Error on week {wk}: {e}", file=sys.stderr)
            if failures:
                print(f"Completed with {failures} failures.")
                return 1
            print("All reports generated successfully.")
            return 0
        except requests.HTTPError as e:  # pragma: no cover
            print(f"HTTPError: {e}", file=sys.stderr)
            return 1
        except (OSError, ValueError) as e:  # pragma: no cover
            print(f"Error: {e}", file=sys.stderr)
            return 1

    try:
        summary = generate_weekly_history_report(
            league_id=args.league_id,
            season=args.season,
            report_week=args.report_week,
            sport=args.sport,
            out_dir=args.out_dir,
            output_formats=formats,
            json_pretty=args.json_pretty,
            verbose=args.verbose,
            dry_run=args.dry_run,
        )
        print(_pretty(summary))
        for fmt_name, info in summary["formats"].items():
            print(f"Wrote [{fmt_name}]: {info['path']}")
        return 0
    except requests.HTTPError as e:  # pragma: no cover
        print(f"HTTPError: {e}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as e:  # pragma: no cover
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
