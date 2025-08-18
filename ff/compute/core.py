from __future__ import annotations


def _coerce_int(value: object, default: int = 0) -> int:
    """Best‑effort int conversion (supports int, float, str of digits)."""
    if value is None:
        return default
    if isinstance(value, bool):  # bool is subclass of int; handle explicitly if undesired
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def group_rows(rows: list[dict]) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = {}
    for row in rows or []:
        mid_raw = row.get("matchup_id")
        if mid_raw is None:
            # Create deterministic synthetic id using roster_id when missing
            rid_int = _coerce_int(row.get("roster_id"), 0)
            mid = -100000 - rid_int
        else:
            mid = _coerce_int(mid_raw, -1)
        groups.setdefault(mid, []).append(row)
    return groups


def compute_standings_with_groups(
    weekly_groups: dict[int, dict[int, list[dict]]], start_week: int, end_week: int
) -> list[dict]:
    records: dict[int, dict] = {}
    for wk in range(start_week, max(start_week, end_week) + 1):
        groups = weekly_groups.get(wk, {})
        for _, entries in (groups or {}).items():
            if len(entries) == 2:
                a, b = entries[0], entries[1]
                for e in (a, b):
                    rid_raw = e.get("roster_id")
                    if rid_raw is None:
                        # Skip malformed entry without roster id
                        continue
                    rid = _coerce_int(rid_raw, -1)
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
                a_rid_raw = a.get("roster_id")
                b_rid_raw = b.get("roster_id")
                if a_rid_raw is None or b_rid_raw is None:
                    # Cannot assign win/loss without both roster ids
                    continue
                a_rid = _coerce_int(a_rid_raw, -1)
                b_rid = _coerce_int(b_rid_raw, -1)
                if ap > bp:
                    records[a_rid]["wins"] += 1
                    records[b_rid]["losses"] += 1
                elif bp > ap:
                    records[b_rid]["wins"] += 1
                    records[a_rid]["losses"] += 1
                else:
                    records[a_rid]["ties"] += 1
                    records[b_rid]["ties"] += 1
            else:
                total_points = [float(e.get("points", 0) or 0) for e in entries]
                for i, e in enumerate(entries):
                    rid_raw = e.get("roster_id")
                    if rid_raw is None:
                        continue
                    rid = _coerce_int(rid_raw, -1)
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


def compute_weekly_results(
    weekly_groups: dict[int, dict[int, list[dict]]], start_week: int, end_week: int
) -> dict[int, list[tuple[int, str]]]:
    results: dict[int, list[tuple[int, str]]] = {}
    for wk in range(start_week, max(start_week, end_week) + 1):
        groups = weekly_groups.get(wk, {})
        for _, entries in (groups or {}).items():
            if len(entries) != 2:
                continue
            a, b = entries
            ap = float(a.get("points", 0) or 0)
            bp = float(b.get("points", 0) or 0)
            a_rid_raw = a.get("roster_id")
            b_rid_raw = b.get("roster_id")
            if a_rid_raw is None or b_rid_raw is None:
                continue
            a_rid = _coerce_int(a_rid_raw, -1)
            b_rid = _coerce_int(b_rid_raw, -1)
            if ap > bp:
                results.setdefault(a_rid, []).append((wk, "W"))
                results.setdefault(b_rid, []).append((wk, "L"))
            elif bp > ap:
                results.setdefault(b_rid, []).append((wk, "W"))
                results.setdefault(a_rid, []).append((wk, "L"))
            else:
                results.setdefault(a_rid, []).append((wk, "T"))
                results.setdefault(b_rid, []).append((wk, "T"))
    return results


def current_streak(res_list: list[tuple[int, str]], through_week: int) -> tuple[str, int, int, int]:
    filtered = [t for t in res_list if t[0] <= through_week]
    if not filtered:
        return ("none", 0, 0, through_week)
    streak_type: str = "none"
    length = 0
    start_wk = through_week
    for week, res in reversed(filtered):
        if res == "T":
            break
        if streak_type == "none":
            streak_type = res
            length = 1
            start_wk = week
        elif res == streak_type:
            length += 1
            start_wk = week
        else:
            break
    if streak_type == "none":
        return ("none", 0, 0, through_week)
    return (streak_type, length, start_wk, through_week)


def longest_streaks(
    res_list: list[tuple[int, str]], through_week: int
) -> tuple[tuple[int, str], tuple[int, str]]:
    filtered = [t for t in res_list if t[0] <= through_week]
    best_win = (0, "-")
    best_loss = (0, "-")
    cur_type = None
    cur_len = 0
    cur_start = None
    for week, res in filtered:
        if res == "T":
            if cur_type == "W" and cur_len > best_win[0]:
                best_win = (cur_len, f"w{cur_start}-w{week}")
            if cur_type == "L" and cur_len > best_loss[0]:
                best_loss = (cur_len, f"w{cur_start}-w{week}")
            cur_type, cur_len, cur_start = None, 0, None
            continue
        if res == cur_type:
            cur_len += 1
        else:
            if cur_type == "W" and cur_len > best_win[0]:
                best_win = (cur_len, f"w{cur_start}-w{week}")
            if cur_type == "L" and cur_len > best_loss[0]:
                best_loss = (cur_len, f"w{cur_start}-w{week}")
            cur_type = res
            cur_len = 1
            cur_start = week
    if cur_type == "W" and cur_len > best_win[0]:
        best_win = (cur_len, f"w{cur_start}-w{through_week}")
    if cur_type == "L" and cur_len > best_loss[0]:
        best_loss = (cur_len, f"w{cur_start}-w{through_week}")
    return best_win, best_loss
