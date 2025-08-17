"""High-level Q&A style helper functions for Sleeper API (migrated)."""
from __future__ import annotations

import os
import json
import datetime
import time
from typing import Any, Callable
import requests

BASE_URL = os.environ.get("SLEEPER_BASE_URL", "https://api.sleeper.com/v1")
LEAGUE_ID = os.environ.get("SLEEPER_LEAGUE_ID", "1180276953741729792")
SPORT = os.environ.get("SLEEPER_SPORT", "nfl")
SEASON = os.environ.get("SLEEPER_SEASON", "2025")
USER_ID = os.environ.get("SLEEPER_USER_ID", "robfoulk")

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
    _MIN_INTERVAL_SEC = 0.10
_last_call_ts = 0.0

def _throttle() -> None:
    global _last_call_ts
    now = time.monotonic()
    elapsed = now - _last_call_ts if _last_call_ts else None
    if elapsed is not None and elapsed < _MIN_INTERVAL_SEC:
        time.sleep(_MIN_INTERVAL_SEC - elapsed)
    _last_call_ts = time.monotonic()

def _get(url: str) -> requests.Response:
    _throttle()
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r

def _pretty(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)

# --- Answer helpers ---

def answer_get_league_information(league_id: str = LEAGUE_ID) -> dict:
    return _get(f"{BASE_URL}/league/{league_id}").json()

def answer_get_roster(league_id: str = LEAGUE_ID, roster_id: int | None = None) -> Any:
    rosters = _get(f"{BASE_URL}/league/{league_id}/rosters").json()
    if roster_id is None:
        return rosters
    for r in rosters:
        if r.get("roster_id") == roster_id:
            return r
    raise ValueError(f"Roster with roster_id={roster_id} not found in league {league_id}")

def answer_get_my_roster_id(league_id: str = LEAGUE_ID, username: str = USER_ID) -> dict:
    user = _get(f"{BASE_URL}/user/{username}").json()
    uid = user.get("user_id") or user.get("userID") or user.get("uid")
    if not uid:
        raise ValueError(f"Could not resolve user_id for username '{username}'")
    rosters = _get(f"{BASE_URL}/league/{league_id}/rosters").json()
    for r in rosters:
        if r.get("owner_id") == uid:
            return {"league_id": league_id, "username": username, "user_id": uid, "roster_id": r.get("roster_id"), "role": "owner"}
        co = r.get("co_owners")
        if isinstance(co, list) and uid in co:
            return {"league_id": league_id, "username": username, "user_id": uid, "roster_id": r.get("roster_id"), "role": "co_owner"}
    raise ValueError(f"User '{username}' (id {uid}) does not own a roster in league {league_id}")

def answer_get_current_draft_id(league_id: str = LEAGUE_ID) -> dict:
    league = _get(f"{BASE_URL}/league/{league_id}").json()
    draft_id = league.get("draft_id")
    if not draft_id:
        drafts = _get(f"{BASE_URL}/league/{league_id}/drafts").json()
        if isinstance(drafts, list) and drafts:
            candidate = next((d for d in drafts if d.get("status") in {"pre_draft", "drafting"}), drafts[0])
            draft_id = candidate.get("draft_id") or candidate.get("id")
    if not draft_id:
        raise ValueError(f"No draft_id found for league {league_id}")
    return {"league_id": league_id, "draft_id": str(draft_id)}

def answer_what_round_was_player_drafted_last_year(player_name: str = "Justin Jefferson", league_id: str = LEAGUE_ID, sport: str = SPORT) -> dict:
    current = _get(f"{BASE_URL}/league/{league_id}").json()
    prev_id = current.get("previous_league_id")
    if not prev_id:
        raise ValueError(f"League {league_id} has no previous_league_id")
    prev = _get(f"{BASE_URL}/league/{prev_id}").json()
    season = prev.get("season")
    draft_id = prev.get("draft_id")
    if not draft_id:
        drafts = _get(f"{BASE_URL}/league/{prev_id}/drafts").json()
        if isinstance(drafts, list) and drafts:
            preferred = next((d for d in drafts if d.get("status") in {"complete", "drafting", "pre_draft"}), drafts[0])
            draft_id = preferred.get("draft_id") or preferred.get("id")
    if not draft_id:
        raise ValueError(f"No draft_id found for previous league {prev_id}")
    picks = _get(f"{BASE_URL}/draft/{draft_id}/picks").json()
    players = _get(f"{BASE_URL}/players/{sport}").json()
    def _norm(s: str | None) -> str:
        if not s: return ""
        s = s.strip().lower(); return "".join(ch for ch in s if ch.isalnum())
    needle = _norm(player_name)
    target_id = None
    for pid, pdata in players.items():
        fn = pdata.get("first_name") or ""; ln = pdata.get("last_name") or ""; full = pdata.get("full_name") or (f"{fn} {ln}".strip())
        if any(_norm(c) == needle for c in {full, f"{fn} {ln}".strip(), f"{fn}{ln}".strip()}):
            target_id = pid; break
    if not target_id:
        raise ValueError(f"Could not find player_id for '{player_name}'")
    chosen = next((pk for pk in picks if str(pk.get("player_id")) == str(target_id)), None)
    if not chosen:
        chosen = next((pk for pk in picks if str(pk.get("metadata", {}).get("player_id")) == str(target_id)), None)
    if not chosen:
        raise ValueError(f"Player {player_name} ({target_id}) not found in draft {draft_id} picks")
    rnd = chosen.get("round")
    try: rnd_int = int(rnd)
    except Exception: rnd_int = rnd
    return {"previous_league_id": prev_id, "season": season, "draft_id": str(draft_id), "player_name": player_name, "player_id": str(target_id), "round": rnd_int}

def answer_when_was_player_drafted_last_year(player_name: str = "Brock Bowers", league_id: str = LEAGUE_ID, sport: str = SPORT) -> dict:
    prev_info = answer_what_round_was_player_drafted_last_year(player_name=player_name, league_id=league_id, sport=sport)
    draft_id = prev_info["draft_id"]; player_id = prev_info["player_id"]
    picks = _get(f"{BASE_URL}/draft/{draft_id}/picks").json()
    chosen = next((pk for pk in picks if str(pk.get("player_id")) == str(player_id)), None)
    if not chosen:
        chosen = next((pk for pk in picks if str(pk.get("metadata", {}).get("player_id")) == str(player_id)), None)
    if not chosen:
        raise ValueError(f"Player {player_name} ({player_id}) not found in draft {draft_id} picks")
    timestamp = (chosen.get("picked_at") or chosen.get("created") or chosen.get("updated") or chosen.get("start_time") or chosen.get("metadata", {}).get("timestamp"))
    out = dict(prev_info); out.update({"pick_no": chosen.get("pick_no"), "draft_slot": chosen.get("draft_slot"), "timestamp": timestamp}); return out

# Weekly report (simpler legacy style) kept for parity with original Q&A file

def _resolve_league_for_season(base_league_id: str, season: str | int | None) -> dict:
    league = _get(f"{BASE_URL}/league/{base_league_id}").json()
    if season is None: return league
    target = str(season); guard = 0
    while guard < 12 and league and str(league.get("season")) != target:
        prev_id = league.get("previous_league_id")
        if not prev_id: break
        league = _get(f"{BASE_URL}/league/{prev_id}").json(); guard += 1
    if str(league.get("season")) != target:
        raise ValueError(f"Could not resolve league for season={season} starting from {base_league_id}")
    return league

def answer_generate_weekly_history_report(league_id: str = LEAGUE_ID, season: str | int | None = None, report_week: int | None = None, sport: str = SPORT, out_dir: str = "reports/weekly") -> dict:
    # Minimal legacy style; prefer ff.report.collect for richer output
    league = _resolve_league_for_season(league_id, season)
    resolved_league_id = str(league.get("league_id")); resolved_season = str(league.get("season"))
    settings = league.get("settings", {}) or {}
    start_week = int(settings.get("start_week", 1) or 1); playoff_week_start = int(settings.get("playoff_week_start", 15) or 15)
    state = _get(f"{BASE_URL}/state/{sport}").json(); state_season = str(state.get("season") or ""); state_week = int(state.get("week") or 0)
    same_season = state_season == resolved_season
    if report_week is None:
        report_week = min(state_week - 1, playoff_week_start - 1) if same_season and state_week > start_week else playoff_week_start - 1
    report_week = max(start_week, int(report_week))
    title = f"# Weekly Report — League {resolved_league_id} — Season {resolved_season} — Week {report_week}"; now_iso = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    dest_dir = os.path.join(out_dir, resolved_season); os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"week-{report_week:02d}.md")
    with open(dest_path, "w", encoding="utf-8") as f: f.write(title + "\nGenerated: " + now_iso + "\n")
    return {"written": True, "path": dest_path, "league_id": resolved_league_id, "season": resolved_season, "report_week": report_week}

AnswerFn = Callable[..., Any]
ANSWER_REGISTRY: dict[str, tuple[AnswerFn, str]] = {
    "get_league_information": (answer_get_league_information, "league_id:str"),
    "get_roster": (answer_get_roster, "league_id:str, roster_id:int?"),
    "get_my_roster_id": (answer_get_my_roster_id, "league_id:str, username:str"),
    "get_current_draft_id": (answer_get_current_draft_id, "league_id:str"),
    "what_round_was_player_drafted_last_year": (answer_what_round_was_player_drafted_last_year, "player_name:str, league_id:str, sport:str"),
    "when_was_player_drafted_last_year": (answer_when_was_player_drafted_last_year, "player_name:str, league_id:str, sport:str"),
    "generate_weekly_history_report": (answer_generate_weekly_history_report, "league_id:str, season:int?, report_week:int?, sport:str, out_dir:str"),
}

def _parse_args(args: list[str]) -> tuple[str, dict[str, Any]]:
    if not args:
        raise SystemExit("Usage: python -m ff.api.answers <answer_name> [key=value ...]\n" f"Answers: {', '.join(ANSWER_REGISTRY.keys())}")
    name = args[0]
    if name not in ANSWER_REGISTRY:
        raise SystemExit(f"Unknown answer: {name}\nAvailable: {', '.join(ANSWER_REGISTRY.keys())}")
    kv: dict[str, Any] = {}
    for token in args[1:]:
        if "=" in token:
            k, v = token.split("=", 1); kv[k.strip()] = v.strip()
        elif name == "get_roster" and token.isdigit():
            kv["roster_id"] = int(token)
    if name == "get_roster" and "roster_id" in kv:
        try: kv["roster_id"] = int(kv["roster_id"]) if kv["roster_id"] is not None else None
        except ValueError as exc: raise SystemExit("roster_id must be an integer") from exc
    return name, kv

def main(argv: list[str] | None = None) -> int:
    import sys
    name, kwargs = _parse_args(sys.argv[1:] if argv is None else argv)
    fn, _ = ANSWER_REGISTRY[name]
    try:
        data = fn(**kwargs)
    except requests.HTTPError as e:
        print(f"HTTPError: {e}")
        if e.response is not None:
            try: print(_pretty(e.response.json()))
            except (ValueError, TypeError): print(e.response.text[:2000])
        return 1
    except (requests.RequestException, ValueError) as e:
        print(f"Error: {e}"); return 1
    print(_pretty(data)); return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
