"""
weekly_report.py

Generates deterministic, machine-readable Markdown weekly reports for a Sleeper league.
Output sections: Metadata, Roster Directory, Weekly Results, Standings, Division Standings,
Playoff Standings, Head-to-Head Grid, Head-to-Head Results, Upcoming Week Preview, Streaks.

Behavioral notes:
- Calls Sleeper HTTP API with a simple throttle; prefetches weekly matchups once per run.
- Renders Markdown tables with escaped pipes and stable column ordering.
- All computations are derived from API data only; no external state.
"""

import os
import sys
import json
import argparse
import time
import datetime
import tempfile
from typing import Any

import requests

# Ensure project root is on sys.path when executed as a script (python scripts/weekly_report.py)
_THIS_DIR = os.path.dirname(__file__)
_PROJ_ROOT = os.path.dirname(_THIS_DIR)
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# Try to import project modules; if run as `python scripts/weekly_report.py`,
# fall back to inserting the project root into sys.path and retry.
try:  # E402: keep imports at top; handle path fix within except
    from scripts.lib.constants import SCHEMA_VERSION
    from scripts.lib.constants import (
        BLOWOUT_MARGIN,
        NAIL_BITER_MARGIN,
        SHOOTOUT_COMBINED,
        SLUGFEST_COMBINED,
        CLOSE_GAME_MARGIN,
        WIN_PCT_PLACES,
        POINTS_PLACES,
        DEFAULT_MIN_INTERVAL_SEC,
    )
    from scripts.lib.client import SleeperClient
    from scripts.lib.compute import (
        group_rows as _compute_group_rows,
        compute_standings_with_groups as _compute_standings_with_groups_lib,
        compute_weekly_results as _compute_weekly_results_lib,
        current_streak as _compute_current_streak,
        longest_streaks as _compute_longest_streaks,
    )
except ModuleNotFoundError:  # pragma: no cover - environment-specific
    _THIS_DIR = os.path.dirname(__file__)
    _PROJ_ROOT = os.path.dirname(_THIS_DIR)
    if _PROJ_ROOT not in sys.path:
        sys.path.insert(0, _PROJ_ROOT)
    from scripts.lib.constants import SCHEMA_VERSION
    from scripts.lib.constants import (
        BLOWOUT_MARGIN,
        NAIL_BITER_MARGIN,
        SHOOTOUT_COMBINED,
        SLUGFEST_COMBINED,
        CLOSE_GAME_MARGIN,
        WIN_PCT_PLACES,
        POINTS_PLACES,
        DEFAULT_MIN_INTERVAL_SEC,
    )
    from scripts.lib.client import SleeperClient
    from scripts.lib.compute import (
        group_rows as _compute_group_rows,
        compute_standings_with_groups as _compute_standings_with_groups_lib,
        compute_weekly_results as _compute_weekly_results_lib,
        current_streak as _compute_current_streak,
        longest_streaks as _compute_longest_streaks,
    )

BASE_URL = os.environ.get("SLEEPER_BASE_URL", "https://api.sleeper.com/v1")
LEAGUE_ID = os.environ.get("SLEEPER_LEAGUE_ID", "1180276953741729792")
SPORT = os.environ.get("SLEEPER_SPORT", "nfl")


def _get(url: str) -> requests.Response:
    # Use shared resilient client with retries and built-in rate limiting.
    # Keep a Response-like return (json() only) to avoid refactoring call sites.
    # Map absolute URL to path expected by the client.
    if not isinstance(url, str):
        raise TypeError("url must be a string")
    base = BASE_URL.rstrip("/")
    if not url.startswith(base):
        # Fallback to direct GET for unexpected hosts (should not happen in this script)
        _throttle()
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r
    path = url[len(base) :]
    if not path.startswith("/"):
        path = "/" + path
    data = _CLIENT.get_json(path)

    class _Resp:
        def __init__(self, payload: Any) -> None:
            self._payload = payload

        def json(self) -> Any:
            return self._payload

    return _Resp(data)


def _pretty(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


# --- Simple rate limiter ---
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

_MIN_INTERVAL_SEC = 0.0
if rpm and rpm > 0:
    _MIN_INTERVAL_SEC = max(_MIN_INTERVAL_SEC, 60.0 / rpm)
if min_ms and min_ms > 0:
    _MIN_INTERVAL_SEC = max(_MIN_INTERVAL_SEC, min_ms / 1000.0)
if _MIN_INTERVAL_SEC <= 0:
    _MIN_INTERVAL_SEC = DEFAULT_MIN_INTERVAL_SEC  # default ~600 rpm

_last_call_ts = 0.0


def _throttle() -> None:
    global _last_call_ts
    now = time.monotonic()
    elapsed = now - _last_call_ts if _last_call_ts else None
    if elapsed is not None and elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)
    _last_call_ts = time.monotonic()


# Shared HTTP client (respects env-based RPM/min interval). Using both the legacy
# throttle (for rare direct GET fallbacks) and the new client for robustness.
_CLIENT = SleeperClient(BASE_URL, rpm_limit=rpm, min_interval_ms=min_ms)


# ---------- helpers ----------


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


def _compute_standings(league_id: str, start_week: int, end_week: int) -> list[dict]:
    """Compute standings by fetching matchups on-demand for the given range.

    This wrapper preserves the legacy signature and delegates to the shared
    compute library after building the minimal weekly_groups structure.
    """
    weekly_groups: dict[int, dict[int, list[dict]]] = {}
    for wk in range(start_week, max(start_week, end_week) + 1):
        rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{wk}").json()
        weekly_groups[wk] = _compute_group_rows(rows)
    return _compute_standings_with_groups_lib(weekly_groups, start_week, end_week)


def _group_rows(rows: list[dict]) -> dict[int, list[dict]]:
    """Delegate to shared group_rows helper (behavior identical)."""
    return _compute_group_rows(rows)


def _fetch_weekly_groups(
    league_id: str, start_week: int, end_week: int
) -> dict[int, dict[int, list[dict]]]:
    weeks: dict[int, dict[int, list[dict]]] = {}
    for wk in range(start_week, max(start_week, end_week) + 1):
        rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{wk}").json()
        weeks[wk] = _compute_group_rows(rows)  # THIS MUST BE INSIDE THE LOOP
    return weeks


def _compute_standings_with_groups(
    league_id: str,
    start_week: int,
    end_week: int,
    weekly_groups: dict[int, dict[int, list[dict]]] | None,
) -> list[dict]:
    """Delegate to shared standings computation; fetch weeks if groups absent."""
    if weekly_groups is None:
        built: dict[int, dict[int, list[dict]]] = {}
        for wk in range(start_week, max(start_week, end_week) + 1):
            rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{wk}").json()
            built[wk] = _compute_group_rows(rows)
        weekly_groups = built
    return _compute_standings_with_groups_lib(weekly_groups, start_week, end_week)


def _head_to_head_week(league_id: str, week: int, roster_owner_name: dict[int, str]) -> list[dict]:
    rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{week}").json()
    groups = _compute_group_rows(rows)

    results: list[dict] = []
    for mid, entries in groups.items():
        if len(entries) == 2:
            a, b = entries
            ap = float(a.get("points", 0) or 0)
            bp = float(b.get("points", 0) or 0)
            winner = None
            if ap > bp:
                winner = a.get("roster_id")
            elif bp > ap:
                winner = b.get("roster_id")
            results.append(
                {
                    "week": week,
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
        else:
            simplified = [
                {
                    "roster_id": e.get("roster_id"),
                    "owner": roster_owner_name.get(e.get("roster_id")),
                    "points": float(e.get("points", 0) or 0),
                }
                for e in entries
            ]
            results.append(
                {
                    "week": week,
                    "matchup_id": mid,
                    "rosters": simplified,
                    "winner_roster_id": None,
                    "tie": None,
                }
            )
    results.sort(key=lambda r: (r["week"], r["matchup_id"]))
    return results


def _preview_week(league_id: str, week: int, roster_owner_name: dict[int, str]) -> list[dict]:
    if week <= 0:
        return []
    rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{week}").json()
    if not rows:
        return []
    groups: dict[int, list[dict]] = {}
    for row in rows:
        mid = row.get("matchup_id")
        if mid is None:
            mid = -100000 - row.get("roster_id", 0)
        groups.setdefault(mid, []).append(row)
    preview: list[dict] = []
    for mid, entries in groups.items():
        preview.append(
            {
                "week": week,
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
    return preview


# ---------- streaks helpers ----------


def _compute_weekly_results(
    league_id: str,
    start_week: int,
    end_week: int,
    weekly_groups: dict[int, dict[int, list[dict]]] | None = None,
) -> dict[int, list[tuple[int, str]]]:
    """Thin wrapper that delegates to shared compute_weekly_results."""
    if weekly_groups is None:
        built: dict[int, dict[int, list[dict]]] = {}
        for wk in range(start_week, max(start_week, end_week) + 1):
            rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{wk}").json()
            built[wk] = _compute_group_rows(rows)
        weekly_groups = built
    return _compute_weekly_results_lib(weekly_groups, start_week, end_week)


def _current_streak(
    res_list: list[tuple[int, str]], through_week: int
) -> tuple[str, int, int, int]:
    """Delegate to shared current_streak helper."""
    return _compute_current_streak(res_list, through_week)


def _longest_streaks(
    res_list: list[tuple[int, str]], through_week: int
) -> tuple[tuple[int, str], tuple[int, str]]:
    """Delegate to shared longest_streaks helper."""
    return _compute_longest_streaks(res_list, through_week)


def _atomic_write(path: str, content: str) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=os.path.splitext(path)[1])
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def generate_weekly_history_report(
    league_id: str = LEAGUE_ID,
    season: str | int | None = None,
    report_week: int | None = None,
    sport: str = SPORT,
    out_dir: str = "reports/weekly",
    *,
    verbose: bool = False,
    dry_run: bool = False,
) -> dict:
    """Build a deterministic weekly Markdown report and write it to disk.

    Args:
        league_id: Sleeper league id; can be the current season or any season anchor.
        season: Target season (e.g., "2024"); if None, uses the resolved league season.
        report_week: Week number to report; defaults to last completed regular-season week.
        sport: Sleeper sport key (default "nfl").
        out_dir: Base output directory (reports are placed under {out_dir}/{season}).
        verbose: If True, print destination and sizes.
        dry_run: If True, compute content but do not write files.

    Returns:
        A summary dict with path and counts, e.g.:
        {
          "written": True,
          "path": "reports/weekly/2024/week-11.md",
          "league_id": str,
          "season": str,
          "report_week": int,
          "same_season": bool,
          "entries": {"standings": int, "head_to_head": int, "preview": int},
        }

    Side effects:
        Writes an atomically-updated Markdown file unless dry_run is True. All
        content is derived solely from Sleeper API data. Output format is
        stable and suitable for downstream parsing.
    """
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
    report_week = int(report_week)
    if report_week < start_week:
        report_week = start_week

    users, rosters = _get_users_and_rosters(resolved_league_id)
    _, roster_owner_name = _build_name_maps(users, rosters)

    # Fetch weekly matchup groups once for [start_week..report_week] to reuse across sections
    weekly_groups = _fetch_weekly_groups(resolved_league_id, start_week, report_week)
    standings = _compute_standings_with_groups(
        resolved_league_id, start_week, report_week, weekly_groups
    )
    # Build H2H using pre-fetched rows for the report week
    # Reuse existing function but avoid refetching: inline equivalent logic here to avoid another request
    groups = weekly_groups.get(report_week, {})
    results: list[dict] = []
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
            results.append(
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
        else:
            simplified = [
                {
                    "roster_id": e.get("roster_id"),
                    "owner": roster_owner_name.get(e.get("roster_id")),
                    "points": float(e.get("points", 0) or 0),
                }
                for e in entries
            ]
            results.append(
                {
                    "week": report_week,
                    "matchup_id": mid,
                    "rosters": simplified,
                    "winner_roster_id": None,
                    "tie": None,
                }
            )
    results.sort(key=lambda r: (r["week"], r["matchup_id"]))
    h2h = results
    next_week = report_week + 1
    # Always attempt preview for the historical season too, but only within regular-season bounds
    last_regular_week = playoff_week_start - 1
    preview_week = next_week if (1 <= next_week <= last_regular_week) else -1
    preview = _preview_week(resolved_league_id, preview_week, roster_owner_name)

    now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    title = f"# Weekly Report — League {resolved_league_id} — Season {resolved_season} — Week {report_week}"

    from scripts.lib.render import md_table as _md_table

    # Build sections as Markdown tables
    md_lines = [title, ""]

    # Roster Directory
    md_lines.append("## Roster Directory")
    dir_rows = []
    for rid in sorted(roster_owner_name.keys()):
        dir_rows.append([str(rid), roster_owner_name[rid]])
    md_lines += _md_table(["roster_id", "owner"], dir_rows)
    md_lines.append("")

    # Weekly Results Week {report_week}
    # Build division map early for enrichments
    div_map_for_wr: dict[int, int] = {}
    for r in rosters:
        rid = r.get("roster_id")
        div = None
        s = r.get("settings") or {}
        if isinstance(s, dict):
            div = s.get("division")
        try:
            div_map_for_wr[int(rid)] = int(div) if div is not None else 0
        except Exception:
            pass

    # Precompute previous-week standings rank map for upset detection
    prev_week = report_week - 1
    prev_rank_map: dict[int, int] = {}
    if prev_week >= start_week:
        prev_table = _compute_standings_with_groups(
            resolved_league_id, start_week, prev_week, weekly_groups
        )
        for rank, rec in enumerate(
            sorted(prev_table, key=lambda r: (-r["win_pct"], -r["points_for"], r["roster_id"])),
            start=1,
        ):
            prev_rank_map[rec.get("roster_id")] = rank

    # Precompute prior-week streaks for opponent streak break detection
    prev_results = (
        _compute_weekly_results(resolved_league_id, start_week, prev_week, weekly_groups)
        if prev_week >= start_week
        else {}
    )

    # Determine weekly point context (for enrichments)
    all_points: list[float] = []
    winner_points: list[float] = []
    loser_points: list[float] = []
    weekly_winner_max = 0.0
    for m in h2h:
        if len(m.get("rosters", [])) == 2:
            a, b = m["rosters"][0], m["rosters"][1]
            ap, bp = float(a.get("points", 0) or 0), float(b.get("points", 0) or 0)
            all_points.extend([ap, bp])
            if m.get("winner_roster_id") == a.get("roster_id"):
                winner_points.append(ap)
                loser_points.append(bp)
                weekly_winner_max = max(weekly_winner_max, ap)
            elif m.get("winner_roster_id") == b.get("roster_id"):
                winner_points.append(bp)
                loser_points.append(ap)
                weekly_winner_max = max(weekly_winner_max, bp)

    def _median(vals: list[float]) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        n = len(s)
        mid = n // 2
        if n % 2 == 1:
            return s[mid]
        return (s[mid - 1] + s[mid]) / 2.0

    weekly_points_median = _median(all_points)
    weekly_loser_max = max(loser_points) if loser_points else 0.0
    weekly_winner_min = min(winner_points) if winner_points else 0.0

    # Enrichment thresholds (centralized constants)

    def _prior_head_to_head_winner(roster_x: int, roster_y: int) -> int | None:
        # Scan prior weeks for a matchup between these two rosters
        if prev_week < start_week:
            return None
        for wk in range(start_week, prev_week + 1):
            groups = weekly_groups.get(wk, {})
            for _, entries in (groups or {}).items():
                if len(entries) != 2:
                    continue
                rx = entries[0].get("roster_id")
                ry = entries[1].get("roster_id")
                if {int(rx), int(ry)} == {int(roster_x), int(roster_y)}:
                    ap = float(entries[0].get("points", 0) or 0)
                    bp = float(entries[1].get("points", 0) or 0)
                    if ap > bp:
                        return int(rx)
                    elif bp > ap:
                        return int(ry)
        return None

    def _enrich(match: dict, a: dict, b: dict) -> dict:
        winner_id = match.get("winner_roster_id")
        ap, bp = float(a.get("points", 0) or 0), float(b.get("points", 0) or 0)
        # Identify winner and loser entries for convenience
        if winner_id == a.get("roster_id"):
            wp, lp = ap, bp
            w_ent, l_ent = a, b
        elif winner_id == b.get("roster_id"):
            wp, lp = bp, ap
            w_ent, l_ent = b, a
        else:
            wp, lp = ap, bp
            w_ent, l_ent = None, None

        details: dict[str, str] = {}
        # margin (always include)
        margin = abs(ap - bp)
        details["margin_pts"] = f"{margin:.2f}"
        # blowout / nail-biter (only when true)
        if margin >= BLOWOUT_MARGIN:
            details["blowout"] = "yes"
        if margin <= NAIL_BITER_MARGIN:
            details["nail_biter"] = "yes"
        # division game (only when true)
        a_div = div_map_for_wr.get(a.get("roster_id"), 0)
        b_div = div_map_for_wr.get(b.get("roster_id"), 0)
        if a_div and b_div and a_div == b_div:
            details["division_game"] = "yes"
        # upset based on previous-week rank (lower rank number is better)
        if winner_id and w_ent is not None and l_ent is not None:
            wrank = prev_rank_map.get(w_ent.get("roster_id"))
            lrank = prev_rank_map.get(l_ent.get("roster_id"))
            if wrank and lrank:
                if wrank > lrank:
                    details["upset"] = "yes"
        # broke opponent streak (prior to this week)
        if l_ent is not None and prev_week >= start_week:
            l_prev = prev_results.get(l_ent.get("roster_id"), [])
            ctype, clen, _, _ = _current_streak(l_prev, prev_week)
            if ctype == "W" and clen >= 2:
                details["broke_opponent_streak"] = "yes"
                details["opponent_prev_streak_type"] = ctype
                details["opponent_prev_streak_len"] = str(clen)
        # extended own streak
        if w_ent is not None and prev_week >= start_week:
            w_prev = prev_results.get(w_ent.get("roster_id"), [])
            ctype, clen, _, _ = _current_streak(w_prev, prev_week)
            if ctype == "W" and clen >= 2:
                details["extended_win_streak"] = str(clen + 1)
        # winner highest score of week
        if winner_id and w_ent is not None:
            if abs(wp - weekly_winner_max) < 1e-6:
                details["winner_highest_score_week"] = "yes"
        # highest loser / lowest winner of the week
        if l_ent is not None and abs(lp - weekly_loser_max) < 1e-6:
            details["highest_loser_score_week"] = "yes"
        if w_ent is not None and abs(wp - weekly_winner_min) < 1e-6:
            details["lowest_winner_score_week"] = "yes"
        # shootout / slugfest
        combined = ap + bp
        if combined >= SHOOTOUT_COMBINED:
            details["shootout"] = "yes"
        if combined <= SLUGFEST_COMBINED:
            details["slugfest"] = "yes"
        # bad beat / got away (relative to weekly median and close-ish margin)
        if w_ent is not None and l_ent is not None:
            if lp >= weekly_points_median and margin <= CLOSE_GAME_MARGIN:
                details["bad_beat"] = "yes"
            if wp <= weekly_points_median and margin <= CLOSE_GAME_MARGIN:
                details["got_away"] = "yes"
        # simple season series note
        try:
            ax, bx = int(a.get("roster_id")), int(b.get("roster_id"))
            prior_winner = _prior_head_to_head_winner(ax, bx)
            if prior_winner is not None and winner_id is not None:
                if int(winner_id) == int(prior_winner):
                    details["season_series_sweep"] = "yes"
                else:
                    details["evened_series"] = "yes"
        except Exception:
            pass
        return details

    def _kv(details: dict[str, str]) -> str:
        # stable key ordering for determinism
        keys = sorted(details.keys())
        return "; ".join(f"{k}={details[k]}" for k in keys) if keys else "-"

    md_lines.append(f"## Weekly Results Week {report_week}")
    wr_rows: list[list[str]] = []
    for m in h2h:
        if len(m.get("rosters", [])) == 2:
            a, b = m["rosters"][0], m["rosters"][1]
            winner_id = m.get("winner_roster_id")
            if winner_id == a.get("roster_id"):
                winner_owner = a.get("owner")
                loser_owner = b.get("owner")
            elif winner_id == b.get("roster_id"):
                winner_owner = b.get("owner")
                loser_owner = a.get("owner")
            else:
                winner_owner = "-"
                loser_owner = "-"
            details = _enrich(m, a, b)
            wr_rows.append(
                [
                    str(m.get("matchup_id")),
                    f"{a.get('roster_id')} - {a.get('owner')}",
                    f"{a.get('points'):.{POINTS_PLACES}f}",
                    f"{b.get('roster_id')} - {b.get('owner')}",
                    f"{b.get('points'):.{POINTS_PLACES}f}",
                    str(winner_id or "-"),
                    winner_owner,
                    loser_owner,
                    "yes" if m.get("tie") else "no",
                    _kv(details),
                ]
            )
        else:
            details = (
                " | ".join(
                    f"{e.get('roster_id')}:{float(e.get('points',0) or 0):.{POINTS_PLACES}f}"
                    for e in m.get("rosters", [])
                )
                or "-"
            )
            wr_rows.append([str(m.get("matchup_id")), "", "", "", "", "-", "-", "-", "-", details])
    md_lines += _md_table(
        [
            "matchup_id",
            "roster_a",
            "points_a",
            "roster_b",
            "points_b",
            "winner_roster_id",
            "winner_owner",
            "loser_owner",
            "tie",
            "details",
        ],
        wr_rows,
    )
    md_lines.append("")

    # Prepare streaks up to report_week for standings
    weekly_results_all = _compute_weekly_results(
        resolved_league_id, start_week, report_week, weekly_groups
    )

    # Standings Through Week {report_week}
    md_lines.append(f"## Standings Through Week {report_week}")
    stand_rows = []
    for rank, rec in enumerate(standings, start=1):
        rid = rec.get("roster_id")
        # current streak
        res_list = weekly_results_all.get(rid, [])
        ctype, clen, _, _ = _current_streak(res_list, report_week)
        cur = f"{ctype}{clen}" if ctype in ("W", "L") and clen > 0 else "-"
        # rank change vs previous week
        prev_rank = prev_rank_map.get(rid)
        rank_change = "-" if prev_rank is None else str(prev_rank - rank)  # positive means moved up
        stand_rows.append(
            [
                str(rank),
                str(rid),
                roster_owner_name.get(rid, f"Roster {rid}"),
                str(rec.get("wins")),
                str(rec.get("losses")),
                str(rec.get("ties")),
                f"{rec.get('win_pct'):.{WIN_PCT_PLACES}f}",
                f"{rec.get('points_for'):.{POINTS_PLACES}f}",
                f"{rec.get('points_against'):.{POINTS_PLACES}f}",
                str(rec.get("games")),
                cur,
                rank_change,
            ]
        )
    md_lines += _md_table(
        [
            "rank",
            "roster_id",
            "owner",
            "W",
            "L",
            "T",
            "win_pct",
            "PF",
            "PA",
            "games",
            "current_streak",
            "rank_change",
        ],
        stand_rows,
    )
    md_lines.append("")

    # Division Standings Through Week {report_week}
    # Build division mapping from rosters
    div_map: dict[int, int] = {}
    for r in rosters:
        rid = r.get("roster_id")
        div = None
        s = r.get("settings") or {}
        if isinstance(s, dict):
            div = s.get("division")
        try:
            div_map[int(rid)] = int(div) if div is not None else 0
        except Exception:
            if rid is not None:
                try:
                    div_map[int(rid)] = 0
                except Exception:
                    pass

    # Resolve division names from league metadata if present
    div_names: dict[int, str] = {}
    meta = league.get("metadata") or {}
    if isinstance(meta, dict):
        for k, v in meta.items():
            if not isinstance(v, str) or not v.strip():
                continue
            lk = str(k).lower()
            # Accept patterns like division_1, division-1, division_1_name
            # Ignore avatar keys
            if "avatar" in lk:
                continue
            if lk.startswith("division"):
                # Extract trailing number
                digits = ""
                for ch in lk:
                    if ch.isdigit():
                        digits += ch
                if digits:
                    try:
                        idx = int(digits)
                        # prefer explicit *_name keys if duplicates occur
                        if lk.endswith("_name") or lk.endswith("name"):
                            div_names[idx] = v.strip()
                        else:
                            div_names.setdefault(idx, v.strip())
                    except Exception:
                        pass

    # Group standings by division id
    divisions: dict[int, list[dict]] = {}
    for rec in standings:
        rid = rec.get("roster_id")
        div_id = div_map.get(rid, 0)
        divisions.setdefault(div_id, []).append(rec)

    # Sort division keys, with 0 (unknown) at the end
    div_keys = sorted([k for k in divisions.keys() if k != 0]) + ([0] if 0 in divisions else [])
    if div_keys:
        md_lines.append(f"## Division Standings Through Week {report_week}")
        for dk in div_keys:
            dname = div_names.get(dk)
            if dk == 0:
                title = "### Division Unknown"
            elif dname:
                title = f"### {dname}"
            else:
                title = f"### Division {dk}"
            md_lines.append(title)
            drows: list[list[str]] = []
            # Sort within division like overall standings order
            div_table = sorted(
                divisions[dk], key=lambda r: (-r["win_pct"], -r["points_for"], r["roster_id"])
            )
            for rank, rec in enumerate(div_table, start=1):
                rid = rec.get("roster_id")
                # current streak per team
                res_list = weekly_results_all.get(rid, [])
                ctype, clen, _, _ = _current_streak(res_list, report_week)
                cur = f"{ctype}{clen}" if ctype in ("W", "L") and clen > 0 else "-"
                drows.append(
                    [
                        str(rank),
                        str(rid),
                        roster_owner_name.get(rid, f"Roster {rid}"),
                        str(rec.get("wins")),
                        str(rec.get("losses")),
                        str(rec.get("ties")),
                        f"{rec.get('win_pct'):.{WIN_PCT_PLACES}f}",
                        f"{rec.get('points_for'):.{POINTS_PLACES}f}",
                        f"{rec.get('points_against'):.{POINTS_PLACES}f}",
                        str(rec.get("games")),
                        cur,
                    ]
                )
            md_lines += _md_table(
                [
                    "rank",
                    "roster_id",
                    "owner",
                    "W",
                    "L",
                    "T",
                    "win_pct",
                    "PF",
                    "PA",
                    "games",
                    "current_streak",
                ],
                drows,
            )
            md_lines.append("")

    # Playoff Standings Through Week {report_week} (2 division winners + 2 best remaining)
    playoff_rows = 0
    try:
        # Map roster_id -> overall position for fast ordering
        pos_map = {rec.get("roster_id"): i for i, rec in enumerate(standings)}
        # Identify division winners (exclude division 0)
        div_winners: list[dict] = []
        for dk in [k for k in divisions.keys() if k != 0]:
            div_table = sorted(
                divisions[dk], key=lambda r: (-r["win_pct"], -r["points_for"], r["roster_id"])
            )
            if div_table:
                div_winners.append(div_table[0])
        # Deduplicate in case of data quirks
        seen = set()
        unique_winners = []
        for rec in div_winners:
            rid = rec.get("roster_id")
            if rid in seen:
                continue
            seen.add(rid)
            unique_winners.append(rec)
        # Order winners by overall standings order
        unique_winners.sort(key=lambda r: pos_map.get(r.get("roster_id"), 1_000_000))
        # Wildcards: best remaining teams regardless of division
        winner_ids = {rec.get("roster_id") for rec in unique_winners}
        wildcards = [rec for rec in standings if rec.get("roster_id") not in winner_ids]
        wildcards = wildcards[: max(0, 4 - len(unique_winners))]
        seeds = unique_winners + wildcards
        if seeds:
            md_lines.append(f"## Playoff Standings Through Week {report_week}")
            prow: list[list[str]] = []
            # Seeded teams first
            for idx, rec in enumerate(seeds, start=1):
                rid = rec.get("roster_id")
                did = div_map.get(rid, 0)
                dname = (
                    div_names.get(did) if did in div_names else (f"Division {did}" if did else "-")
                )
                typ = "Division Winner" if rid in winner_ids else "Wildcard"
                # current streak
                res_list = weekly_results_all.get(rid, [])
                ctype, clen, _, _ = _current_streak(res_list, report_week)
                cur = f"{ctype}{clen}" if ctype in ("W", "L") and clen > 0 else "-"
                prow.append(
                    [
                        str(idx),
                        str(rid),
                        roster_owner_name.get(rid, f"Roster {rid}"),
                        dname,
                        typ,
                        str(rec.get("wins")),
                        str(rec.get("losses")),
                        str(rec.get("ties")),
                        f"{rec.get('win_pct'):.{WIN_PCT_PLACES}f}",
                        f"{rec.get('points_for'):.{POINTS_PLACES}f}",
                        f"{rec.get('points_against'):.{POINTS_PLACES}f}",
                        str(rec.get("games")),
                        cur,
                    ]
                )

            # In the Hunt: any non-seeded teams with the same W/L/T record as any seeded team
            seeded_records = {
                (int(r.get("wins")), int(r.get("losses")), int(r.get("ties"))) for r in seeds
            }
            seeded_ids = {int(r.get("roster_id")) for r in seeds}
            in_hunt: list[dict] = []
            for rec in standings:
                rid = int(rec.get("roster_id"))
                if rid in seeded_ids:
                    continue
                tup = (int(rec.get("wins")), int(rec.get("losses")), int(rec.get("ties")))
                if tup in seeded_records:
                    in_hunt.append(rec)
            # Order in-hunt by overall standings position
            in_hunt.sort(key=lambda r: pos_map.get(r.get("roster_id"), 1_000_000))
            for rec in in_hunt:
                rid = rec.get("roster_id")
                did = div_map.get(rid, 0)
                dname = (
                    div_names.get(did) if did in div_names else (f"Division {did}" if did else "-")
                )
                # current streak
                res_list = weekly_results_all.get(rid, [])
                ctype, clen, _, _ = _current_streak(res_list, report_week)
                cur = f"{ctype}{clen}" if ctype in ("W", "L") and clen > 0 else "-"
                prow.append(
                    [
                        "-",  # no seed assigned
                        str(rid),
                        roster_owner_name.get(rid, f"Roster {rid}"),
                        dname,
                        "In the Hunt",
                        str(rec.get("wins")),
                        str(rec.get("losses")),
                        str(rec.get("ties")),
                        f"{rec.get('win_pct'):.4f}",
                        f"{rec.get('points_for'):.2f}",
                        f"{rec.get('points_against'):.2f}",
                        str(rec.get("games")),
                        cur,
                    ]
                )
            md_lines += _md_table(
                [
                    "seed",
                    "roster_id",
                    "owner",
                    "division",
                    "type",
                    "W",
                    "L",
                    "T",
                    "win_pct",
                    "PF",
                    "PA",
                    "games",
                    "current_streak",
                ],
                prow,
            )
            md_lines.append("")
            playoff_rows = len(prow)
    except Exception:
        # Fail-soft: skip section on any error
        playoff_rows = 0

    # Head-to-Head Grid Through Week {report_week}
    # Build an order from overall standings for rows/columns
    order_rids = [rec.get("roster_id") for rec in standings]
    # Build pairwise records across all weeks up to report_week (two-team matchups only)
    pair_records: dict[int, dict[int, tuple[int, int, int]]] = {}
    for wk in range(start_week, report_week + 1):
        for _, entries in (weekly_groups.get(wk, {}) or {}).items():
            if len(entries) != 2:
                continue
            a, b = entries
            ra, rb = int(a.get("roster_id")), int(b.get("roster_id"))
            ap, bp = float(a.get("points", 0) or 0), float(b.get("points", 0) or 0)
            # initialize
            for x, y in ((ra, rb), (rb, ra)):
                pair_records.setdefault(x, {}).setdefault(y, (0, 0, 0))
            Wa, La, Ta = pair_records[ra][rb]
            Wb, Lb, Tb = pair_records[rb][ra]
            if ap > bp:
                Wa += 1
                Lb += 1
            elif bp > ap:
                Wb += 1
                La += 1
            else:
                Ta += 1
                Tb += 1
            pair_records[ra][rb] = (Wa, La, Ta)
            pair_records[rb][ra] = (Wb, Lb, Tb)

    def _fmt_record(tup: tuple[int, int, int]) -> str:
        w, losses, t = tup
        if (w + losses + t) == 0:
            return "--"
        # Always show W-L, append -T only when T > 0
        return f"{w}-{losses}-{t}" if t else f"{w}-{losses}"

    # Render grid (header uses roster_id-owner labels)
    md_lines.append(f"## Head-to-Head Grid Through Week {report_week}")
    col_labels = [f"{rid}-{roster_owner_name.get(rid, f'Roster {rid}')}" for rid in order_rids]
    # Build rows
    grid_rows: list[list[str]] = []
    for rid_row in order_rids:
        row_label = f"{rid_row}-{roster_owner_name.get(rid_row, f'Roster {rid_row}')}"
        cells: list[str] = [row_label]
        for rid_col in order_rids:
            if rid_row == rid_col:
                cells.append("-")
            else:
                tup = pair_records.get(rid_row, {}).get(rid_col, (0, 0, 0))
                cells.append(_fmt_record(tup))
        grid_rows.append(cells)
    md_lines += _md_table([""] + col_labels, grid_rows)
    md_lines.append("")

    # Head-to-Head Results Week {report_week}
    md_lines.append(f"## Head-to-Head Results Week {report_week}")
    h2h_rows = []
    for m in h2h:
        if len(m.get("rosters", [])) == 2:
            a, b = m["rosters"][0], m["rosters"][1]
            h2h_rows.append(
                [
                    str(m.get("matchup_id")),
                    f"{a.get('roster_id')} - {a.get('owner')}",
                    f"{a.get('points'):.2f}",
                    f"{b.get('roster_id')} - {b.get('owner')}",
                    f"{b.get('points'):.2f}",
                    str(m.get("winner_roster_id") or "-"),
                    "yes" if m.get("tie") else "no",
                    "-",
                ]
            )
        else:
            details = (
                " | ".join(
                    f"{e.get('roster_id')}:{float(e.get('points',0) or 0):.{POINTS_PLACES}f}"
                    for e in m.get("rosters", [])
                )
                or "-"
            )
            h2h_rows.append([str(m.get("matchup_id")), "", "", "", "", "-", "-", details])
    md_lines += _md_table(
        [
            "matchup_id",
            "roster_a",
            "points_a",
            "roster_b",
            "points_b",
            "winner_roster_id",
            "tie",
            "details",
        ],
        h2h_rows,
    )
    md_lines.append("")

    # Upcoming Week Preview
    md_lines.append(f"## Upcoming Week Preview Week {next_week}")
    prev_rows = []
    for p in preview:
        rost = p.get("rosters", []) or []
        if len(rost) == 2:
            a, b = rost[0], rost[1]
            prev_rows.append(
                [
                    str(p.get("matchup_id")),
                    f"{a.get('roster_id')}-{a.get('owner')}",
                    f"{b.get('roster_id')}-{b.get('owner')}",
                    "-",
                ]
            )
        else:
            details = " | ".join(f"{e.get('roster_id')}-{e.get('owner')}" for e in rost) or "-"
            prev_rows.append([str(p.get("matchup_id")), "", "", details])
    if not prev_rows:
        prev_rows.append(["-", "-", "-", "-"])
    md_lines += _md_table(["matchup_id", "roster_a", "roster_b", "details"], prev_rows)
    md_lines.append("")

    # Streaks Through Week {report_week}
    # Compute per-roster weekly results and streaks
    weekly_results = _compute_weekly_results(
        resolved_league_id, start_week, report_week, weekly_groups
    )
    streak_rows: list[list[str]] = []
    for rid in sorted(roster_owner_name.keys()):
        res_list = weekly_results.get(rid, [])
        ctype, clen, cstart, cend = _current_streak(res_list, report_week)
        win_best, loss_best = _longest_streaks(res_list, report_week)
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
    md_lines.append(f"## Streaks Through Week {report_week}")
    md_lines += _md_table(
        [
            "roster_id",
            "owner",
            "current_streak",
            "current_start_week",
            "current_end_week",
            "longest_win_len",
            "longest_win_span",
            "longest_loss_len",
            "longest_loss_span",
        ],
        streak_rows,
    )
    md_lines.append("")
    streaks_count = len(streak_rows)

    # ---------- Build and insert Metadata now that counts and context are known ----------
    standings_count = len(standings)
    h2h_count = len(h2h)
    preview_count = len(preview)
    num_teams = len(roster_owner_name)

    # Weekly scoring context (avg/median/high/low)
    try:
        all_points = []
        for m in h2h:
            rost = m.get("rosters", [])
            if len(rost) == 2:
                all_points.extend(
                    [float(rost[0].get("points", 0) or 0), float(rost[1].get("points", 0) or 0)]
                )
        week_points_avg = (sum(all_points) / len(all_points)) if all_points else 0.0
        s_sorted = sorted(all_points)
        if s_sorted:
            n = len(s_sorted)
            if n % 2:
                week_points_median = float(s_sorted[n // 2])
            else:
                week_points_median = float((s_sorted[n // 2 - 1] + s_sorted[n // 2]) / 2.0)
            week_high = float(max(s_sorted))
            week_low = float(min(s_sorted))
        else:
            week_points_median = 0.0
            week_high = 0.0
            week_low = 0.0
    except Exception:
        week_points_avg = 0.0
        week_points_median = 0.0
        week_high = 0.0
        week_low = 0.0

    # Season high/low through week (per-team single-week scores)
    season_high_through = 0.0
    season_low_through = None
    for wk in range(start_week, report_week + 1):
        for entries in (weekly_groups.get(wk, {}) or {}).values():
            for e in entries:
                pts = float(e.get("points", 0) or 0)
                season_high_through = max(season_high_through, pts)
                season_low_through = (
                    pts if season_low_through is None else min(season_low_through, pts)
                )
    if season_low_through is None:
        season_low_through = 0.0

    # Division metadata for inclusion in Metadata table
    div_names_meta: dict[int, str] = {}
    _lg_meta = league.get("metadata") or {}
    if isinstance(_lg_meta, dict):
        for k, v in _lg_meta.items():
            if not isinstance(v, str) or not v.strip():
                continue
            lk = str(k).lower()
            if "avatar" in lk:
                continue
            if lk.startswith("division"):
                digits = "".join([ch for ch in lk if ch.isdigit()])
                if digits:
                    try:
                        idx = int(digits)
                        if lk.endswith("_name") or lk.endswith("name"):
                            div_names_meta[idx] = v.strip()
                        else:
                            div_names_meta.setdefault(idx, v.strip())
                    except Exception:
                        pass
    active_divisions = sorted(
        {int((r.get("settings") or {}).get("division") or 0) for r in rosters} - {0}
    )
    all_div_ids = sorted(set(div_names_meta.keys()) | set(active_divisions))
    season_phase = "regular" if report_week < playoff_week_start else "postseason"
    last_regular_week = playoff_week_start - 1
    preview_week_meta = str(next_week) if (1 <= next_week <= last_regular_week) else "-"

    meta_rows = [
        ["schema_version", SCHEMA_VERSION],
        ["generated_at", now_iso],
        ["league_id", resolved_league_id],
        ["league_name", str(league.get("name"))],
        ["season", resolved_season],
        ["report_week", str(report_week)],
        ["standings_through_week", str(report_week)],
        ["head_to_head_week", str(report_week)],
        ["preview_week", preview_week_meta],
        ["start_week", str(start_week)],
        ["playoff_week_start", str(playoff_week_start)],
        ["playoff_teams", str(playoff_teams)],
        ["state_season", state_season],
        ["state_week", str(state_week)],
        ["same_season", "yes" if same_season else "no"],
        ["season_phase", season_phase],
        ["num_teams", str(num_teams)],
        ["standings_rows", str(standings_count)],
        ["h2h_rows", str(h2h_count)],
        ["weekly_results_rows", str(len(wr_rows))],
        ["preview_rows", str(preview_count)],
        ["playoff_rows", str(playoff_rows)],
        ["streaks_rows", str(streaks_count)],
        ["details_format", "kv;sep=';';kvsep='=';sparse=yes"],
    ["week_points_avg", f"{week_points_avg:.{POINTS_PLACES}f}"],
    ["week_points_median", f"{week_points_median:.{POINTS_PLACES}f}"],
    ["week_high", f"{week_high:.{POINTS_PLACES}f}"],
    ["week_low", f"{week_low:.{POINTS_PLACES}f}"],
    ["season_high_through_week", f"{season_high_through:.{POINTS_PLACES}f}"],
    ["season_low_through_week", f"{season_low_through:.{POINTS_PLACES}f}"],
    ]
    meta_rows.append(["division_count_configured", str(len(div_names_meta))])
    meta_rows.append(["division_count_active", str(len(active_divisions))])
    for did in all_div_ids:
        meta_rows.append([f"division_{did}_name", div_names_meta.get(did, f"Division {did}")])

    # Insert metadata at top (after title line and blank line)
    metadata_block = ["## Metadata"] + _md_table(["key", "value"], meta_rows) + [""]
    md_lines[2:2] = metadata_block

    dest_dir = os.path.join(out_dir, resolved_season)
    dest_path = os.path.join(dest_dir, f"week-{report_week:02d}.md")
    content = "\n".join(md_lines)
    if verbose:
        print(f"[weekly_report] writing {dest_path} ({len(content)} bytes)")
    if not dry_run:
        _atomic_write(dest_path, content)

    return {
        "written": True,
        "path": dest_path,
        "league_id": resolved_league_id,
        "season": resolved_season,
        "report_week": report_week,
        "same_season": same_season,
        "entries": {
            "standings": len(standings),
            "head_to_head": len(h2h),
            "preview": len(preview),
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

    args = parser.parse_args(argv)
    # Range or single?
    try:
        if args.all or args.from_week is not None or args.to_week is not None:
            # Resolve season boundaries
            league = _resolve_league_for_season(args.league_id, args.season)
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
                        verbose=args.verbose,
                        dry_run=args.dry_run,
                    )
                    print(f"OK  Week {wk:02d} -> {summary['path']}")
                except requests.HTTPError as e:
                    failures += 1
                    print(f"HTTPError on week {wk}: {e}", file=sys.stderr)
                    if e.response is not None:
                        try:
                            print(_pretty(e.response.json()), file=sys.stderr)
                        except Exception:
                            print(e.response.text[:2000], file=sys.stderr)
                except Exception as e:
                    failures += 1
                    print(f"Error on week {wk}: {e}", file=sys.stderr)
            if failures:
                print(f"Completed with {failures} failures.")
                return 1
            print("All reports generated successfully.")
            return 0
        else:
            summary = generate_weekly_history_report(
                league_id=args.league_id,
                season=args.season,
                report_week=args.report_week,
                sport=args.sport,
                out_dir=args.out_dir,
                verbose=args.verbose,
                dry_run=args.dry_run,
            )
            print(_pretty(summary))
            print(f"Wrote: {summary['path']}")
            return 0
    except requests.HTTPError as e:
        print(f"HTTPError: {e}", file=sys.stderr)
        if e.response is not None:
            try:
                print(_pretty(e.response.json()), file=sys.stderr)
            except Exception:
                print(e.response.text[:2000], file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
