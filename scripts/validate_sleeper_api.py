import os
import sys
import json
import time
from typing import Any

import requests

BASE_URL = os.environ.get("SLEEPER_BASE_URL", "https://api.sleeper.com/v1")
LEAGUE_ID = os.environ.get("SLEEPER_LEAGUE_ID", "1180276953741729792")
SPORT = os.environ.get("SLEEPER_SPORT", "nfl")
SEASON = os.environ.get("SLEEPER_SEASON", "2025")
ROSTER_ID_ENV = os.environ.get("SLEEPER_ROSTER_ID")


def get(url: str) -> requests.Response:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r


def pretty(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def main() -> int:
    print(f"Base: {BASE_URL}")
    print(f"League: {LEAGUE_ID}")
    # Optional roster_id from env or CLI
    roster_id: int | None = None
    if ROSTER_ID_ENV and ROSTER_ID_ENV.strip():
        try:
            roster_id = int(ROSTER_ID_ENV)
        except ValueError:
            print(f"Warning: SLEEPER_ROSTER_ID '{ROSTER_ID_ENV}' is not an int; ignoring.")
    if roster_id is None and len(sys.argv) > 1:
        try:
            roster_id = int(sys.argv[1])
        except ValueError:
            print(f"Warning: CLI roster_id '{sys.argv[1]}' is not an int; ignoring.")

    # 1) League info
    league_url = f"{BASE_URL}/league/{LEAGUE_ID}"
    print(f"GET {league_url}")
    league = get(league_url).json()
    print("League info sample:")
    print(pretty({k: league.get(k) for k in list(league.keys())[:12]}))

    # 2) League rosters
    rosters_url = f"{BASE_URL}/league/{LEAGUE_ID}/rosters"
    print(f"\nGET {rosters_url}")
    rosters = get(rosters_url).json()
    print(f"Rosters count: {len(rosters)}")
    target = None
    if roster_id is not None:
        for r in rosters:
            if r.get("roster_id") == roster_id:
                target = r
                break
        if target is None:
            print(f"Roster with roster_id={roster_id} not found; showing first instead.")
    if not target and rosters:
        target = rosters[0]
    if target:
        print("Roster keys:")
        print(sorted(list(target.keys())))
        sample = {
            k: target.get(k)
            for k in [
                "roster_id",
                "owner_id",
                "co_owners",
                "players",
                "starters",
                "reserve",
                "taxi",
                "metadata",
            ]
            if k in target
        }
        print(pretty(sample))

    # Optional: small pacing to be polite
    time.sleep(0.25)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as e:
        print(f"HTTPError: {e}", file=sys.stderr)
        if e.response is not None:
            print(e.response.text[:2000], file=sys.stderr)
        raise
