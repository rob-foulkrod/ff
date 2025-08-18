from __future__ import annotations
from dataclasses import dataclass
from typing import Any


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
    roster_directory: list[dict]
    division_standings: list[dict]
    playoff_standings: list[dict]
    h2h_grid: list[list[str]]
    meta_rows: list[list[str]]
    markdown_lines: list[str]
    # New enhancement sections
    all_play_records: list[dict] | None = None
    median_records: list[dict] | None = None
    margin_summary: dict | None = None
    division_power_week: list[dict] | None = None
    division_power_season: list[dict] | None = None
    teams_summary: list[dict] | None = None  # consolidated per-team metrics

    def to_json_payload(self, schema_version: str) -> dict[str, Any]:
        base = {
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
        if self.all_play_records is not None:
            base["all_play_records"] = self.all_play_records
        if self.median_records is not None:
            base["median_records"] = self.median_records
        if self.margin_summary is not None:
            base["margin_summary"] = self.margin_summary
        if self.division_power_week is not None:
            base["division_power_week"] = self.division_power_week
        if self.division_power_season is not None:
            base["division_power_season"] = self.division_power_season
        if self.teams_summary is not None:
            base["teams"] = self.teams_summary
        return base
