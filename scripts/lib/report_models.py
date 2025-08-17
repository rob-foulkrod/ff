"""Data models for weekly report generation.

The legacy monolithic implementation has been removed; this dataclass
is consumed by the modular collection + formatter pipeline.
"""
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
    wr_rows: list[list[str]]  # simplified weekly results rows
    preview: list[dict]
    streak_rows: list[list[str]]
    playoff_rows: int
    meta_rows: list[list[str]]  # key/value pairs
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
        }
