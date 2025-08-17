"""Collection & assembly for modular weekly report generation.

Provides a trimmed context (core pieces) suitable for multi-format output.
"""
from __future__ import annotations

import os
import datetime
from typing import Any
import requests

from scripts.lib.constants import SCHEMA_VERSION, WIN_PCT_PLACES, POINTS_PLACES
from scripts.lib.client import SleeperClient
from scripts.lib.compute import (
    group_rows as _compute_group_rows,
    compute_standings_with_groups as _compute_standings_with_groups_lib,
    compute_weekly_results as _compute_weekly_results_lib,
    current_streak as _compute_current_streak,
    longest_streaks as _compute_longest_streaks,
)
from scripts.lib.report_models import WeeklyContext
from scripts.lib.render import md_table as _md_table

BASE_URL = os.environ.get("SLEEPER_BASE_URL", "https://api.sleeper.com/v1")


def _make_client() -> SleeperClient:
    _RPM_LIMIT = os.environ.get("SLEEPER_RPM_LIMIT")
    _MIN_INTERVAL_MS = os.environ.get("SLEEPER_MIN_INTERVAL_MS")
    try:
        rpm = float(_RPM_LIMIT) if _RPM_LIMIT else None
    except ValueError:
        rpm = None
    try:
        min_ms = float(_MIN_INTERVAL_MS) if _MIN_INTERVAL_MS else None
    except ValueError:
        min_ms = None
    return SleeperClient(BASE_URL, rpm_limit=rpm, min_interval_ms=min_ms)


__CLIENT = _make_client()


def _get(url: str) -> requests.Response:
    base = BASE_URL.rstrip("/")
    if not url.startswith(base):
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r
    path = url[len(base) :]
    if not path.startswith("/"):
        path = "/" + path
    data = __CLIENT.get_json(path)

    class _Resp:
        def __init__(self, payload: Any) -> None:
            self._payload = payload

        def json(self) -> Any:  # noqa: D401
            return self._payload

    return _Resp(data)  # type: ignore[return-value]


def _resolve_league_for_season(base_league_id: str, season: str | int | None) -> dict:
    league = _get(f"{BASE_URL}/league/{base_league_id}").json()
    if season is None:
        return league
    target = str(season)
    guard = 0
    while guard < 12 and league and str(league.get("season")) != target:
        prev_id = league.get("previous_league_id")
        if not prev_id:
            break
        league = _get(f"{BASE_URL}/league/{prev_id}").json()
        guard += 1
    if str(league.get("season")) != target:
        raise ValueError(
            f"Could not resolve league for season={season} starting from {base_league_id}"
        )
    return league


def _get_users_and_rosters(league_id: str) -> tuple[list[dict], list[dict]]:
    users = _get(f"{BASE_URL}/league/{league_id}/users").json()
    rosters = _get(f"{BASE_URL}/league/{league_id}/rosters").json()
    return users, rosters


def _build_name_maps(users: list[dict], rosters: list[dict]) -> tuple[dict, dict]:
    user_name = {
        u.get("user_id"): (u.get("display_name") or u.get("username") or u.get("user_id"))
        for u in users
    }
    roster_owner_name: dict[int, str] = {}
    for r in rosters:
        rid = r.get("roster_id")
        owner = r.get("owner_id")
        if owner and owner in user_name:
            roster_owner_name[rid] = user_name[owner]
        else:
            co = r.get("co_owners") or []
            if isinstance(co, list):
                for uid in co:
                    if uid in user_name:
                        roster_owner_name[rid] = user_name[uid]
                        break
        if rid not in roster_owner_name:
            roster_owner_name[rid] = f"Roster {rid}"
    return user_name, roster_owner_name


def _fetch_weekly_groups(
    league_id: str, start_week: int, end_week: int
) -> dict[int, dict[int, list[dict]]]:
    weeks: dict[int, dict[int, list[dict]]] = {}
    for wk in range(start_week, max(start_week, end_week) + 1):
        rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{wk}").json()
        weeks[wk] = _compute_group_rows(rows)
    return weeks


def _compute_standings_with_groups(
    league_id: str,
    start_week: int,
    end_week: int,
    weekly_groups: dict[int, dict[int, list[dict]]] | None,
) -> list[dict]:
    if weekly_groups is None:
        weekly_groups = _fetch_weekly_groups(league_id, start_week, end_week)
    return _compute_standings_with_groups_lib(weekly_groups, start_week, end_week)


def _compute_weekly_results(
    league_id: str,
    start_week: int,
    end_week: int,
    weekly_groups: dict[int, dict[int, list[dict]]] | None = None,
) -> dict[int, list[tuple[int, str]]]:
    if weekly_groups is None:
        weekly_groups = _fetch_weekly_groups(league_id, start_week, end_week)
    return _compute_weekly_results_lib(weekly_groups, start_week, end_week)


def build_weekly_context(
    *, league_id: str, season: str | int | None, report_week: int | None, sport: str
) -> WeeklyContext:
    league = _resolve_league_for_season(league_id, season)
    resolved_league_id = str(league.get("league_id"))
    resolved_season = str(league.get("season"))
    settings = league.get("settings", {}) or {}
    start_week = int(settings.get("start_week", 1) or 1)
    playoff_week_start = int(settings.get("playoff_week_start", 15) or 15)
    playoff_teams = int(settings.get("playoff_teams", 0) or 0)

    state = _get(f"{BASE_URL}/state/{sport}").json()
    state_season = str(state.get("season") or "")
    state_week = int(state.get("week") or 0)
    same_season = state_season == resolved_season

    if report_week is None:
        if same_season and state_week > start_week:
            report_week = min(state_week - 1, playoff_week_start - 1)
        else:
            report_week = playoff_week_start - 1
    report_week = max(start_week, int(report_week))

    users, rosters = _get_users_and_rosters(resolved_league_id)
    _, roster_owner_name = _build_name_maps(users, rosters)
    weekly_groups = _fetch_weekly_groups(resolved_league_id, start_week, report_week)
    standings = _compute_standings_with_groups(
        resolved_league_id, start_week, report_week, weekly_groups
    )
    # H2H for report week
    groups = weekly_groups.get(report_week, {})
    h2h: list[dict] = []
    for mid, entries in (groups or {}).items():
        if len(entries) == 2:
            a, b = entries
            ap = float(a.get("points", 0) or 0)
            bp = float(b.get("points", 0) or 0)
            winner = None
            if ap > bp:
                winner = a.get("roster_id")
            elif bp > ap:
                winner = b.get("roster_id")
            h2h.append(
                {
                    "week": report_week,
                    "matchup_id": mid,
                    "rosters": [
                        {
                            "roster_id": a.get("roster_id"),
                            "owner": roster_owner_name.get(a.get("roster_id")),
                            "points": ap,
                        },
                        {
                            "roster_id": b.get("roster_id"),
                            "owner": roster_owner_name.get(b.get("roster_id")),
                            "points": bp,
                        },
                    ],
                    "winner_roster_id": winner,
                    "tie": winner is None,
                }
            )
    h2h.sort(key=lambda r: (r["week"], r["matchup_id"]))

    # Preview (usually empty for historical weeks)
    next_week = report_week + 1
    last_regular_week = playoff_week_start - 1
    preview_week = next_week if (1 <= next_week <= last_regular_week) else -1
    preview: list[dict] = []
    if preview_week > 0:
        pg = _fetch_weekly_groups(resolved_league_id, preview_week, preview_week)
        for mid, entries in (pg.get(preview_week, {}) or {}).items():
            preview.append(
                {
                    "week": preview_week,
                    "matchup_id": mid,
                    "rosters": [
                        {
                            "roster_id": e.get("roster_id"),
                            "owner": roster_owner_name.get(e.get("roster_id")),
                        }
                        for e in entries
                    ],
                }
            )
        preview.sort(key=lambda r: (r["week"], r["matchup_id"]))

    # Simple weekly results enrichment (margin only for now)
    wr_rows: list[list[str]] = []
    for m in h2h:
        if len(m.get("rosters", [])) == 2:
            a, b = m["rosters"][0], m["rosters"][1]
            ap, bp = float(a["points"]), float(b["points"])
            winner_id = m.get("winner_roster_id")
            margin = abs(ap - bp)
            wr_rows.append(
                [
                    str(m.get("matchup_id")),
                    f"{a.get('roster_id')} - {a.get('owner')}",
                    f"{ap:.2f}",
                    f"{b.get('roster_id')} - {b.get('owner')}",
                    f"{bp:.2f}",
                    str(winner_id or "-"),
                    f"{margin:.2f}",
                ]
            )

    # Streaks
    weekly_results_all = _compute_weekly_results(
        resolved_league_id, start_week, report_week, weekly_groups
    )
    streak_rows: list[list[str]] = []
    for rid, seq in sorted(weekly_results_all.items()):
        ctype, clen, cstart, cend = _compute_current_streak(seq, report_week)
        win_best, loss_best = _compute_longest_streaks(seq, report_week)
        if ctype == "W":
            cur = f"W{clen}"
        elif ctype == "L":
            cur = f"L{clen}"
        else:
            cur = "-"
        streak_rows.append(
            [
                str(rid),
                roster_owner_name.get(rid, f"Roster {rid}"),
                cur,
                str(cstart if cstart else "-"),
                str(cend if clen else "-"),
                str(win_best[0]) if win_best[0] else "-",
                win_best[1],
                str(loss_best[0]) if loss_best[0] else "-",
                loss_best[1],
            ]
        )

    playoff_rows = 0  # placeholder

    now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    title = f"# Weekly Report — League {resolved_league_id} — Season {resolved_season} — Week {report_week}"
    md_lines = [title, ""]
    meta_rows = [
        ["schema_version", SCHEMA_VERSION],
        ["generated_at", now_iso],
        ["league_id", resolved_league_id],
        ["season", resolved_season],
        ["report_week", str(report_week)],
        ["start_week", str(start_week)],
        ["playoff_week_start", str(playoff_week_start)],
        ["playoff_teams", str(playoff_teams)],
        ["state_week", str(state_week)],
        ["same_season", "yes" if same_season else "no"],
    ]
    md_lines += ["## Metadata"] + _md_table(["key", "value"], meta_rows) + [""]
    md_lines.append(f"## Standings Through Week {report_week}")
    stand_rows = []
    for rank, rec in enumerate(standings, start=1):
        stand_rows.append(
            [
                rank,
                rec.get("roster_id"),
                rec.get("wins"),
                rec.get("losses"),
                rec.get("ties"),
                f"{rec.get('win_pct'):.{WIN_PCT_PLACES}f}",
                f"{rec.get('points_for'):.{POINTS_PLACES}f}",
                f"{rec.get('points_against'):.{POINTS_PLACES}f}",
            ]
        )
    md_lines += _md_table(
        ["rank", "roster_id", "W", "L", "T", "win_pct", "PF", "PA"], stand_rows
    ) + [""]

    return WeeklyContext(
        league_id=resolved_league_id,
        season=resolved_season,
        report_week=report_week,
        same_season=same_season,
        start_week=start_week,
        playoff_week_start=playoff_week_start,
        playoff_teams=playoff_teams,
        state_week=state_week,
        standings=standings,
        h2h=h2h,
        wr_rows=wr_rows,
        preview=preview,
        streak_rows=streak_rows,
        playoff_rows=playoff_rows,
        meta_rows=meta_rows,
        markdown_lines=md_lines,
    )
