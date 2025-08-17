"""Output formatters for modular weekly report contexts (new package)."""
from __future__ import annotations
import json
from typing import Any, Iterable, Sequence

from .models import WeeklyContext


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:  # noqa: D401
    esc = lambda v: str(v).replace("|", "\\|")  # noqa: E731
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for r in rows:
        out.append("| " + " | ".join(esc(c) for c in r) + " |")
    return out


def format_markdown(ctx: WeeklyContext) -> str:
    return "\n".join(ctx.markdown_lines) + "\n"


def format_json(ctx: WeeklyContext, schema_version: str, *, pretty: bool = False) -> str:
    """
    Produce an enriched, analysis-friendly JSON document with a normalized structure.
    Original payload retained under 'legacy'.
    """
    legacy = ctx.to_json_payload(schema_version) or {}
    meta = legacy.get("metadata") or {}

    def _lm(key: str, default=None):
        return meta.get(key, default)

    report_week = _lm("report_week")
    through_week = _lm("standings_through_week") or report_week
    league_id = _lm("league_id")
    league_name = _lm("league_name")
    season = _lm("season")

    # Divisions
    divisions: list[dict] = []
    for k, v in meta.items():
        if k.startswith("division_") and k.endswith("_name"):
            parts = k.split("_")
            if len(parts) == 3 and parts[1].isdigit():
                divisions.append({"division_id": int(parts[1]), "name": v})
    div_id_by_name = {d["name"]: d["division_id"] for d in divisions}

    roster_dir = legacy.get("roster_directory") or []
    if not isinstance(roster_dir, list):
        roster_dir = []

    # Prepare playoff & division data early (needed to infer division_ids)
    raw_divs = legacy.get("division_standings") or []
    if not isinstance(raw_divs, list):
        raw_divs = []

    # Build roster_id -> division_id map from division standings
    roster_div_map: dict[int, int] = {}
    for d in raw_divs:
        if not isinstance(d, dict):
            continue
        div_name = d.get("division_name")
        did = div_id_by_name.get(div_name)
        for r in d.get("rows", []) or []:
            if isinstance(r, dict) and isinstance(r.get("roster_id"), (int, str)):
                try:
                    rid = int(r["roster_id"])
                    if did:
                        roster_div_map[rid] = did
                except ValueError:
                    pass

    # Legacy overall standings (may have points_for / points_against)
    overall_rows = legacy.get("standings") or []
    if not isinstance(overall_rows, list):
        overall_rows = []

    # Owner lookup map (owner -> roster_id) for missing roster_directory roster_id
    owner_to_roster: dict[str, int] = {}
    for row in overall_rows:
        if isinstance(row, dict):
            rid = row.get("roster_id")
            owner = row.get("owner")
            if isinstance(rid, int) and isinstance(owner, str):
                owner_to_roster.setdefault(owner, rid)

    def _norm_pf(row: dict):
        return row.get("PF") if row.get("PF") is not None else row.get("points_for")

    def _norm_pa(row: dict):
        return row.get("PA") if row.get("PA") is not None else row.get("points_against")

    def _norm_games(row: dict):
        return row.get("games")

    overall = []
    for row in overall_rows:
        if not isinstance(row, dict):
            continue
        rid = row.get("roster_id")
        pf = _norm_pf(row)
        pa = _norm_pa(row)
        games = _norm_games(row)
        pf_pg = pa_pg = None
        if isinstance(games, (int, float)) and games:
            try:
                pf_pg = round(pf / games, 2) if isinstance(pf, (int, float)) else None
                pa_pg = round(pa / games, 2) if isinstance(pa, (int, float)) else None
            except ZeroDivisionError:
                pass
        overall.append({
            "rank": row.get("rank"),  # may be None in legacy list
            "roster_id": rid,
            "owner": row.get("owner"),
            "wins": row.get("wins") if row.get("wins") is not None else row.get("W"),
            "losses": row.get("losses") if row.get("losses") is not None else row.get("L"),
            "ties": row.get("ties") if row.get("ties") is not None else row.get("T"),
            "win_pct": row.get("win_pct"),
            "pf": pf,
            "pa": pa,
            "pf_pg": pf_pg,
            "pa_pg": pa_pg,
            "diff": (pf - pa) if isinstance(pf, (int, float)) and isinstance(pa, (int, float)) else None,
            "streak": row.get("streak"),
            "rank_change": row.get("rank_change"),
        })

    # Division standings normalized
    division_standings = []
    for d in raw_divs:
        if not isinstance(d, dict):
            continue
        div_name = d.get("division_name")
        did = div_id_by_name.get(div_name)
        norm_rows = []
        for r in d.get("rows", []) or []:
            if not isinstance(r, dict):
                continue
            rid = r.get("roster_id")
            pf = _norm_pf(r)
            pa = _norm_pa(r)
            games = _norm_games(r)
            pf_pg = pa_pg = None
            if isinstance(games, (int, float)) and games:
                try:
                    pf_pg = round(pf / games, 2) if isinstance(pf, (int, float)) else None
                    pa_pg = round(pa / games, 2) if isinstance(pa, (int, float)) else None
                except ZeroDivisionError:
                    pass
            norm_rows.append({
                "rank": r.get("rank"),
                "roster_id": rid,
                "owner": r.get("owner"),
                "wins": r.get("wins") if r.get("wins") is not None else r.get("W"),
                "losses": r.get("losses") if r.get("losses") is not None else r.get("L"),
                "ties": r.get("ties") if r.get("ties") is not None else r.get("T"),
                "win_pct": r.get("win_pct"),
                "pf": pf,
                "pa": pa,
                "pf_pg": pf_pg,
                "pa_pg": pa_pg,
                "games": games,
                "current_streak": r.get("current_streak"),
            })
        division_standings.append({
            "division_name": div_name,
            "division_id": did,
            "rows": norm_rows
        })

    # Playoff standings
    playoff_rows = legacy.get("playoff_standings") or []
    if not isinstance(playoff_rows, list):
        playoff_rows = []
    playoff_seeds = [r for r in playoff_rows if isinstance(r, dict) and r.get("seed") not in (None, "-", "")]
    in_the_hunt = [r for r in playoff_rows if isinstance(r, dict) and r.get("type") == "In the Hunt"]

    # Weekly results (unchanged parsing for now)
    weekly_results_src = legacy.get("weekly_results") or []
    weekly_results = []
    for m in weekly_results_src:
        if not isinstance(m, dict):
            continue
        details_raw = m.get("details", "")
        details_obj: dict = {}
        if isinstance(details_raw, str):
            for part in filter(None, (p.strip() for p in details_raw.split(";"))):
                if "=" in part:
                    k, v = part.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    low = v.lower()
                    if low in ("yes", "true"):
                        val = True
                    elif low in ("no", "false"):
                        val = False
                    else:
                        try:
                            val = float(v) if "." in v else int(v)
                        except ValueError:
                            val = v
                    details_obj[k] = val
                else:
                    details_obj[part] = True
        elif isinstance(details_raw, dict):
            details_obj = details_raw
        ra_label = m.get("roster_a") or ""
        rb_label = m.get("roster_b") or ""
        def _extract_roster_id(label: str):
            if " - " in label:
                head = label.split(" - ", 1)[0].strip()
            else:
                head = label.split()[0] if label else ""
            try:
                return int(head)
            except (ValueError, TypeError):
                return head or None
        ra_id = m.get("roster_a_roster_id") or _extract_roster_id(ra_label)
        rb_id = m.get("roster_b_roster_id") or _extract_roster_id(rb_label)
        weekly_results.append({
            "week": report_week,
            "matchup_id": m.get("matchup_id"),
            "winner_roster_id": m.get("winner_roster_id"),
            "tie": str(m.get("tie")).lower() in ("yes", "true"),
            "teams": [
                {
                    "slot": "a",
                    "roster_id": ra_id,
                    "label": ra_label,
                    "points": m.get("points_a"),
                    "owner": m.get("winner_owner") if m.get("winner_roster_id") == ra_id else m.get("loser_owner"),
                },
                {
                    "slot": "b",
                    "roster_id": rb_id,
                    "label": rb_label,
                    "points": m.get("points_b"),
                    "owner": m.get("winner_owner") if m.get("winner_roster_id") == rb_id else m.get("loser_owner"),
                },
            ],
            "details": details_obj
        })

    # Head-to-head grid
    h2h_raw = legacy.get("head_to_head_grid") or {}
    if not isinstance(h2h_raw, dict):
        h2h_raw = {}
    h2h_order = h2h_raw.get("index_order") or h2h_raw.get("order") or []
    matrix_src = h2h_raw.get("matrix") or h2h_raw.get("rows") or []
    matrix = []
    records = []
    if isinstance(matrix_src, list):
        for r_idx, row in enumerate(matrix_src):
            if not isinstance(row, list):
                continue
            norm_row = []
            for c_idx, cell in enumerate(row):
                if r_idx == c_idx:
                    norm_row.append(None)
                    continue
                cell_obj = None
                if isinstance(cell, str) and "-" in cell:
                    parts = cell.split("-", 1)
                    try:
                        w_val = int(parts[0]); l_val = int(parts[1])
                    except ValueError:
                        w_val = l_val = None
                    cell_obj = {"w": w_val, "l": l_val}
                elif isinstance(cell, dict):
                    cell_obj = {"w": cell.get("w"), "l": cell.get("l")}
                norm_row.append(cell_obj)
                if cell_obj:
                    records.append({
                        "home": h2h_order[r_idx] if r_idx < len(h2h_order) else None,
                        "away": h2h_order[c_idx] if c_idx < len(h2h_order) else None,
                        **cell_obj
                    })
            matrix.append(norm_row)

    # Streaks
    streaks_norm = []
    for s in legacy.get("streaks") or []:
        if not isinstance(s, dict):
            continue
        streaks_norm.append({
            "roster_id": s.get("roster_id"),
            "owner": s.get("owner"),
            "current": {
                "label": s.get("current_streak"),
                "start_week": s.get("current_start_week"),
                "end_week": s.get("current_end_week"),
            },
            "longest_win": {
                "length": s.get("longest_win_len"),
                "span": s.get("longest_win_span"),
            },
            "longest_loss": {
                "length": s.get("longest_loss_len"),
                "span": s.get("longest_loss_span"),
            },
        })

    summary = {
        "teams": len(roster_dir),
        "through_week": through_week,
        "week_points": {
            "avg": _lm("week_points_avg"),
            "median": _lm("week_points_median"),
            "high": _lm("week_high"),
            "low": _lm("week_low"),
            "season_high_to_date": _lm("season_high_through_week"),
            "season_low_to_date": _lm("season_low_through_week"),
        },
        "row_counts": {
            "standings": _lm("standings_rows"),
            "weekly_results": _lm("weekly_results_rows"),
            "preview": _lm("preview_rows"),
            "playoff": _lm("playoff_rows"),
            "streaks": _lm("streaks_rows"),
        }
    }

    # Build teams with inferred roster_id & division_id
    teams_out = []
    for t in roster_dir:
        if not isinstance(t, dict):
            continue
        rid = t.get("roster_id")
        owner = t.get("owner")
        if rid is None and isinstance(owner, str):
            rid = owner_to_roster.get(owner)
        did = roster_div_map.get(rid)
        teams_out.append({
            "roster_id": rid,
            "owner": owner,
            "division_id": did
        })

    enhanced = {
        "schema_version": "2.0.0",
        "generated_at": _lm("generated_at"),
        "league": {
            "league_id": league_id,
            "name": league_name,
            "season": season,
            "phase": _lm("season_phase"),
            "playoff_week_start": _lm("playoff_week_start"),
            "start_week": _lm("start_week"),
        },
        "through_week": through_week,
        "report_week": report_week,
        "divisions": divisions,
        "teams": teams_out,
        "standings": {
            "overall": overall,
            "divisions": division_standings,
            "playoff_seeds": playoff_seeds,
            "in_the_hunt": in_the_hunt,
        },
        "weekly": {
            "week": report_week,
            "matchups": weekly_results
        },
        "head_to_head": {
            "through_week": through_week,
            "index_order": h2h_order,
            "matrix": matrix,
            "records": records
        },
        "streaks": streaks_norm,
        "summary": summary,
        "legacy": legacy,
    }

    if pretty:
        return json.dumps(enhanced, indent=2)
    return json.dumps(enhanced, separators=(",", ":"))
