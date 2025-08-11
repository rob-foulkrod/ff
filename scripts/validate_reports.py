import argparse
import os
import re


SECTION_RE = re.compile(r"^## (?P<title>.+)$")
SUBSECTION_RE = re.compile(r"^### (?P<title>.+)$")
WEEK_NUM_RE = re.compile(r"Week\s+(?P<wk>\d+)")
THROUGH_WEEK_NUM_RE = re.compile(r"Through\s+Week\s+(?P<wk>\d+)")


def parse_sections(text: str) -> dict:
    lines = text.splitlines()
    sections = {}
    current = None
    buf: list[str] = []
    for line in lines:
        m = SECTION_RE.match(line.strip())
        if m:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = m.group("title")
            buf = []
        else:
            if current is not None:
                buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def parse_table(block: str) -> tuple[list[str], list[list[str]]]:
    # Expect a markdown table: header, separator, rows...
    rows = [line.strip() for line in block.splitlines() if line.strip()]
    # find first line that starts with '|'
    table_lines = [line for line in rows if line.startswith("|")]
    if len(table_lines) < 2:
        return [], []
    header = [c.strip() for c in table_lines[0].strip().strip("|").split("|")]
    data_lines = table_lines[2:]  # skip header + separator
    data: list[list[str]] = []
    for data_line in data_lines:
        cells = [c.strip() for c in data_line.strip().strip("|").split("|")]
        data.append(cells)
    return header, data


def parse_subsection_tables(block: str) -> list[tuple[str, list[str], list[list[str]]]]:
    """Parse level-3 subsections (### Title) each followed by a markdown table.
    Returns list of tuples: (subsection_title, header, rows).
    """
    lines = block.splitlines()
    # Find indices of subsection headers
    idxs: list[int] = []
    titles: list[str] = []
    for i, ln in enumerate(lines):
        m = SUBSECTION_RE.match(ln.strip())
        if m:
            idxs.append(i)
            titles.append(m.group("title"))
    results: list[tuple[str, list[str], list[list[str]]]] = []
    for si, start_idx in enumerate(idxs):
        end_idx = idxs[si + 1] if si + 1 < len(idxs) else len(lines)
        sub_lines = lines[start_idx:end_idx]
        # Find first table start
        tbl_start = None
        for j, ln in enumerate(sub_lines):
            if ln.strip().startswith("|"):
                tbl_start = j
                break
        if tbl_start is None:
            results.append((titles[si], [], []))
            continue
    # Collect table lines until blank line or next subsection (shouldn't appear here)
        tbl_lines: list[str] = []
        for ln in sub_lines[tbl_start:]:
            if ln.strip() == "":
                break
            tbl_lines.append(ln)
        header, rows = parse_table("\n".join(tbl_lines))
        results.append((titles[si], header, rows))
    return results


def validate_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    errs: list[str] = []
    sections = parse_sections(txt)

    # Metadata
    if "Metadata" not in sections:
        errs.append("Missing section: Metadata")
        return errs
    meta_header, meta_rows = parse_table(sections["Metadata"])
    if meta_header != ["key", "value"]:
        errs.append("Metadata header mismatch")
    meta = {}
    for row in meta_rows:
        if len(row) >= 2:
            meta[row[0]] = row[1]
    required_keys = [
        "schema_version",
        "generated_at",
        "league_id",
        "league_name",
        "season",
        "report_week",
        "standings_through_week",
        "head_to_head_week",
        "preview_week",
        "start_week",
        "playoff_week_start",
        "state_season",
        "state_week",
        "same_season",
        "season_phase",
        "num_teams",
        "standings_rows",
        "h2h_rows",
        "preview_rows",
        # New required keys
        "weekly_results_rows",
        "playoff_rows",
        "streaks_rows",
        "details_format",
        "week_points_avg",
        "week_points_median",
        "week_high",
        "week_low",
        "season_high_through_week",
        "season_low_through_week",
        "division_count_configured",
        "division_count_active",
    ]
    for rk in required_keys:
        if rk not in meta:
            errs.append(f"Metadata missing key: {rk}")

    # Validate division names if division_count_active > 0
    try:
        div_active = int(meta.get("division_count_active", "0"))
    except Exception:
        div_active = 0
    if div_active > 0:
        missing_div_names = []
        for i in range(1, div_active + 1):
            k = f"division_{i}_name"
            if k not in meta:
                missing_div_names.append(k)
        if missing_div_names:
            errs.append(f"Metadata missing division name keys: {', '.join(missing_div_names)}")

    # Roster Directory
    if "Roster Directory" not in sections:
        errs.append("Missing section: Roster Directory")
    else:
        rd_header, rd_rows = parse_table(sections["Roster Directory"])
        if rd_header != ["roster_id", "owner"]:
            errs.append("Roster Directory header mismatch")
        try:
            num_teams = int(meta.get("num_teams", "0"))
            if len(rd_rows) != num_teams:
                errs.append(f"Roster Directory row count {len(rd_rows)} != num_teams {num_teams}")
        except Exception:
            pass

    # Standings
    sw_key = next((k for k in sections.keys() if k.startswith("Standings Through Week ")), None)
    if not sw_key:
        errs.append("Missing section: Standings Through Week N")
    else:
        st_header, st_rows = parse_table(sections[sw_key])
        expected = [
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
        ]
        if st_header != expected:
            errs.append("Standings header mismatch")
        try:
            expected_rows = int(meta.get("standings_rows", "0"))
            if len(st_rows) != expected_rows:
                errs.append(f"Standings row count {len(st_rows)} != metadata {expected_rows}")
        except Exception:
            pass
        # Coherence: standings week number matches metadata
        m = THROUGH_WEEK_NUM_RE.search(sw_key)
        if m:
            if meta.get("standings_through_week") != m.group("wk"):
                errs.append(
                    f"Standings week mismatch: section {m.group('wk')} vs metadata {meta.get('standings_through_week')}"
                )

    # Head-to-Head
    hh_key = next((k for k in sections.keys() if k.startswith("Head-to-Head Results Week ")), None)
    if not hh_key:
        errs.append("Missing section: Head-to-Head Results Week N")
    else:
        hh_header, hh_rows = parse_table(sections[hh_key])
        expected = [
            "matchup_id",
            "roster_a",
            "points_a",
            "roster_b",
            "points_b",
            "winner_roster_id",
            "tie",
            "details",
        ]
        if hh_header != expected:
            errs.append("Head-to-Head header mismatch")
        try:
            expected_rows = int(meta.get("h2h_rows", "0"))
            if len(hh_rows) != expected_rows:
                errs.append(f"H2H row count {len(hh_rows)} != metadata {expected_rows}")
        except Exception:
            pass
        m = WEEK_NUM_RE.search(hh_key)
        if m:
            if meta.get("head_to_head_week") != m.group("wk"):
                errs.append(
                    f"Head-to-Head week mismatch: section {m.group('wk')} vs metadata {meta.get('head_to_head_week')}"
                )

    # Preview
    pv_key = next((k for k in sections.keys() if k.startswith("Upcoming Week Preview ")), None)
    if not pv_key:
        errs.append("Missing section: Upcoming Week Preview")
    else:
        pv_header, pv_rows = parse_table(sections[pv_key])
        expected = ["matchup_id", "roster_a", "roster_b", "details"]
        if pv_header != expected:
            errs.append("Preview header mismatch")
        # preview_rows should count only non-sentinel rows
        non_sentinel = [r for r in pv_rows if len(r) >= 1 and r[0] != "-"]
        try:
            expected_rows = int(meta.get("preview_rows", "0"))
            if len(non_sentinel) != expected_rows:
                errs.append(
                    f"Preview non-sentinel row count {len(non_sentinel)} != metadata {expected_rows}"
                )
        except Exception:
            pass

        # If preview_week is '-', we expect a single sentinel row
        if meta.get("preview_week", "") == "-":
            if not (len(pv_rows) == 1 and all(c.strip() == "-" for c in pv_rows[0])):
                errs.append("Preview sentinel row expected when preview_week is -")
        else:
            m = WEEK_NUM_RE.search(pv_key)
            if m:
                if meta.get("preview_week") != m.group("wk"):
                    errs.append(
                        f"Preview week mismatch: section {m.group('wk')} vs metadata {meta.get('preview_week')}"
                    )

    # Weekly Results
    wr_key = next((k for k in sections.keys() if k.startswith("Weekly Results Week ")), None)
    if not wr_key:
        errs.append("Missing section: Weekly Results Week N")
    else:
        wr_header, wr_rows = parse_table(sections[wr_key])
        expected = [
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
        ]
        if wr_header != expected:
            errs.append("Weekly Results header mismatch")
        try:
            expected_rows = int(meta.get("weekly_results_rows", "0"))
            if len(wr_rows) != expected_rows:
                errs.append(f"Weekly Results row count {len(wr_rows)} != metadata {expected_rows}")
        except Exception:
            pass
        m = WEEK_NUM_RE.search(wr_key)
        if m:
            if meta.get("head_to_head_week") != m.group("wk"):
                errs.append(
                    f"Weekly Results week mismatch: section {m.group('wk')} vs metadata {meta.get('head_to_head_week')}"
                )

    # Division Standings
    ds_key = next(
        (k for k in sections.keys() if k.startswith("Division Standings Through Week ")), None
    )
    if not ds_key:
        errs.append("Missing section: Division Standings Through Week N")
    else:
        # Parse all subsections (each division)
        sub_tables = parse_subsection_tables(sections[ds_key])
        if not sub_tables:
            errs.append("Division Standings missing division subsections")
        else:
            # Validate header shape for each division
            expected = [
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
            ]
            for title, header, rows in sub_tables:
                if header != expected:
                    errs.append(f"Division Standings header mismatch for '{title}'")
            # Count divisions vs metadata
            try:
                div_active = int(meta.get("division_count_active", "0"))
                if len(sub_tables) != div_active:
                    errs.append(
                        f"Division subsections {len(sub_tables)} != division_count_active {div_active}"
                    )
            except Exception:
                pass
            # Optional coherence: total teams across divisions equals standings_rows
            try:
                total_rows = sum(len(rows) for _, _, rows in sub_tables)
                expected_total = int(meta.get("standings_rows", "0"))
                if total_rows != expected_total:
                    errs.append(
                        f"Division Standings total rows {total_rows} != standings_rows {expected_total}"
                    )
            except Exception:
                pass
            m = THROUGH_WEEK_NUM_RE.search(ds_key)
            if m:
                if meta.get("standings_through_week") != m.group("wk"):
                    errs.append(
                        f"Division Standings week mismatch: section {m.group('wk')} vs metadata {meta.get('standings_through_week')}"
                    )

    # Playoff Standings
    ps_key = next(
        (k for k in sections.keys() if k.startswith("Playoff Standings Through Week ")), None
    )
    if not ps_key:
        errs.append("Missing section: Playoff Standings Through Week N")
    else:
        ps_header, ps_rows = parse_table(sections[ps_key])
        expected = [
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
        ]
        if ps_header != expected:
            errs.append("Playoff Standings header mismatch")
        try:
            expected_rows = int(meta.get("playoff_rows", "0"))
            if len(ps_rows) != expected_rows:
                errs.append(
                    f"Playoff Standings row count {len(ps_rows)} != metadata {expected_rows}"
                )
        except Exception:
            pass
        m = THROUGH_WEEK_NUM_RE.search(ps_key)
        if m:
            if meta.get("standings_through_week") != m.group("wk"):
                errs.append(
                    f"Playoff Standings week mismatch: section {m.group('wk')} vs metadata {meta.get('standings_through_week')}"
                )

    # Head-to-Head Grid
    hg_key = next(
        (k for k in sections.keys() if k.startswith("Head-to-Head Grid Through Week ")), None
    )
    if not hg_key:
        errs.append("Missing section: Head-to-Head Grid Through Week N")
    else:
        header, rows = parse_table(sections[hg_key])
        # Expect first header cell empty label, followed by N column labels
        if not header or header[0] != "":
            errs.append("H2H Grid header first cell must be empty label")
        # Row count should equal number of column labels (excluding first label col)
        try:
            n = len(header) - 1
            if n <= 0:
                errs.append("H2H Grid has no team columns")
            else:
                if len(rows) != n:
                    errs.append(f"H2H Grid rows {len(rows)} != columns {n}")
                # Validate each row has exactly 1 + n cells
                for i, r in enumerate(rows):
                    if len(r) != (1 + n):
                        errs.append(f"H2H Grid row {i} has {len(r)} cells != {1+n}")
                    # Diagonal must be '-'
                    if i < len(r) and r[i + 1] != "-":
                        errs.append(f"H2H Grid diagonal mismatch at row {i}, expected -")
                    # Non-diagonal cells must be -- or W-L or W-L-T
                    for j in range(1, len(r)):
                        if j == i + 1:
                            continue
                        cell = r[j].strip()
                        if cell == "--":
                            continue
                        if not re.match(r"^\d+-\d+(-\d+)?$", cell):
                            errs.append(f"H2H Grid bad cell '{cell}' at row {i}, col {j}")
        except Exception:
            pass
        m = THROUGH_WEEK_NUM_RE.search(hg_key)
        if m:
            if meta.get("standings_through_week") != m.group("wk"):
                errs.append(
                    f"H2H Grid week mismatch: section {m.group('wk')} vs metadata {meta.get('standings_through_week')}"
                )

    # Streaks
    sk_key = next((k for k in sections.keys() if k.startswith("Streaks Through Week ")), None)
    if not sk_key:
        errs.append("Missing section: Streaks Through Week N")
    else:
        sk_header, sk_rows = parse_table(sections[sk_key])
        expected = [
            "roster_id",
            "owner",
            "current_streak",
            "current_start_week",
            "current_end_week",
            "longest_win_len",
            "longest_win_span",
            "longest_loss_len",
            "longest_loss_span",
        ]
        if sk_header != expected:
            errs.append("Streaks header mismatch")
        try:
            expected_rows = int(meta.get("streaks_rows", "0"))
            if len(sk_rows) != expected_rows:
                errs.append(f"Streaks row count {len(sk_rows)} != metadata {expected_rows}")
        except Exception:
            pass
        m = THROUGH_WEEK_NUM_RE.search(sk_key)
        if m:
            if meta.get("standings_through_week") != m.group("wk"):
                errs.append(
                    f"Streaks week mismatch: section {m.group('wk')} vs metadata {meta.get('standings_through_week')}"
                )

    return errs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate generated weekly reports for structure and coherence"
    )
    parser.add_argument("--out-dir", default="reports/weekly", help="Reports base directory")
    parser.add_argument("--season", required=True, help="Season folder to validate (e.g., 2024)")
    parser.add_argument("--from-week", type=int, default=1)
    parser.add_argument("--to-week", type=int, default=99)
    args = parser.parse_args(argv)

    season_dir = os.path.join(args.out_dir, args.season)
    if not os.path.isdir(season_dir):
        print(f"No such directory: {season_dir}")
        return 1

    failures = 0
    for wk in range(args.from_week, args.to_week + 1):
        path = os.path.join(season_dir, f"week-{wk:02d}.md")
        if not os.path.exists(path):
            continue
        errs = validate_file(path)
        if errs:
            failures += 1
            print(f"FAIL week {wk:02d}: {path}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"OK   week {wk:02d}: {path}")

    if failures:
        print(f"Validation completed with {failures} failing file(s).")
        return 2
    print("Validation completed successfully (all files OK).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
