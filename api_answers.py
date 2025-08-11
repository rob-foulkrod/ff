import os
import sys
import json
import datetime
import time
from typing import Any, Callable

import requests

# Defaults based on project context; override with env vars when needed
BASE_URL = os.environ.get("SLEEPER_BASE_URL", "https://api.sleeper.com/v1")
LEAGUE_ID = os.environ.get("SLEEPER_LEAGUE_ID", "1180276953741729792")
SPORT = os.environ.get("SLEEPER_SPORT", "nfl")
SEASON = os.environ.get("SLEEPER_SEASON", "2025")
USER_ID = os.environ.get("SLEEPER_USER_ID", "robfoulk")


def _get(url: str) -> requests.Response:
    # Throttle to respect RPM; defaults keep us far below 1000/min
    _throttle()
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r


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
    # default to 100ms per call (~600 rpm)
    _MIN_INTERVAL_SEC = 0.10

_last_call_ts = 0.0


def _throttle() -> None:
    global _last_call_ts
    now = time.monotonic()
    elapsed = now - _last_call_ts if _last_call_ts else None
    if elapsed is not None and elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)
    _last_call_ts = time.monotonic()


# --- Answers go below ---


def answer_get_league_information(league_id: str = LEAGUE_ID) -> dict:
    """Question: get league information"""
    url = f"{BASE_URL}/league/{league_id}"
    return _get(url).json()


def answer_get_roster(league_id: str = LEAGUE_ID, roster_id: int | None = None) -> Any:
    """Question: get a roster
    - If roster_id provided, returns that roster dict; else returns the list of rosters.
    """
    url = f"{BASE_URL}/league/{league_id}/rosters"
    rosters = _get(url).json()
    if roster_id is None:
        return rosters
    for r in rosters:
        if r.get("roster_id") == roster_id:
            return r
    raise ValueError(f"Roster with roster_id={roster_id} not found in league {league_id}")


def answer_get_my_roster_id(league_id: str = LEAGUE_ID, username: str = USER_ID) -> dict:
    """Question: what is my current roster_id?
    - Resolves the given username to a user_id via /user/{username}
    - Scans /league/{league_id}/rosters to find the roster where owner_id matches (or co_owners contains) that user_id.
    Returns: { "league_id": str, "username": str, "user_id": str, "roster_id": int, "role": "owner"|"co_owner" }
    """
    # 1) Resolve username -> user_id
    user_url = f"{BASE_URL}/user/{username}"
    user = _get(user_url).json()
    uid = user.get("user_id") or user.get("userID") or user.get("uid")
    if not uid:
        raise ValueError(f"Could not resolve user_id for username '{username}'")

    # 2) Fetch rosters and locate user's roster
    rosters = _get(f"{BASE_URL}/league/{league_id}/rosters").json()
    for r in rosters:
        if r.get("owner_id") == uid:
            return {
                "league_id": league_id,
                "username": username,
                "user_id": uid,
                "roster_id": r.get("roster_id"),
                "role": "owner",
            }
        co = r.get("co_owners")
        if isinstance(co, list) and uid in co:
            return {
                "league_id": league_id,
                "username": username,
                "user_id": uid,
                "roster_id": r.get("roster_id"),
                "role": "co_owner",
            }
    raise ValueError(f"User '{username}' (id {uid}) does not own a roster in league {league_id}")


def answer_get_current_draft_id(league_id: str = LEAGUE_ID) -> dict:
    """Question: what is the current draft_id?
    - Returns the league's draft_id when present.
    - Fallback: checks /league/{league_id}/drafts and returns the first draft's id if available.
    Returns: { "league_id": str, "draft_id": str }
    """
    league = _get(f"{BASE_URL}/league/{league_id}").json()
    draft_id = league.get("draft_id")
    if not draft_id:
        drafts = _get(f"{BASE_URL}/league/{league_id}/drafts").json()
        if isinstance(drafts, list) and drafts:
            # Prefer an active draft if such a flag exists, else take the first
            candidate = next(
                (d for d in drafts if d.get("status") in {"pre_draft", "drafting"}), drafts[0]
            )
            draft_id = candidate.get("draft_id") or candidate.get("id")
    if not draft_id:
        raise ValueError(f"No draft_id found for league {league_id}")
    return {"league_id": league_id, "draft_id": str(draft_id)}


def answer_what_round_was_player_drafted_last_year(
    player_name: str = "Justin Jefferson",
    league_id: str = LEAGUE_ID,
    sport: str = SPORT,
) -> dict:
    """Question: Last Year, a team drafted <player_name>. What round was he drafted in?
    Steps:
      1) Get current league -> previous_league_id
      2) Get previous league's draft_id (or pick one from /drafts)
      3) Fetch /draft/{draft_id}/picks
      4) Resolve player_name -> player_id via /players/{sport}
      5) Find matching pick and return round
    Returns: { previous_league_id, season, draft_id, player_name, player_id, round }
    """
    # 1) Resolve previous league
    current = _get(f"{BASE_URL}/league/{league_id}").json()
    prev_id = current.get("previous_league_id")
    if not prev_id:
        raise ValueError(
            f"League {league_id} has no previous_league_id; cannot determine last year's draft"
        )
    prev = _get(f"{BASE_URL}/league/{prev_id}").json()
    season = prev.get("season")

    # 2) Get draft_id
    draft_id = prev.get("draft_id")
    if not draft_id:
        drafts = _get(f"{BASE_URL}/league/{prev_id}/drafts").json()
        if isinstance(drafts, list) and drafts:
            # Prefer a likely main league draft
            preferred = next(
                (d for d in drafts if d.get("status") in {"complete", "drafting", "pre_draft"}),
                drafts[0],
            )
            draft_id = preferred.get("draft_id") or preferred.get("id")
    if not draft_id:
        raise ValueError(f"No draft_id found for previous league {prev_id}")

    # 3) Fetch picks
    picks = _get(f"{BASE_URL}/draft/{draft_id}/picks").json()
    if not isinstance(picks, list) or not picks:
        raise ValueError(f"No picks returned for draft {draft_id}")

    # 4) Resolve player name -> id (normalize to alphanumeric lowercase to ignore punctuation/hyphens)
    players = _get(f"{BASE_URL}/players/{sport}").json()

    def _norm(s: str | None) -> str:
        if not s:
            return ""
        s = s.strip().lower()
        return "".join(ch for ch in s if ch.isalnum())

    needle = _norm(player_name)
    target_id = None
    for pid, pdata in players.items():
        fn = pdata.get("first_name") or ""
        ln = pdata.get("last_name") or ""
        full = pdata.get("full_name") or (f"{fn} {ln}".strip())
        candidates = {full, f"{fn} {ln}".strip(), f"{fn}{ln}".strip()}
        if any(_norm(c) == needle for c in candidates):
            target_id = pid
            break
    if not target_id:
        raise ValueError(f"Could not find player_id for '{player_name}' in /players/{sport}")

    # 5) Find pick by player_id
    chosen = next((pk for pk in picks if str(pk.get("player_id")) == str(target_id)), None)
    if not chosen:
        # Some drafts store player_id under metadata
        chosen = next(
            (pk for pk in picks if str(pk.get("metadata", {}).get("player_id")) == str(target_id)),
            None,
        )
    if not chosen:
        raise ValueError(f"Player {player_name} ({target_id}) not found in draft {draft_id} picks")

    rnd = chosen.get("round")
    try:
        rnd_int = int(rnd)
    except Exception:
        rnd_int = rnd

    return {
        "previous_league_id": prev_id,
        "season": season,
        "draft_id": str(draft_id),
        "player_name": player_name,
        "player_id": str(target_id),
        "round": rnd_int,
    }


def answer_when_was_player_drafted_last_year(
    player_name: str = "Brock Bowers",
    league_id: str = LEAGUE_ID,
    sport: str = SPORT,
) -> dict:
    """Question: when was <player_name> drafted? (last year's league draft)
    Returns pick details for last season's league draft: { previous_league_id, season, draft_id, player_name, player_id, round, pick_no, draft_slot, timestamp }
    timestamp is best-effort (if present in pick data under common keys).
    """
    # reuse logic by calling the previous helper and then searching the pick
    prev_info = answer_what_round_was_player_drafted_last_year(
        player_name=player_name, league_id=league_id, sport=sport
    )
    draft_id = prev_info["draft_id"]
    player_id = prev_info["player_id"]
    picks = _get(f"{BASE_URL}/draft/{draft_id}/picks").json()
    chosen = next((pk for pk in picks if str(pk.get("player_id")) == str(player_id)), None)
    if not chosen:
        chosen = next(
            (pk for pk in picks if str(pk.get("metadata", {}).get("player_id")) == str(player_id)),
            None,
        )
    if not chosen:
        raise ValueError(f"Player {player_name} ({player_id}) not found in draft {draft_id} picks")

    # attempt to extract a timestamp if present
    timestamp = (
        chosen.get("picked_at")
        or chosen.get("created")
        or chosen.get("updated")
        or chosen.get("start_time")
        or chosen.get("metadata", {}).get("timestamp")
    )
    out = dict(prev_info)
    out.update(
        {
            "pick_no": chosen.get("pick_no"),
            "draft_slot": chosen.get("draft_slot"),
            "timestamp": timestamp,
        }
    )
    return out


# --- Weekly history reporting ---


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
    records: dict[int, dict] = {}
    for wk in range(start_week, max(start_week, end_week) + 1):
        week_rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{wk}").json()
        groups: dict[int, list[dict]] = {}
        for row in week_rows or []:
            mid = row.get("matchup_id")
            if mid is None:
                mid = -100000 - row.get("roster_id", 0)
            groups.setdefault(mid, []).append(row)

        for mid, entries in groups.items():
            if len(entries) == 2:
                a, b = entries[0], entries[1]
                for e in (a, b):
                    rid = e.get("roster_id")
                    rec = records.setdefault(
                        rid,
                        {
                            "roster_id": rid,
                            "wins": 0,
                            "losses": 0,
                            "ties": 0,
                            "points_for": 0.0,
                            "points_against": 0.0,
                        },
                    )
                    opp = b if e is a else a
                    rec["points_for"] += float(e.get("points", 0) or 0)
                    rec["points_against"] += float(opp.get("points", 0) or 0)
                ap = float(a.get("points", 0) or 0)
                bp = float(b.get("points", 0) or 0)
                if ap > bp:
                    records[a.get("roster_id")]["wins"] += 1
                    records[b.get("roster_id")]["losses"] += 1
                elif bp > ap:
                    records[b.get("roster_id")]["wins"] += 1
                    records[a.get("roster_id")]["losses"] += 1
                else:
                    records[a.get("roster_id")]["ties"] += 1
                    records[b.get("roster_id")]["ties"] += 1
            else:
                total_points = [float(e.get("points", 0) or 0) for e in entries]
                for i, e in enumerate(entries):
                    rid = e.get("roster_id")
                    rec = records.setdefault(
                        rid,
                        {
                            "roster_id": rid,
                            "wins": 0,
                            "losses": 0,
                            "ties": 0,
                            "points_for": 0.0,
                            "points_against": 0.0,
                        },
                    )
                    rec["points_for"] += total_points[i]
                    rec["points_against"] += sum(total_points) - total_points[i]

    table = []
    for rid, rec in records.items():
        g = rec["wins"] + rec["losses"] + rec["ties"]
        win_pct = (rec["wins"] + 0.5 * rec["ties"]) / g if g else 0.0
        table.append(
            {
                **rec,
                "games": g,
                "win_pct": round(win_pct, 4),
                "points_for": round(rec["points_for"], 2),
                "points_against": round(rec["points_against"], 2),
            }
        )
    table.sort(key=lambda r: (-r["win_pct"], -r["points_for"], r["roster_id"]))
    return table


def _head_to_head_week(league_id: str, week: int, roster_owner_name: dict[int, str]) -> list[dict]:
    rows = _get(f"{BASE_URL}/league/{league_id}/matchups/{week}").json()
    groups: dict[int, list[dict]] = {}
    for row in rows or []:
        mid = row.get("matchup_id")
        if mid is None:
            mid = -100000 - row.get("roster_id", 0)
        groups.setdefault(mid, []).append(row)

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


def answer_generate_weekly_history_report(
    league_id: str = LEAGUE_ID,
    season: str | int | None = None,
    report_week: int | None = None,
    sport: str = SPORT,
    out_dir: str = "reports/weekly",
) -> dict:
    league = _resolve_league_for_season(league_id, season)
    resolved_league_id = str(league.get("league_id"))
    resolved_season = str(league.get("season"))
    settings = league.get("settings", {}) or {}
    start_week = int(settings.get("start_week", 1) or 1)
    playoff_week_start = int(settings.get("playoff_week_start", 15) or 15)

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
    user_name, roster_owner_name = _build_name_maps(users, rosters)

    standings = _compute_standings(resolved_league_id, start_week, report_week)
    h2h = _head_to_head_week(resolved_league_id, report_week, roster_owner_name)
    next_week = report_week + 1
    preview = _preview_week(resolved_league_id, next_week if same_season else -1, roster_owner_name)

    now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    title = f"# Weekly Report — League {resolved_league_id} — Season {resolved_season} — Week {report_week}"

    sections = [
        (
            "metadata",
            {
                "generated_at": now_iso,
                "league_id": resolved_league_id,
                "league_name": league.get("name"),
                "season": resolved_season,
                "report_week": report_week,
                "start_week": start_week,
                "playoff_week_start": playoff_week_start,
                "state_season": state_season,
                "state_week": state_week,
                "same_season": same_season,
            },
        ),
        (f"standings_after_week_{report_week}", standings),
        (f"head_to_head_week_{report_week}", h2h),
        (f"upcoming_week_preview_week_{next_week}", preview),
    ]

    md_lines = [title, ""]
    for header, payload in sections:
        md_lines.append(f"## {header}")
        md_lines.append("```json")
        md_lines.append(_pretty(payload))
        md_lines.append("```")
        md_lines.append("")

    dest_dir = os.path.join(out_dir, resolved_season)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"week-{report_week:02d}.md")
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

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


# --- Minimal CLI to run answers quickly ---

AnswerFn = Callable[..., Any]
ANSWER_REGISTRY: dict[str, tuple[AnswerFn, str]] = {
    "get_league_information": (answer_get_league_information, "league_id:str"),
    "get_roster": (answer_get_roster, "league_id:str, roster_id:int?"),
    "get_my_roster_id": (answer_get_my_roster_id, "league_id:str, username:str"),
    "get_current_draft_id": (answer_get_current_draft_id, "league_id:str"),
    "what_round_was_player_drafted_last_year": (
        answer_what_round_was_player_drafted_last_year,
        "player_name:str, league_id:str, sport:str",
    ),
    "when_was_player_drafted_last_year": (
        answer_when_was_player_drafted_last_year,
        "player_name:str, league_id:str, sport:str",
    ),
    "generate_weekly_history_report": (
        answer_generate_weekly_history_report,
        "league_id:str, season:int?, report_week:int?, sport:str, out_dir:str",
    ),
}


def _parse_args(args: list[str]) -> tuple[str, dict[str, Any]]:
    if not args:
        raise SystemExit(
            "Usage: python api_answers.py <answer_name> [key=value ...]\n"
            f"Answers: {', '.join(ANSWER_REGISTRY.keys())}"
        )
    name = args[0]
    if name not in ANSWER_REGISTRY:
        raise SystemExit(f"Unknown answer: {name}\nAvailable: {', '.join(ANSWER_REGISTRY.keys())}")
    kv: dict[str, Any] = {}
    for token in args[1:]:
        if "=" in token:
            k, v = token.split("=", 1)
            kv[k.strip()] = v.strip()
        else:
            # allow positional roster_id as convenience for get_roster
            if name == "get_roster" and token.isdigit():
                kv["roster_id"] = int(token)
            else:
                # ignore unexpected non key=value tokens
                pass
    # Coerce known ints
    if name == "get_roster" and "roster_id" in kv:
        try:
            kv["roster_id"] = int(kv["roster_id"]) if kv["roster_id"] is not None else None
        except ValueError as exc:
            raise SystemExit("roster_id must be an integer") from exc
    return name, kv


def _main() -> int:
    name, kwargs = _parse_args(sys.argv[1:])
    fn, _ = ANSWER_REGISTRY[name]
    try:
        data = fn(**kwargs)
    except requests.HTTPError as e:
        print(f"HTTPError: {e}")
        if e.response is not None:
            try:
                print(_pretty(e.response.json()))
            except (ValueError, TypeError):
                print(e.response.text[:2000])
        return 1
    except (requests.RequestException, ValueError) as e:
        print(f"Error: {e}")
        return 1
    print(_pretty(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
