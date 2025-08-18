"""Output format helpers for weekly report contexts.

Design goals for JSON (no backward compat required):
 - Provide strongly typed shapes (objects with named fields instead of opaque row arrays)
 - Remove presentation artifacts (markdown line breaks, HTML <br>, semicolon joined key/value strings)
 - Coerce numeric-looking strings to numbers
 - Add structured variants while retaining (optionally) raw legacy sections for debugging
 - Avoid lossy transformations: every original datum either preserved or represented structurally

Normalization pipeline (applied when normalize=True):
 1. Copy base payload produced by WeeklyContext.to_json_payload
 2. Coerce metadata numeric strings (ints / floats) to numeric types
 3. Convert tabular list-of-lists sections into list-of-objects with explicit keys
 4. Expand "details" composite cell into structured fields (list + kv map)
 5. Restructure head_to_head_grid into matrix objects (one object per row with vs mapping)
 6. Restructure margin_summary *_game entries from text into objects when possible
 7. Emit a sections index describing optional section presence
"""

from __future__ import annotations
import json
from typing import Any, Iterable, Sequence
from .models import WeeklyContext


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    esc = lambda v: str(v).replace("|", "\\|")  # noqa: E731
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        out.append("| " + " | ".join(esc(c) for c in r) + " |")
    return out


def format_markdown(ctx: WeeklyContext) -> str:
    return "\n".join(ctx.markdown_lines) + "\n"


def _coerce_number(val: Any) -> Any:
    if not isinstance(val, str):
        return val
    s = val.strip()
    if s.isdigit():
        try:
            return int(s)
        except ValueError:
            return val
    try:
        # Accept float forms like 0.7143
        return float(s)
    except ValueError:
        return val


def _parse_details_cell(details: str) -> tuple[list[str], list[str], dict[str, str]]:
    if not details or details == "-":
        return [], [], {}
    normalized = details.replace("<br>", "; ")
    tokens = [p.strip() for p in normalized.split(";") if p.strip()]
    kv = {}
    ordered = []
    flat = []
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            k = k.strip()
            v = v.strip()
            kv[k] = v
            ordered.append(f"{k}={v}")
            flat.append(k)
        else:
            flat.append(t)
            ordered.append(t)
    return ordered, flat, kv


def _grid_to_matrix(grid: list[list[Any]]) -> list[dict[str, Any]]:
    if not grid:
        return []
    header = grid[0][1:]  # roster header labels with pattern id-owner
    # extract roster ids from header cells split by '-' first segment
    roster_ids: list[int] = []
    for cell in header:
        try:
            rid = int(str(cell).split('-', 1)[0])
        except ValueError:
            rid = -1
        roster_ids.append(rid)
    out: list[dict[str, Any]] = []
    for row in grid[1:]:
        if not row:
            continue
        left = row[0]
        try:
            row_rid = int(str(left).split('-', 1)[0])
        except ValueError:
            row_rid = -1
        vs_map: dict[str, Any] = {}
        for idx, cell in enumerate(row[1:]):
            opp = roster_ids[idx]
            if isinstance(cell, str) and cell == '-':
                continue
            vs_map[str(opp)] = cell
        out.append({"roster_id": row_rid, "vs": vs_map})
    return out


def _parse_margin_game(text: str) -> dict[str, Any] | None:
    # Expected format: "OwnerA over OwnerB 123.45-120.11 (wk7, m3)" OR tied
    if not text or not isinstance(text, str):
        return None
    try:
        core, tail = text.rsplit("(", 1)
        tail = tail.rstrip(")")
        week_part, match_part = tail.split(",")
        wk = int(week_part.strip().lstrip("wk"))
        mid = int(match_part.strip().lstrip("m"))
        if " tied " in core:
            lhs, rest = core.split(" tied ", 1)
            score_part = rest.strip().split()[-1]
            owners_part = lhs + " & " + rest[: -(len(score_part) + 1)]
            # fallback simple parse
        if " over " in core:
            a_part, b_rest = core.split(" over ", 1)
            score_segment = b_rest.strip().split()[-1]
            scores = score_segment.split("-")
            a_score = float(scores[0])
            b_score = float(scores[1])
            # Everything before score in b_rest except last token is loser owner
            loser_owner = " ".join(b_rest.split()[:-1])
            return {
                "week": wk,
                "matchup_id": mid,
                "winner_owner": a_part.strip(),
                "loser_owner": loser_owner.strip(),
                "winner_points": a_score,
                "loser_points": b_score,
                "margin": round(abs(a_score - b_score), 2),
            }
    except Exception:
        return None
    return None


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.copy()
    meta = data.get("metadata") or {}
    if isinstance(meta, dict):
        for k, v in list(meta.items()):
            meta[k] = _coerce_number(v)
    # Weekly results enriched rows -> objects
    raw_rows = data.pop("weekly_results_enriched_rows", None)
    if raw_rows:
        header = [
            "matchup_id","roster_a","points_a","roster_b","points_b","winner_roster_id","winner_owner","loser_owner","tie","details"
        ]
        normalized_rows: list[dict[str, Any]] = []
        for r in raw_rows:
            obj = {header[i]: r[i] for i in range(min(len(header), len(r)))}
            details_ordered, details_flags, details_kv = _parse_details_cell(obj.get("details", ""))
            obj["details_ordered"] = details_ordered
            obj["details_flags"] = details_flags
            obj["details_kv"] = details_kv
            # numeric coercion
            for fld in ("matchup_id","points_a","points_b"):
                obj[fld] = _coerce_number(obj.get(fld))
            if isinstance(obj.get("winner_roster_id"), str) and obj["winner_roster_id"].isdigit():
                obj["winner_roster_id"] = int(obj["winner_roster_id"])
            obj["tie"] = (str(obj.get("tie")) == "yes") or (obj.get("tie") is True)
            normalized_rows.append(obj)
        data["weekly_results_enriched"] = normalized_rows
    # Streaks table -> objects
    streak_rows = data.pop("streaks_table", None)
    if streak_rows:
        header = [
            "roster_id","owner","current_streak","current_start_week","current_end_week","longest_win_len","longest_win_span","longest_loss_len","longest_loss_span"
        ]
        streak_objs = []
        for r in streak_rows:
            obj = {header[i]: r[i] for i in range(min(len(header), len(r)))}
            for fld in ("roster_id","current_start_week","current_end_week","longest_win_len","longest_loss_len"):
                try:
                    obj[fld] = int(obj[fld]) if obj[fld] not in {"-", None} else None
                except Exception:
                    pass
            streak_objs.append(obj)
        data["streaks"] = streak_objs
    # h2h grid restructure
    if isinstance(data.get("head_to_head_grid"), list):
        data["head_to_head_matrix"] = _grid_to_matrix(data["head_to_head_grid"])
    # Margin summary game fields -> structured objects
    ms = data.get("margin_summary")
    if isinstance(ms, dict):
        for key in list(ms.keys()):
            if key.endswith("_game") or key.endswith("_game_through"):
                parsed = _parse_margin_game(ms[key])
                if parsed:
                    ms[key + "_obj"] = parsed
    # Sections index
    optional_keys = [
        "weekly_results_enriched","streaks","head_to_head_matrix","all_play_records","median_records","margin_summary","division_power_week","division_power_season","playoff_standings","division_standings","roster_directory"
    ]
    data["sections"] = [k for k in optional_keys if k in data and data[k]]
    return data


def format_json(
    ctx: WeeklyContext,
    schema_version: str,
    *,
    pretty: bool = False,
    normalize: bool = True,
) -> str:
    """Render context to JSON.

    Args:
        schema_version: Requested schema version (still passed into model payload creator).
        pretty: Indent output.
        normalize: If True, apply structural normalization (recommended for site generation).
    """
    payload = ctx.to_json_payload(schema_version) or {}
    if normalize:
        payload = _normalize_payload(payload)
    if pretty:
        return json.dumps(payload, indent=2)
    return json.dumps(payload, separators=(",", ":"))
