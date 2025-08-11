from scripts.lib.compute import (
    group_rows,
    compute_standings_with_groups,
    compute_weekly_results,
    current_streak,
    longest_streaks,
)


def test_group_rows_with_missing_matchup_id():
    rows = [
        {"roster_id": 1, "points": 100},
        {"roster_id": 2, "points": 90},
    ]
    groups = group_rows(rows)
    # With no matchup_id, implementation creates a synthetic id per roster
    assert len(groups) == 2
    for _, entries in groups.items():
        assert len(entries) == 1


def test_compute_standings_basic_two_team():
    # Week 1: 1 beats 2; Week 2: tie
    weekly_groups = {
        1: {1: [{"roster_id": 1, "points": 110}, {"roster_id": 2, "points": 100}]},
        2: {1: [{"roster_id": 1, "points": 100}, {"roster_id": 2, "points": 100}]},
    }
    table = compute_standings_with_groups(weekly_groups, 1, 2)
    assert len(table) == 2
    t1 = next(r for r in table if r["roster_id"] == 1)
    assert t1["wins"] == 1 and t1["ties"] == 1 and t1["losses"] == 0
    assert abs(t1["points_for"] - 210.0) < 1e-6


ess = [
    (1, "W"),
    (2, "W"),
    (3, "L"),
    (4, "W"),
    (5, "T"),
    (6, "W"),
]


def test_current_streak_break_on_tie():
    typ, ln, _st, en = current_streak(ess, 6)
    # Tie breaks the streak, so last segment is W from 6 only
    assert typ == "W" and ln == 1 and en == 6


def test_longest_streaks_simple():
    win_best, loss_best = longest_streaks(ess, 6)
    assert win_best[0] >= 2 and isinstance(loss_best, tuple)


def test_weekly_results_outcomes():
    weekly_groups = {
        1: {10: [{"roster_id": 1, "points": 120}, {"roster_id": 2, "points": 100}]},
        2: {20: [{"roster_id": 1, "points": 90}, {"roster_id": 2, "points": 100}]},
    }
    results = compute_weekly_results(weekly_groups, 1, 2)
    assert results[1] == [(1, "W"), (2, "L")]
    assert results[2] == [(1, "L"), (2, "W")]
