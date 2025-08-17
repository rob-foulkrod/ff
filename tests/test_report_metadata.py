import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'python')))
from ff.report.collect import build_weekly_context  # type: ignore

LEAGUE_ID = '1180276953741729792'
SEASON = '2024'
SPORT = 'nfl'
REPORT_WEEK = 8

EXPECTED_META_KEYS = {
    'schema_version', 'generated_at', 'league_id', 'season', 'report_week', 'start_week',
    'playoff_week_start', 'playoff_teams', 'state_season', 'state_week', 'same_season',
    'league_name', 'standings_through_week', 'head_to_head_week', 'preview_week', 'num_teams',
    'standings_rows', 'h2h_rows', 'weekly_results_rows', 'preview_rows', 'playoff_rows',
    'streaks_rows', 'division_count_configured', 'division_count_active', 'season_phase',
    'details_format'
}

EXPECTED_WEEKLY_RESULTS_COLUMNS = [
    'matchup_id','roster_a','points_a','roster_b','points_b','winner_roster_id','winner_owner','loser_owner','tie','details'
]

def test_metadata_keys_present():
    ctx = build_weekly_context(league_id=LEAGUE_ID, season=SEASON, report_week=REPORT_WEEK, sport=SPORT)
    meta = {k for k, _ in ctx.meta_rows}
    missing = EXPECTED_META_KEYS - meta
    assert not missing, f"Missing metadata keys: {missing}"


def test_weekly_results_columns_and_flag_order():
    ctx = build_weekly_context(league_id=LEAGUE_ID, season=SEASON, report_week=REPORT_WEEK, sport=SPORT)
    # Find weekly results header line in markdown
    lines = ctx.markdown_lines
    try:
        idx = lines.index(f"## Weekly Results Week {REPORT_WEEK}")
    except ValueError as exc:
        raise AssertionError("Weekly Results section header missing") from exc
    header_line = lines[idx+1]
    # Extract columns from markdown table header
    cols = [c.strip() for c in header_line.strip('| ').split('|')]
    assert cols == EXPECTED_WEEKLY_RESULTS_COLUMNS, f"Unexpected columns: {cols}"
    # Check ordering of details flags alphabetical segments
    data_line_candidates = [l for l in lines[idx+3:] if l.startswith('| 1 ') or l.startswith('| 2 ') or l.startswith('| 3 ') or l.startswith(f'| {REPORT_WEEK}')]
    assert data_line_candidates, 'No data lines found in weekly results'
    # Parse details cell of first data row
    parts = data_line_candidates[0].split('|')
    details = parts[-2].strip()  # last meaningful before trailing pipe
    if details != '-' and '<br>' in details:
        details_flat = details.replace('<br>', '; ')
    else:
        details_flat = details
    tokens = [p.strip() for p in details_flat.split(';') if p.strip()]
    # all tokens should be key=value sorted
    kv_pairs = []
    for t in tokens:
        assert '=' in t, f"Flag not key=value: {t}"
        k,v = t.split('=',1)
        kv_pairs.append((k,v))
    assert kv_pairs == sorted(kv_pairs, key=lambda kv: (kv[0], kv[1])), 'Flags not sorted'
