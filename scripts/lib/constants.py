# constants.py
# Centralized constants used by the weekly report. Do not change values without bumping schema_version.

SCHEMA_VERSION = "1.8.0"

# Enrichment thresholds (keep values identical to legacy implementation)
BLOWOUT_MARGIN = 50.0
NAIL_BITER_MARGIN = 5.0
SHOOTOUT_COMBINED = 340.0
SLUGFEST_COMBINED = 260.0
CLOSE_GAME_MARGIN = 20.0  # for bad_beat/got_away flavor

# Formatting
WIN_PCT_PLACES = 4
POINTS_PLACES = 2

# Throttling defaults
DEFAULT_MIN_INTERVAL_SEC = 0.10  # ~600 rpm
