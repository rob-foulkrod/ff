"""Generate weekly reports (markdown + json) for the 2024 season.

Usage (from project root, virtualenv active):
  python generate_2024_reports.py

Outputs written under: reports/weekly/2024/week-XX.(md|json)
Existing files will be overwritten.
"""
from __future__ import annotations

from pathlib import Path

from ff.report.collect import build_weekly_context
from ff.report.constants import SCHEMA_VERSION
from ff.report.formatters import format_markdown, format_json


BASE_LEAGUE_ID = "1180276953741729792"  # starting league id (will traverse to 2024)
SPORT = "nfl"
SEASON = 2024

OUTPUT_DIR = Path("reports/weekly/2024")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Build week 1 context first to discover playoff_week_start
    ctx1 = build_weekly_context(
        league_id=BASE_LEAGUE_ID,
        season=SEASON,
        report_week=1,
        sport=SPORT,
    )
    last_regular_week = ctx1.playoff_week_start - 1
    print(f"Detected playoff_week_start={ctx1.playoff_week_start}; generating weeks 1..{last_regular_week}")
    for wk in range(1, last_regular_week + 1):
        print(f"Generating week {wk:02d} ...", end="", flush=True)
        ctx = build_weekly_context(
            league_id=BASE_LEAGUE_ID,
            season=SEASON,
            report_week=wk,
            sport=SPORT,
        )
        md_path = OUTPUT_DIR / f"week-{wk:02d}.md"
        json_path = OUTPUT_DIR / f"week-{wk:02d}.json"
        md_path.write_text(format_markdown(ctx), encoding="utf-8")
        json_path.write_text(
            format_json(ctx, SCHEMA_VERSION, pretty=True), encoding="utf-8"
        )
        print(" done")
    print("All weeks generated.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
