"""Data models for weekly report generation (new package location)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class WeeklyContext:
    league_id: str
    season: str
    report_week: int
    same_season: bool
    start_week: int
    playoff_week_start: int
    playoff_teams: int
    state_week: int
    standings: list[dict]
    h2h: list[dict]
    wr_rows: list[list[str]]
    preview: list[dict]
    streak_rows: list[list[str]]
    playoff_rows: int
    # Added restored rich sections
    roster_directory: list[dict]
    division_standings: list[dict]  # each: {division_id, division_name, rows:[...]}
    playoff_standings: list[dict]  # ordered list of playoff seeding rows
    h2h_grid: list[list[str]]  # matrix with header row first
    meta_rows: list[list[str]]
    markdown_lines: list[str]

    def to_json_payload(self, schema_version: str) -> Dict[str, Any]:
        return {
            "schema_version": schema_version,
            "metadata": {k: v for k, v in self.meta_rows},
            "standings": self.standings,
            "head_to_head_week": self.h2h,
            "weekly_results_enriched_rows": self.wr_rows,
            "preview": self.preview,
            "streaks_table": self.streak_rows,
            "playoff_rows": self.playoff_rows,
            "roster_directory": self.roster_directory,
            "division_standings": self.division_standings,
            "playoff_standings": self.playoff_standings,
            "head_to_head_grid": self.h2h_grid,
        }
