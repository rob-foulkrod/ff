"""Collection & assembly for modular weekly report generation (new package)."""

from __future__ import annotations

import os
import datetime
import statistics
from typing import Any
import requests

from ff.report.constants import (
    SCHEMA_VERSION,
    WIN_PCT_PLACES,
    POINTS_PLACES,
    BLOWOUT_MARGIN,
    NAIL_BITER_MARGIN,
    SHOOTOUT_COMBINED,
    SLUGFEST_COMBINED,
    CLOSE_GAME_MARGIN,
)
from ff.api.client import SleeperClient
from ff.compute import (
    group_rows as _compute_group_rows,
    compute_standings_with_groups as _compute_standings_with_groups_lib,
    compute_weekly_results as _compute_weekly_results_lib,
    current_streak as _compute_current_streak,
    longest_streaks as _compute_longest_streaks,
)
from .models import WeeklyContext
from .render import md_table as _md_table

BASE_URL = os.environ.get("SLEEPER_BASE_URL", "https://api.sleeper.com/v1")


def _make_client() -> SleeperClient:
    RPM_LIMIT = os.environ.get("SLEEPER_RPM_LIMIT")
    MIN_INTERVAL_MS = os.environ.get("SLEEPER_MIN_INTERVAL_MS")
    try:
        rpm = float(RPM_LIMIT) if RPM_LIMIT else None
    except ValueError:
        rpm = None
    try:
        min_ms = float(MIN_INTERVAL_MS) if MIN_INTERVAL_MS else None
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


def _build_name_maps(users: list[dict], rosters: list[dict]) -> tuple[dict, dict, dict]:
    """Build lookup maps for user & roster naming.

    Returns:
        user_name: user_id -> preferred display (display_name > username > user_id)
        roster_owner_name: roster_id -> owner display name (or fallback)
        roster_team_name: roster_id -> team name set by user (metadata.team_name / roster metadata)
    """
    user_name: dict[str, str] = {}
    user_team: dict[str, str] = {}
    for u in users:
        uid = u.get("user_id")
        if not uid:
            continue
        disp = u.get("display_name") or u.get("username") or uid
        user_name[uid] = disp
        meta = u.get("metadata") or {}
        if isinstance(meta, dict):
            tn = meta.get("team_name") or meta.get("team_name_updated") or meta.get("nickname")
            if tn:
                user_team[uid] = tn
    roster_owner_name: dict[int, str] = {}
    roster_team_name: dict[int, str] = {}
    for r in rosters:
        rid = r.get("roster_id")
        owner = r.get("owner_id")
        chosen_owner = None
        if owner and owner in user_name:
            chosen_owner = owner
        else:
            co = r.get("co_owners") or []
            if isinstance(co, list):
                for uid in co:
                    if uid in user_name:
                        chosen_owner = uid
                        break
        if chosen_owner:
            roster_owner_name[rid] = user_name[chosen_owner]
            if chosen_owner in user_team:
                roster_team_name[rid] = user_team[chosen_owner]
        # Fall back to roster metadata if no user-level team name
        if rid not in roster_team_name:
            rmeta = r.get("metadata") or {}
            if isinstance(rmeta, dict):
                tn = rmeta.get("team_name") or rmeta.get("name")
                if tn:
                    roster_team_name[rid] = tn
        if rid not in roster_owner_name:
            roster_owner_name[rid] = f"Roster {rid}"
        if rid not in roster_team_name:
            roster_team_name[rid] = "-"
    return user_name, roster_owner_name, roster_team_name


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
    _, roster_owner_name, roster_team_name = _build_name_maps(users, rosters)
    weekly_groups = _fetch_weekly_groups(resolved_league_id, start_week, report_week)
    standings = _compute_standings_with_groups(
        resolved_league_id, start_week, report_week, weekly_groups
    )

    # Build initial roster directory (ordered by roster_id); division enrichment added
    # after division_names computed
    roster_directory = []
    for r in sorted(rosters, key=lambda x: int(x.get("roster_id", 0))):
        rid = r.get("roster_id")
        div_id = None
        settings_r = r.get("settings") or {}
        if isinstance(settings_r, dict):
            div_id = settings_r.get("division")
        try:
            div_id_int = int(div_id) if div_id is not None else None
        except (TypeError, ValueError):
            div_id_int = None
        roster_directory.append(
            {
                "roster_id": rid,
                "owner": roster_owner_name.get(rid),
                "team_name": roster_team_name.get(rid, "-"),
                "division_id": div_id_int,
            }
        )
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

    # Advanced Weekly Results enrichment will be executed after divisions computed (later)
    wr_rows: list[list[str]] = []

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

    playoff_rows = 0

    now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    title = (
        f"# Weekly Report - League {resolved_league_id} - Season {resolved_season} - "
        f"Week {report_week}"
    )
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
        ["state_season", state_season],
        ["state_week", str(state_week)],
        ["same_season", "yes" if same_season else "no"],
    ]
    # (Delay metadata injection until all enrichment complete; we'll splice once at end)
    # Expanded metadata additions (league name, division info, counts)
    league_name = league.get("name") or league.get("league_name") or "-"
    divisions = league.get("metadata", {}) or {}
    # Sleeper stores division names like division_1, division_2 in metadata
    division_names = {
        int(k.split("_")[-1]): v
        for k, v in divisions.items()
        if k.startswith("division_") and str(k.split("_")[-1]).isdigit()
    }
    # Enrich roster_directory with division names
    for entry in roster_directory:
        div_id = entry.get("division_id")
        if isinstance(div_id, int) and div_id in division_names:
            entry["division"] = division_names[div_id]
        else:
            entry["division"] = "-"
    division_count_configured = len(division_names)
    # Map roster_id -> division
    roster_division: dict[int, int] = {}
    for r in rosters:
        rid = int(r.get("roster_id"))
        div = r.get("settings", {}).get("division") if isinstance(r.get("settings"), dict) else None
        if div is not None:
            roster_division[rid] = int(div)
    division_count_active = len({d for d in roster_division.values() if d is not None})

    # Compute division standings grouping
    division_standings: list[dict] = []
    if division_count_active > 0:
        by_div: dict[int, list[dict]] = {}
        for rec in standings:
            rid = int(rec.get("roster_id"))
            div = roster_division.get(rid)
            if div is None:
                continue
            by_div.setdefault(div, []).append(rec)
        for div, rows in by_div.items():
            # rank within division
            ranked = []
            for rank, rec in enumerate(rows, start=1):
                ranked.append({"rank": rank, **rec})
            division_standings.append(
                {
                    "division_id": div,
                    "division_name": division_names.get(div, f"Division {div}"),
                    "rows": ranked,
                }
            )
        division_standings.sort(key=lambda d: d["division_id"])  # stable ordering

    # Playoff standings (simple seeding: division winners then next best records)
    playoff_standings: list[dict] = []
    if playoff_teams > 0 and standings:
        # Identify division winners
        div_winners: dict[int, dict] = {}
        for rec in standings:
            rid = int(rec.get("roster_id"))
            div = roster_division.get(rid)
            if div is None:
                continue
            cur = div_winners.get(div)
            if not cur:
                div_winners[div] = rec
            else:
                # Compare by win_pct then points_for
                if (rec.get("win_pct"), rec.get("points_for")) > (
                    cur.get("win_pct"),
                    cur.get("points_for"),
                ):
                    div_winners[div] = rec
        winners_set = {r.get("roster_id") for r in div_winners.values()}
        others = [rec for rec in standings if rec.get("roster_id") not in winners_set]
        seeds = list(div_winners.values()) + others
        seeds = seeds[:playoff_teams]
        for seed_idx, rec in enumerate(seeds, start=1):
            rid = rec.get("roster_id")
            div = roster_division.get(int(rid))
            playoff_standings.append(
                {
                    "seed": seed_idx,
                    "roster_id": rid,
                    "division": division_names.get(div, f"Division {div}") if div else "-",
                    "wins": rec.get("wins"),
                    "losses": rec.get("losses"),
                    "ties": rec.get("ties"),
                    "win_pct": rec.get("win_pct"),
                    "points_for": rec.get("points_for"),
                    "points_against": rec.get("points_against"),
                    "type": "Division Winner" if rid in winners_set else "Wildcard",
                }
            )
    playoff_rows = len(playoff_standings)

    # Advanced Weekly Results enrichment (requires roster_division)
    prior_win_pct: dict[int, float] = {}
    if report_week > start_week:
        _prev = _compute_standings_with_groups(
            resolved_league_id, start_week, report_week - 1, weekly_groups
        )
        for _r in _prev:
            try:
                prior_win_pct[int(_r.get("roster_id"))] = float(_r.get("win_pct") or 0)
            except (TypeError, ValueError):
                continue
    prior_h2h: dict[tuple[int, int], dict[str, int]] = {}
    for wk in range(start_week, report_week):
        for _, entries in (weekly_groups.get(wk, {}) or {}).items():
            if len(entries) != 2:
                continue
            a0, b0 = entries
            aid0 = int(a0.get("roster_id"))
            bid0 = int(b0.get("roster_id"))
            ap0 = float(a0.get("points", 0) or 0)
            bp0 = float(b0.get("points", 0) or 0)
            key0 = (min(aid0, bid0), max(aid0, bid0))
            rec0 = prior_h2h.setdefault(key0, {"a_wins": 0, "b_wins": 0})
            if ap0 > bp0:
                if aid0 < bid0:
                    rec0["a_wins"] += 1
                else:
                    rec0["b_wins"] += 1
            elif bp0 > ap0:
                if aid0 < bid0:
                    rec0["b_wins"] += 1
                else:
                    rec0["a_wins"] += 1
    highest_loser = (None, -1.0)
    lowest_winner = (None, 10**9)
    week_high_points = -1.0
    for m in h2h:
        if len(m.get("rosters", [])) == 2:
            a_, b_ = m["rosters"][0], m["rosters"][1]
            week_high_points = max(week_high_points, float(a_["points"]), float(b_["points"]))

    def _order_and_wrap(flags: list[str]) -> str:
        if not flags:
            return "-"
        # Normalize to key (=value) tokens and sort alphabetically by key then value
        parsed = []
        for f in flags:
            if "=" in f:
                k, v = f.split("=", 1)
                parsed.append((k.strip(), v.strip()))
            else:
                parsed.append((f.strip(), "yes"))
        parsed.sort(key=lambda kv: (kv[0], kv[1]))
        parts = [f"{k}={v}" for k, v in parsed]
        joined = "; ".join(parts)
        # Simple wrap at ~100 chars inserting <br> after nearest '; '
        WIDTH = 100
        if len(joined) <= WIDTH:
            return joined
        out = []
        line = []
        cur_len = 0
        for p in parts:
            seg = p
            if cur_len + len(seg) + (2 if line else 0) > WIDTH:
                out.append("; ".join(line))
                line = [seg]
                cur_len = len(seg)
            else:
                if line:
                    line.append(seg)
                    cur_len += len(seg) + 2
                else:
                    line = [seg]
                    cur_len = len(seg)
        if line:
            out.append("; ".join(line))
        return "<br>".join(out)

    for m in h2h:
        if len(m.get("rosters", [])) != 2:
            continue
        a_, b_ = m["rosters"][0], m["rosters"][1]
        ap = float(a_["points"])
        bp = float(b_["points"])
        winner_id = m.get("winner_roster_id")
        tie = m.get("tie")
        margin = abs(ap - bp)
        total = ap + bp
        if ap > bp:
            winner_points, loser_points = ap, bp
            winner_owner, loser_owner = a_.get("owner"), b_.get("owner")
            loser_id = b_.get("roster_id")
        elif bp > ap:
            winner_points, loser_points = bp, ap
            winner_owner, loser_owner = b_.get("owner"), a_.get("owner")
            loser_id = a_.get("roster_id")
        else:
            winner_points, loser_points = ap, bp
            winner_owner = loser_owner = "-"
            loser_id = None
        if winner_id and winner_points < lowest_winner[1]:
            lowest_winner = (m.get("matchup_id"), winner_points)
        if loser_points > highest_loser[1]:
            highest_loser = (m.get("matchup_id"), loser_points)
        flags: list[str] = []
        if not tie:
            if margin >= BLOWOUT_MARGIN:
                flags.append("blowout=yes")
            if margin <= NAIL_BITER_MARGIN:
                flags.append("nail_biter=yes")
            if winner_points - loser_points <= CLOSE_GAME_MARGIN and margin > NAIL_BITER_MARGIN:
                flags.append("close_game=yes")
        if total >= SHOOTOUT_COMBINED:
            flags.append("shootout=yes")
        if total <= SLUGFEST_COMBINED:
            flags.append("slugfest=yes")
        aid = int(a_.get("roster_id"))
        bid = int(b_.get("roster_id"))
        if roster_division.get(aid) and roster_division.get(aid) == roster_division.get(bid):
            flags.append("division_game=yes")
        if (
            winner_id
            and loser_id
            and prior_win_pct.get(int(winner_id), 0) < prior_win_pct.get(int(loser_id), 0)
        ):
            flags.append("upset=yes")
        if winner_points == week_high_points:
            flags.append("winner_highest_score_week=yes")
        if not tie and loser_points >= 180 and margin <= 20:
            flags.append("bad_beat=yes")
        if winner_id:
            seq_w = weekly_results_all.get(int(winner_id), [])
            ctype_w, clen_w, *_ = (
                _compute_current_streak(seq_w, report_week) if seq_w else (None, 0, None, None)
            )
            if ctype_w == "W" and clen_w >= 4:
                flags.append(f"extended_win_streak={clen_w}")
        if loser_id:
            seq_l = weekly_results_all.get(int(loser_id), [])
            ctype_prev, clen_prev, *_ = (
                _compute_current_streak([t for t in seq_l if t[0] < report_week], report_week - 1)
                if seq_l
                else (None, 0, None, None)
            )
            if ctype_prev == "W" and clen_prev >= 2 and not tie:
                flags.append("broke_opponent_streak=yes")
                flags.append(f"opponent_prev_streak_type={ctype_prev}")
                flags.append(f"opponent_prev_streak_len={clen_prev}")
        key = (min(aid, bid), max(aid, bid))
        prev_counts = prior_h2h.get(key, {"a_wins": 0, "b_wins": 0})
        a_w_prev = prev_counts["a_wins"]
        b_w_prev = prev_counts["b_wins"]
        a_w_new, b_w_new = a_w_prev, b_w_prev
        if winner_id:
            if aid < bid:
                if int(winner_id) == aid:
                    a_w_new += 1
                elif int(winner_id) == bid:
                    b_w_new += 1
            else:
                if int(winner_id) == bid:
                    a_w_new += 1
                elif int(winner_id) == aid:
                    b_w_new += 1
        if winner_id:
            if a_w_new > 0 and b_w_new == 0:
                flags.append("season_series_sweep=yes")
            elif b_w_new > 0 and a_w_new == 0:
                flags.append("season_series_sweep=yes")
            elif a_w_new == b_w_new and a_w_new > 0:
                flags.append("evened_series=yes")
        if not tie:
            flags.append(f"margin_pts={margin:.2f}")
        wr_rows.append(
            [
                str(m.get("matchup_id")),
                f"{a_.get('roster_id')} - {a_.get('owner')}",
                f"{ap:.2f}",
                f"{b_.get('roster_id')} - {b_.get('owner')}",
                f"{bp:.2f}",
                str(winner_id or "-"),
                winner_owner if winner_id else "-",
                loser_owner if winner_id else "-",
                "yes" if tie else "no",
                _order_and_wrap(flags),
            ]
        )

    # Head-to-head cumulative grid
    roster_ids_sorted = [r["roster_id"] for r in roster_directory]
    # Initialize matrix counts
    matrix: dict[tuple[int, int], tuple[int, int]] = {}  # (a,b) -> (a_wins, b_wins)
    for wk in range(start_week, report_week + 1):
        groups_wk = weekly_groups.get(wk, {})
        for _, entries in (groups_wk or {}).items():
            if len(entries) != 2:
                continue
            a, b = entries
            aid = int(a.get("roster_id"))
            bid = int(b.get("roster_id"))
            ap = float(a.get("points", 0) or 0)
            bp = float(b.get("points", 0) or 0)
            key = (aid, bid)
            cur = matrix.get(key, (0, 0))
            if ap > bp:
                cur = (cur[0] + 1, cur[1])
            elif bp > ap:
                cur = (cur[0], cur[1] + 1)
            else:  # tie counts as half? store separately as no change
                pass
            matrix[key] = cur
    # Build grid lines
    h2h_grid: list[list[str]] = []
    header = [""] + [
        f"{rid}-{roster_owner_name.get(rid, 'Roster '+str(rid))}" for rid in roster_ids_sorted
    ]
    h2h_grid.append(header)
    for rid_a in roster_ids_sorted:
        row = [f"{rid_a}-{roster_owner_name.get(rid_a, 'Roster '+str(rid_a))}"]
        for rid_b in roster_ids_sorted:
            if rid_a == rid_b:
                row.append("-")
            else:
                key = (rid_a, rid_b)
                rev = (rid_b, rid_a)
                rec_ab = matrix.get(key, (0, 0))
                rec_ba = matrix.get(rev, (0, 0))
                wins_a = rec_ab[0] + rec_ba[1]
                wins_b = rec_ab[1] + rec_ba[0]
                row.append(f"{wins_a}-{wins_b}")
        h2h_grid.append(row)

    # --- New Derived Enhancements: All-Play, Median, Margin Summary, Division Power ---
    roster_ids = [r["roster_id"] for r in roster_directory]
    team_names_map = {r["roster_id"]: r.get("owner") for r in roster_directory}
    week_team_points: dict[int, dict[int, float]] = {}
    for wk in range(start_week, report_week + 1):
        wk_points: dict[int, float] = {}
        for _, entries in (weekly_groups.get(wk, {}) or {}).items():
            for e in entries:
                try:
                    rid = int(e.get("roster_id"))
                except (TypeError, ValueError):
                    continue
                wk_points[rid] = float(e.get("points", 0) or 0.0)
        week_team_points[wk] = wk_points
    cumulative_all_play: dict[int, dict[str, float]] = {
        rid: {"w": 0.0, "l": 0.0} for rid in roster_ids
    }
    cumulative_median: dict[int, dict[str, float]] = {
        rid: {"w": 0.0, "l": 0.0} for rid in roster_ids
    }
    for wk, pts_map in week_team_points.items():
        if not pts_map:
            continue
        scores = list(pts_map.values())
        n = len(scores)
        if n < 2:
            continue
        for rid, score in pts_map.items():
            wins = sum(1 for s in scores if s < score)
            ties = sum(1 for s in scores if s == score) - 1
            all_play_w = wins + 0.5 * ties
            all_play_l = (n - 1) - all_play_w
            cumulative_all_play[rid]["w"] += all_play_w
            cumulative_all_play[rid]["l"] += all_play_l
        scores_sorted = sorted(scores)
        mid = n // 2
        if n % 2 == 1:
            median_val = scores_sorted[mid]
        else:
            median_val = 0.5 * (scores_sorted[mid - 1] + scores_sorted[mid])
        for rid, score in pts_map.items():
            if score > median_val:
                cumulative_median[rid]["w"] += 1
            elif score < median_val:
                cumulative_median[rid]["l"] += 1
            else:
                cumulative_median[rid]["w"] += 0.5
                cumulative_median[rid]["l"] += 0.5
    actual_wins_map = {}
    for rec in standings:
        try:
            actual_wins_map[int(rec.get("roster_id"))] = float(rec.get("wins") or 0)
        except (TypeError, ValueError):
            pass
    n_teams = len(roster_ids)
    all_play_records: list[dict] = []
    median_records: list[dict] = []
    for rid in roster_ids:
        ap_w = cumulative_all_play[rid]["w"]
        ap_l = cumulative_all_play[rid]["l"]
        ap_pct = (ap_w / (ap_w + ap_l)) if (ap_w + ap_l) > 0 else 0.0
        expected_wins = ap_w / max(1, (n_teams - 1))
        luck_diff = actual_wins_map.get(rid, 0.0) - expected_wins
        med_w = cumulative_median[rid]["w"]
        med_l = cumulative_median[rid]["l"]
        med_pct = (med_w / (med_w + med_l)) if (med_w + med_l) > 0 else 0.0
        all_play_records.append(
            {
                "roster_id": rid,
                "owner": team_names_map.get(rid),
                "all_play_w": round(ap_w, 2),
                "all_play_l": round(ap_l, 2),
                "all_play_pct": round(ap_pct, 4),
                "expected_wins": round(expected_wins, 2),
                "actual_wins": actual_wins_map.get(rid, 0.0),
                "luck_diff": round(luck_diff, 2),
            }
        )
        median_records.append(
            {
                "roster_id": rid,
                "owner": team_names_map.get(rid),
                "median_w": round(med_w, 2),
                "median_l": round(med_l, 2),
                "median_pct": round(med_pct, 4),
            }
        )

    def _matchup_margins_through(wk_end: int) -> list[float]:
        vals: list[float] = []
        for wk in range(start_week, wk_end + 1):
            for _, entries in (weekly_groups.get(wk, {}) or {}).items():
                if len(entries) != 2:
                    continue
                a, b = entries
                ap = float(a.get("points", 0) or 0)
                bp = float(b.get("points", 0) or 0)
                vals.append(abs(ap - bp))
        return vals

    # Build detailed matchup margin records to allow structured extremes
    matchup_margin_details: list[dict] = []
    for wk in range(start_week, report_week + 1):
        for mid, entries in (weekly_groups.get(wk, {}) or {}).items():
            if len(entries) != 2:
                continue
            a_i, b_i = entries
            ap_i = float(a_i.get("points", 0) or 0)
            bp_i = float(b_i.get("points", 0) or 0)
            if ap_i > bp_i:
                winner, loser = a_i, b_i
                winner_pts, loser_pts = ap_i, bp_i
            elif bp_i > ap_i:
                winner, loser = b_i, a_i
                winner_pts, loser_pts = bp_i, ap_i
            else:
                winner, loser = a_i, b_i
                winner_pts, loser_pts = ap_i, bp_i
            matchup_margin_details.append(
                {
                    "week": wk,
                    "matchup_id": mid,
                    "margin": round(abs(ap_i - bp_i), 2),
                    "winner_id": winner.get("roster_id"),
                    "loser_id": loser.get("roster_id"),
                    "winner_owner": roster_owner_name.get(winner.get("roster_id")),
                    "loser_owner": roster_owner_name.get(loser.get("roster_id")),
                    "winner_points": winner_pts,
                    "loser_points": loser_pts,
                    "tie": ap_i == bp_i,
                }
            )

    def _convert_game(d: dict) -> dict:
        return {
            "week": d["week"],
            "matchup_id": d["matchup_id"],
            "margin": d["margin"],
            "tie": d["tie"],
            "winner": {
                "roster_id": d.get("winner_id"),
                "owner": d.get("winner_owner"),
                "points": d.get("winner_points"),
            },
            "loser": {
                "roster_id": d.get("loser_id"),
                "owner": d.get("loser_owner"),
                "points": d.get("loser_points"),
            },
        }

    margin_summary: dict[str, dict] = {}
    # Weekly extremes
    week_games = [d for d in matchup_margin_details if d["week"] == report_week]
    if week_games:
        largest_week = max(week_games, key=lambda d: d["margin"])
        smallest_week = min(week_games, key=lambda d: d["margin"])
        margin_summary["week"] = {
            "largest": _convert_game(largest_week),
            "smallest": _convert_game(smallest_week),
            "average_margin": round(sum(g["margin"] for g in week_games) / len(week_games), 2),
        }
    # Season-through extremes
    if matchup_margin_details:
        largest_season = max(matchup_margin_details, key=lambda d: d["margin"])
        smallest_season = min(matchup_margin_details, key=lambda d: d["margin"])
        margin_summary["season_through"] = {
            "largest": _convert_game(largest_season),
            "smallest": _convert_game(smallest_season),
            "average_margin": round(
                sum(g["margin"] for g in matchup_margin_details) / len(matchup_margin_details), 2
            ),
        }
    division_power_week: list[dict] = []
    division_power_season: list[dict] = []
    if division_count_active > 0:
        wk_pts_map = week_team_points.get(report_week, {})
        week_wl: dict[int, dict[str, int]] = {rid: {"w": 0, "l": 0} for rid in roster_ids}
        for _, entries in (weekly_groups.get(report_week, {}) or {}).items():
            if len(entries) != 2:
                continue
            a, b = entries
            aid = int(a.get("roster_id"))
            bid = int(b.get("roster_id"))
            ap = float(a.get("points", 0) or 0)
            bp = float(b.get("points", 0) or 0)
            if ap > bp:
                week_wl[aid]["w"] += 1
                week_wl[bid]["l"] += 1
            elif bp > ap:
                week_wl[bid]["w"] += 1
                week_wl[aid]["l"] += 1
        by_div_week: dict[int, list[int]] = {}
        for rid in roster_ids:
            d = roster_division.get(rid)
            if d is not None:
                by_div_week.setdefault(d, []).append(rid)
        for div, members in by_div_week.items():
            member_pts = [wk_pts_map.get(rid, 0.0) for rid in members]
            w = sum(week_wl[rid]["w"] for rid in members)
            l = sum(week_wl[rid]["l"] for rid in members)
            division_power_week.append(
                {
                    "division_id": div,
                    "division_name": division_names.get(div, f"Division {div}"),
                    "team_count": len(members),
                    "week_points_total": round(sum(member_pts), 2),
                    "week_points_avg": (
                        round(sum(member_pts) / len(member_pts), 2) if member_pts else 0.0
                    ),
                    "week_wins": w,
                    "week_losses": l,
                }
            )
        by_div_season: dict[int, list[dict]] = {}
        for rec in standings:
            try:
                rid = int(rec.get("roster_id"))
            except (TypeError, ValueError):
                continue
            d = roster_division.get(rid)
            if d is not None:
                by_div_season.setdefault(d, []).append(rec)
        for div, rows in by_div_season.items():
            total_pf = sum(float(r.get("points_for") or 0) for r in rows)
            total_pa = sum(float(r.get("points_against") or 0) for r in rows)
            total_w = sum(int(r.get("wins") or 0) for r in rows)
            total_l = sum(int(r.get("losses") or 0) for r in rows)
            total_t = sum(int(r.get("ties") or 0) for r in rows)
            games = (total_w + total_l + total_t) / max(1, len(rows))
            division_power_season.append(
                {
                    "division_id": div,
                    "division_name": division_names.get(div, f"Division {div}"),
                    "team_count": len(rows),
                    "season_points_for": round(total_pf, 2),
                    "season_points_against": round(total_pa, 2),
                    "pf_per_team_pg": round((total_pf / len(rows)) / games, 2) if games else 0.0,
                    "pa_per_team_pg": round((total_pa / len(rows)) / games, 2) if games else 0.0,
                    "agg_wins": total_w,
                    "agg_losses": total_l,
                    "agg_ties": total_t,
                    "agg_win_pct": round(total_w / max(1, (total_w + total_l + total_t)), 4),
                }
            )
    enhancements_md: list[str] = []
    # Build consolidated per-team summary now that we have all derived metrics
    teams_summary: list[dict] = []
    for rid in roster_ids:
        team_entry = {
            "roster_id": rid,
            "owner": team_names_map.get(rid),
            "division_id": next(
                (rd.get("division_id") for rd in roster_directory if rd.get("roster_id") == rid),
                None,
            ),
            "all_play_w": (
                next(
                    (r["all_play_w"] for r in all_play_records if r["roster_id"] == rid),
                    None,
                )
                if all_play_records
                else None
            ),
            "all_play_l": (
                next(
                    (r["all_play_l"] for r in all_play_records if r["roster_id"] == rid),
                    None,
                )
                if all_play_records
                else None
            ),
            "all_play_pct": (
                next(
                    (r["all_play_pct"] for r in all_play_records if r["roster_id"] == rid),
                    None,
                )
                if all_play_records
                else None
            ),
            "median_w": (
                next(
                    (r["median_w"] for r in median_records if r["roster_id"] == rid),
                    None,
                )
                if median_records
                else None
            ),
            "median_l": (
                next(
                    (r["median_l"] for r in median_records if r["roster_id"] == rid),
                    None,
                )
                if median_records
                else None
            ),
            "median_pct": (
                next(
                    (r["median_pct"] for r in median_records if r["roster_id"] == rid),
                    None,
                )
                if median_records
                else None
            ),
            "expected_wins": (
                next(
                    (r["expected_wins"] for r in all_play_records if r["roster_id"] == rid),
                    None,
                )
                if all_play_records
                else None
            ),
            "actual_wins": (
                next(
                    (r["actual_wins"] for r in all_play_records if r["roster_id"] == rid),
                    None,
                )
                if all_play_records
                else None
            ),
            "luck_diff": (
                next(
                    (r["luck_diff"] for r in all_play_records if r["roster_id"] == rid),
                    None,
                )
                if all_play_records
                else None
            ),
        }
        teams_summary.append(team_entry)
    if all_play_records:
        enhancements_md.append(f"## All-Play & Median Records Through Week {report_week}")
        enhancements_md += _md_table(
            [
                "roster_id",
                "owner",
                "all_play_w",
                "all_play_l",
                "all_play_pct",
                "median_w",
                "median_l",
                "median_pct",
                "actual_wins",
                "expected_wins",
                "luck_diff",
            ],
            [
                [
                    r["roster_id"],
                    r["owner"],
                    r["all_play_w"],
                    r["all_play_l"],
                    f"{r['all_play_pct']:.4f}",
                    *(
                        lambda _rid: [
                            next(m["median_w"] for m in median_records if m["roster_id"] == _rid),
                            next(m["median_l"] for m in median_records if m["roster_id"] == _rid),
                            (lambda _mp: f"{_mp:.4f}")(
                                next(
                                    m["median_pct"]
                                    for m in median_records
                                    if m["roster_id"] == _rid
                                )
                            ),
                        ]
                    )(_rid := r["roster_id"]),
                    r["actual_wins"],
                    r["expected_wins"],
                    r["luck_diff"],
                ]
                for r in all_play_records
            ],
        ) + [""]
    if margin_summary:
        enhancements_md.append(f"## Margin Summary Week {report_week}")
        # Week extremes table
        week_part = margin_summary.get("week")
        if week_part:
            enhancements_md.append("### Weekly Extremes")
            week_rows = []
            for label in ("largest", "smallest"):
                g = week_part.get(label)
                if not g:
                    continue
                week_rows.append(
                    [
                        label,
                        g["winner"].get("owner"),
                        g["loser"].get("owner"),
                        f"{g['winner'].get('points'):.2f}",
                        f"{g['loser'].get('points'):.2f}",
                        f"{g['margin']:.2f}",
                        g["matchup_id"],
                        g["week"],
                    ]
                )
            enhancements_md += _md_table(
                [
                    "type",
                    "winner",
                    "loser",
                    "winner_pts",
                    "loser_pts",
                    "margin",
                    "matchup_id",
                    "week",
                ],
                week_rows,
            ) + [""]
            enhancements_md += _md_table(
                ["scope", "average_margin"],
                [["week", f"{week_part.get('average_margin'):.2f}"]],
            ) + [""]
        season_part = margin_summary.get("season_through")
        if season_part:
            enhancements_md.append("### Season-To-Date Extremes")
            season_rows = []
            for label in ("largest", "smallest"):
                g = season_part.get(label)
                if not g:
                    continue
                season_rows.append(
                    [
                        label,
                        g["winner"].get("owner"),
                        g["loser"].get("owner"),
                        f"{g['winner'].get('points'):.2f}",
                        f"{g['loser'].get('points'):.2f}",
                        f"{g['margin']:.2f}",
                        g["matchup_id"],
                        g["week"],
                    ]
                )
            enhancements_md += _md_table(
                [
                    "type",
                    "winner",
                    "loser",
                    "winner_pts",
                    "loser_pts",
                    "margin",
                    "matchup_id",
                    "week",
                ],
                season_rows,
            ) + [""]
            enhancements_md += _md_table(
                ["scope", "average_margin"],
                [["season_through", f"{season_part.get('average_margin'):.2f}"]],
            ) + [""]
    if division_power_week:
        enhancements_md.append(f"## Division Power Week {report_week}")
        enhancements_md += _md_table(
            [
                "division_id",
                "division_name",
                "team_count",
                "week_points_total",
                "week_points_avg",
                "week_wins",
                "week_losses",
            ],
            [
                [
                    d["division_id"],
                    d["division_name"],
                    d["team_count"],
                    d["week_points_total"],
                    d["week_points_avg"],
                    d["week_wins"],
                    d["week_losses"],
                ]
                for d in division_power_week
            ],
        ) + [""]
    if division_power_season:
        enhancements_md.append(f"## Division Power Season Through Week {report_week}")
        enhancements_md += _md_table(
            [
                "division_id",
                "division_name",
                "team_count",
                "season_points_for",
                "season_points_against",
                "pf_per_team_pg",
                "pa_per_team_pg",
                "agg_wins",
                "agg_losses",
                "agg_ties",
                "agg_win_pct",
            ],
            [
                [
                    d["division_id"],
                    d["division_name"],
                    d["team_count"],
                    d["season_points_for"],
                    d["season_points_against"],
                    d["pf_per_team_pg"],
                    d["pa_per_team_pg"],
                    d["agg_wins"],
                    d["agg_losses"],
                    d["agg_ties"],
                    f"{d['agg_win_pct']:.4f}",
                ]
                for d in division_power_season
            ],
        ) + [""]
    # Defer adding enhancements until after the Head-to-Head Grid so current week info appears earlier.

    # Insert enriched metadata additions
    season_phase = "regular" if report_week < playoff_week_start else "playoffs"
    meta_rows.extend(
        [
            ["league_name", league_name],
            ["standings_through_week", str(report_week)],
            ["head_to_head_week", str(report_week)],
            ["preview_week", str(preview_week if preview_week > 0 else "-")],
            ["num_teams", str(len(roster_directory))],
            ["standings_rows", str(len(standings))],
            ["h2h_rows", str(len(h2h))],
            ["weekly_results_rows", str(len(wr_rows))],
            ["preview_rows", str(len(preview))],
            ["playoff_rows", str(playoff_rows)],
            ["streaks_rows", str(len(streak_rows))],
            ["division_count_configured", str(division_count_configured)],
            ["division_count_active", str(division_count_active)],
            ["season_phase", season_phase],
            ["details_format", "kv;sep=';';kvsep='=';sparse=yes"],
        ]
    )
    # Append division names to metadata
    for div_id, name in division_names.items():
        meta_rows.append([f"division_{div_id}_name", name])

    # Prepare base metadata block but delay injection until after enrichment (end of function)

    # Roster Directory
    if roster_directory:
        md_lines.append("## Roster Directory")
        md_lines += _md_table(
            ["roster_id", "owner", "team_name", "division_id", "division"],
            [
                [
                    r.get("roster_id"),
                    r.get("owner"),
                    r.get("team_name", "-"),
                    (r.get("division_id") if r.get("division_id") is not None else "-"),
                    r.get("division", "-"),
                ]
                for r in roster_directory
            ],
        ) + [""]

    # Weekly Results
    if wr_rows:
        # annotate highest loser / lowest winner flags retroactively
        for row in wr_rows:
            mid = row[0]
            details_idx = 9
            if row[details_idx] != "-":
                details = [
                    c.strip()
                    for c in row[details_idx].replace("<br>", "; ").split(";")
                    if c.strip()
                ]
            else:
                details = []
            if str(highest_loser[0]) == mid:
                details.append("highest_loser_score_week=yes")
            if str(lowest_winner[0]) == mid:
                details.append("lowest_winner_score_week=yes")
            row[details_idx] = _order_and_wrap(details)
        md_lines.append(f"## Weekly Results Week {report_week}")
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
        ) + [""]

    # Overall Standings (enriched)
    if standings:
        # prior week standings for rank change
        prior_rank: dict[int, int] = {}
        if report_week > start_week:
            prev_standings = _compute_standings_with_groups(
                resolved_league_id, start_week, report_week - 1, weekly_groups
            )
            for idx, rec in enumerate(prev_standings, start=1):
                try:
                    prior_rank[int(rec.get("roster_id"))] = idx
                except (TypeError, ValueError):
                    continue
        standings_rows: list[list[str]] = []
        for rank, rec in enumerate(standings, start=1):
            rid = int(rec.get("roster_id"))
            wins = rec.get("wins")
            losses = rec.get("losses")
            ties = rec.get("ties")
            gp = (wins or 0) + (losses or 0) + (ties or 0)
            pf = float(rec.get("points_for") or 0)
            pa = float(rec.get("points_against") or 0)
            pf_pg = pf / gp if gp else 0.0
            pa_pg = pa / gp if gp else 0.0
            diff = pf - pa
            # current streak
            seq = weekly_results_all.get(rid)
            ctype, clen, *_ = (
                _compute_current_streak(seq, report_week) if seq else (None, 0, None, None)
            )
            if ctype == "W":
                cur_streak = f"W{clen}"
            elif ctype == "L":
                cur_streak = f"L{clen}"
            else:
                cur_streak = "-"
            pr = prior_rank.get(rid)
            if pr is None:
                rank_change = "-"
            else:
                delta = pr - rank
                if delta > 0:
                    rank_change = f"+{delta}"
                elif delta < 0:
                    rank_change = f"{delta}"
                else:
                    rank_change = "0"
            standings_rows.append(
                [
                    str(rank),
                    str(rid),
                    roster_owner_name.get(rid, f"Roster {rid}"),
                    str(wins),
                    str(losses),
                    str(ties),
                    f"{rec.get('win_pct'):.{WIN_PCT_PLACES}f}",
                    f"{pf:.{POINTS_PLACES}f}",
                    f"{pa:.{POINTS_PLACES}f}",
                    f"{pf_pg:.2f}",
                    f"{pa_pg:.2f}",
                    f"{diff:.2f}",
                    cur_streak,
                    rank_change,
                ]
            )
        md_lines.append(f"## Standings Through Week {report_week}")
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
                "PF_pg",
                "PA_pg",
                "diff",
                "streak",
                "rank_change",
            ],
            standings_rows,
        ) + [""]

    # Division Standings
    if division_standings:
        md_lines.append(f"## Division Standings Through Week {report_week}")
        for div in division_standings:
            md_lines.append(f"### {div['division_name']}")
            div_rows = []
            for rec in div["rows"]:
                rid = rec.get("roster_id")
                wins = rec.get("wins")
                losses = rec.get("losses")
                ties = rec.get("ties")
                gp = (wins or 0) + (losses or 0) + (ties or 0)
                seq = weekly_results_all.get(int(rid), [])
                ctype, clen, *_ = (
                    _compute_current_streak(seq, report_week) if seq else (None, 0, None, None)
                )
                if ctype == "W":
                    cur_streak = f"W{clen}"
                elif ctype == "L":
                    cur_streak = f"L{clen}"
                else:
                    cur_streak = "-"
                div_rows.append(
                    [
                        rec.get("rank"),
                        rid,
                        roster_owner_name.get(int(rid), f"Roster {rid}"),
                        wins,
                        losses,
                        ties,
                        f"{rec.get('win_pct'):.{WIN_PCT_PLACES}f}",
                        f"{rec.get('points_for'):.{POINTS_PLACES}f}",
                        f"{rec.get('points_against'):.{POINTS_PLACES}f}",
                        str(gp),
                        cur_streak,
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
                div_rows,
            ) + [""]

    # Playoff Standings
    if playoff_standings:
        md_lines.append(f"## Playoff Standings Through Week {report_week}")
        po_rows = []
        seeded_ids = {rec.get("roster_id") for rec in playoff_standings}
        first_out = None
        for rec in standings:
            if rec.get("roster_id") not in seeded_ids:
                first_out = rec
                break
        for rec in playoff_standings:
            rid = int(rec.get("roster_id"))
            wins = rec.get("wins")
            losses = rec.get("losses")
            ties = rec.get("ties")
            gp = wins + losses + ties
            seq = weekly_results_all.get(rid, [])
            ctype, clen, *_ = (
                _compute_current_streak(seq, report_week) if seq else (None, 0, None, None)
            )
            cur_streak = f"{ctype}{clen}" if ctype in {"W", "L"} else "-"
            po_rows.append(
                [
                    rec.get("seed"),
                    rid,
                    roster_owner_name.get(rid, f"Roster {rid}"),
                    rec.get("division"),
                    rec.get("type"),
                    wins,
                    losses,
                    ties,
                    f"{rec.get('win_pct'):.{WIN_PCT_PLACES}f}",
                    f"{float(rec.get('points_for')):.{POINTS_PLACES}f}",
                    f"{float(rec.get('points_against')):.{POINTS_PLACES}f}",
                    gp,
                    cur_streak,
                ]
            )
        if first_out:
            rid = int(first_out.get("roster_id"))
            wins = first_out.get("wins")
            losses = first_out.get("losses")
            ties = first_out.get("ties")
            gp = wins + losses + ties
            seq = weekly_results_all.get(rid, [])
            ctype, clen, *_ = (
                _compute_current_streak(seq, report_week) if seq else (None, 0, None, None)
            )
            cur_streak = f"{ctype}{clen}" if ctype in {"W", "L"} else "-"
            div = roster_division.get(rid)
            po_rows.append(
                [
                    "-",
                    rid,
                    roster_owner_name.get(rid, f"Roster {rid}"),
                    division_names.get(div, f"Division {div}") if div else "-",
                    "In the Hunt",
                    wins,
                    losses,
                    ties,
                    f"{first_out.get('win_pct'):.{WIN_PCT_PLACES}f}",
                    f"{float(first_out.get('points_for')):.{POINTS_PLACES}f}",
                    f"{float(first_out.get('points_against')):.{POINTS_PLACES}f}",
                    gp,
                    cur_streak,
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
            po_rows,
        ) + [""]

    # Head-to-Head Grid
    if h2h_grid:
        md_lines.append(f"## Head-to-Head Grid Through Week {report_week}")
        md_lines += _md_table(h2h_grid[0], h2h_grid[1:]) + [""]
        # Insert enhancements after the cumulative grid (historical analytics below core current-week sections)
        if enhancements_md:
            md_lines.extend(enhancements_md)

    # (Removed simplified duplicate Head-to-Head Results section to avoid repetition with Weekly Results.)

    # Upcoming Preview
    if preview:
        md_lines.append(f"## Upcoming Week Preview Week {preview_week}")
        preview_rows: list[list[str]] = []
        for m in preview:
            ro = m.get("rosters") or []
            a = ro[0] if len(ro) > 0 else {}
            b = ro[1] if len(ro) > 1 else {}
            preview_rows.append(
                [
                    str(m.get("matchup_id")),
                    f"{a.get('roster_id')}-{a.get('owner')}" if a else "-",
                    f"{b.get('roster_id')}-{b.get('owner')}" if b else "-",
                    "-",
                ]
            )
        md_lines += _md_table(["matchup_id", "roster_a", "roster_b", "details"], preview_rows) + [
            ""
        ]

    # Streaks
    if streak_rows:
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
        ) + [""]

    # Enrich meta with week aggregate stats & season high/low
    week_points: list[float] = []
    for row in wr_rows:
        try:
            week_points.append(float(row[2]))
            week_points.append(float(row[4]))
        except (TypeError, ValueError):
            continue
    if week_points:
        week_avg = sum(week_points) / len(week_points)
        week_med = statistics.median(week_points)
        week_high = max(week_points)
        week_low = min(week_points)
        meta_rows.extend(
            [
                ["week_points_avg", f"{week_avg:.2f}"],
                ["week_points_median", f"{week_med:.2f}"],
                ["week_high", f"{week_high:.2f}"],
                ["week_low", f"{week_low:.2f}"],
            ]
        )
    all_points_through: list[float] = []
    for wk in range(start_week, report_week + 1):
        for _, entries in (weekly_groups.get(wk, {}) or {}).items():
            for e in entries:
                all_points_through.append(float(e.get("points", 0) or 0))
    if all_points_through:
        meta_rows.append(["season_high_through_week", f"{max(all_points_through):.2f}"])
        meta_rows.append(["season_low_through_week", f"{min(all_points_through):.2f}"])

    # Finally inject metadata at top (after title & blank)
    meta_block = ["## Metadata"] + _md_table(["key", "value"], meta_rows) + [""]
    md_lines[2:2] = meta_block

    # Optional sections
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
        teams_summary=teams_summary,
        roster_directory=roster_directory,
        division_standings=division_standings,
        playoff_standings=playoff_standings,
        h2h_grid=h2h_grid,
        meta_rows=meta_rows,
        markdown_lines=md_lines,
        all_play_records=all_play_records,
        median_records=median_records,
        margin_summary=margin_summary,
        division_power_week=division_power_week,
        division_power_season=division_power_season,
    )


__all__ = ["build_weekly_context", "_resolve_league_for_season"]
