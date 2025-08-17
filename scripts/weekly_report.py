"""Trimmed CLI wrapper for modular weekly report generation.

This script orchestrates the modular collection/formatting pipeline defined in
scripts.lib.report_collect and scripts.lib.report_formatters.
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from typing import Any, Sequence

import requests

# Ensure project root is on sys.path when executed directly
_THIS_DIR = os.path.dirname(__file__)
_PROJ_ROOT = os.path.dirname(_THIS_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from scripts.lib.constants import SCHEMA_VERSION  # type: ignore  # noqa: E402
from scripts.lib.report_collect import (  # noqa: E402
    build_weekly_context as _build_weekly_context_mod,
    _resolve_league_for_season as _resolve_league_for_season_mod,  # reuse for range bounds
)
from scripts.lib.report_formatters import (  # noqa: E402
    format_markdown as _format_markdown_mod,
    format_json as _format_json_mod,
)

LEAGUE_ID = os.environ.get("SLEEPER_LEAGUE_ID", "1180276953741729792")
SPORT = os.environ.get("SLEEPER_SPORT", "nfl")


def _pretty(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


# ---------- streaks helpers ----------


def generate_weekly_history_report(
    league_id: str = LEAGUE_ID,
    season: str | int | None = None,
    report_week: int | None = None,
    sport: str = SPORT,
    out_dir: str = "reports/weekly",
    *,
    output_formats: Sequence[str] | None = None,
    json_pretty: bool = False,
    verbose: bool = False,
    dry_run: bool = False,
) -> dict:
    """Generate a weekly history report using the modular pipeline only."""
    if output_formats is None:
        output_formats = ["markdown"]
    ctx = _build_weekly_context_mod(
        league_id=league_id, season=season, report_week=report_week, sport=sport
    )
    dest_dir = os.path.join(out_dir, ctx.season)
    os.makedirs(dest_dir, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    for fmt in output_formats:
        f = fmt.lower()
        if f in {"md", "markdown"}:
            content = _format_markdown_mod(ctx)
            path = os.path.join(dest_dir, f"week-{ctx.report_week:02d}.md")
        elif f == "json":
            content = _format_json_mod(ctx, SCHEMA_VERSION, pretty=json_pretty)
            path = os.path.join(dest_dir, f"week-{ctx.report_week:02d}.json")
        else:
            raise ValueError(f"Unsupported format: {fmt}")
        if not dry_run:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        if verbose:
            print(f"[weekly_report][mod] wrote {fmt} -> {path} ({len(content)} bytes)")
        results[f if f != "md" else "markdown"] = {
            "path": path,
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


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument(
        "--json-pretty", action="store_true", help="Pretty-print JSON output when using --formats json"
    )
    args = parser.parse_args(argv)
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    # Range or single?
    if args.all or args.from_week is not None or args.to_week is not None:
        try:
            league = _resolve_league_for_season_mod(args.league_id, args.season)
            settings = league.get("settings", {}) or {}
            start_week = int(settings.get("start_week", 1) or 1)
            playoff_week_start = int(settings.get("playoff_week_start", 15) or 15)
            last_regular = playoff_week_start - 1
            w1 = args.from_week if args.from_week is not None else start_week
            w2 = args.to_week if args.to_week is not None else last_regular
            if w1 > w2:
                w1, w2 = w2, w1
            w1 = max(start_week, w1)
            w2 = min(last_regular, w2)
            print(f"Generating reports for weeks {w1}-{w2} (season {league.get('season')}) ...")
            failures = 0
            for wk in range(w1, w2 + 1):
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
                except requests.HTTPError as e:
                    failures += 1
                    print(f"HTTPError on week {wk}: {e}", file=sys.stderr)
                    if e.response is not None:
                        try:
                            print(_pretty(e.response.json()), file=sys.stderr)
                        except Exception:
                            print(e.response.text[:2000], file=sys.stderr)
                except Exception as e:  # pragma: no cover - defensive
                    failures += 1
                    print(f"Error on week {wk}: {e}", file=sys.stderr)
            if failures:
                print(f"Completed with {failures} failures.")
                return 1
            print("All reports generated successfully.")
            return 0
        except requests.HTTPError as e:
            print(f"HTTPError: {e}", file=sys.stderr)
            if e.response is not None:
                try:
                    print(_pretty(e.response.json()), file=sys.stderr)
                except Exception:
                    print(e.response.text[:2000], file=sys.stderr)
            return 1
        except Exception as e:  # pragma: no cover - defensive
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
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
        except requests.HTTPError as e:
            print(f"HTTPError: {e}", file=sys.stderr)
            if e.response is not None:
                try:
                    print(_pretty(e.response.json()), file=sys.stderr)
                except Exception:
                    print(e.response.text[:2000], file=sys.stderr)
            return 1
        except Exception as e:  # pragma: no cover - defensive
            print(f"Error: {e}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
