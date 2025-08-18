## Sleeper Weekly Reports

Generate deterministic, machine‑readable weekly reports (Markdown and/or JSON) for a Sleeper fantasy football league. The current modular implementation focuses on core season tracking: metadata, standings, week head‑to‑head results, a lightweight weekly results table (with margin), an optional upcoming week preview, and streaks. Output is stable and safe to regenerate for any range of regular‑season weeks.

## Quick start

1) Prerequisites
- Python 3.11+
- A Sleeper league ID (default wired for this repo: 1180276953741729792)

2) Create a virtual environment and install deps (PowerShell/pwsh on Windows):

```powershell
# From repo root
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# Editable install (package) + dev tools & test deps via extras
pip install -e .[dev]

# (Legacy alternative removed) Previously used requirements.txt; now use extras only.
```

3) Generate a weekly report (Markdown default)

```powershell
# Single week for a season (installed console script)
weekly-report --season 2024 --report-week 11

# Or via Python module (development / editable install)
python -m ff.cli.weekly_report --season 2024 --report-week 11

# The file will be written to: reports/weekly/2024/week-11.md

# Include JSON alongside Markdown (pretty JSON is the default)
weekly-report --season 2024 --report-week 11 --formats markdown,json

# Generate compact JSON instead of pretty
weekly-report --season 2024 --report-week 11 --formats json --json-compact

# (Automation) Generate a range or list using the helper script
python scripts/generate_reports.py --season 2024 --range 1-4 --formats markdown,json
python scripts/generate_reports.py --season 2024 --weeks 1,3,7 --formats json

# Specify a different league id (e.g., new 2025 league) explicitly
weekly-report --league-id 123456789012345678 --season 2025 --report-week 1

# Or set env var (persists for the session)
$Env:SLEEPER_LEAGUE_ID="123456789012345678"
weekly-report --season 2025 --all --formats markdown,json
```

4) Validate reports

```powershell
# Validate one or more weeks
python scripts/validate_reports.py --season 2024 --from-week 11 --to-week 11
```

## Configuration

Environment variables (all optional):
- SLEEPER_BASE_URL: API base (default https://api.sleeper.com/v1)
- SLEEPER_LEAGUE_ID: League to use by default (default 1180276953741729792)
- SLEEPER_SPORT: Sport key (default nfl)
- SLEEPER_RPM_LIMIT: Calls per minute, to throttle requests
- SLEEPER_MIN_INTERVAL_MS: Minimum milliseconds between requests

You can place these in a local .env file for convenience. See .env.example for defaults.

Notes
- Requests are throttled using an interval (env configurable) with retry/backoff for 429/5xx via the shared client.
- JSON output schema version is `schema_version` in the payload (also in Metadata table for Markdown).

## CLI usage

Weekly report generator

```powershell
weekly-report \
  --league-id 1180276953741729792 \
  --season 2024 \
  --report-week 11 \
  --out-dir reports/weekly \
  --formats markdown,json \
  --verbose
```

Range/all generation

```powershell
# All regular-season weeks for a season (based on league settings.playoff_week_start)
weekly-report --season 2024 --all

# Custom range
weekly-report --season 2024 --from-week 3 --to-week 8
```

Dry run

```powershell
# Build but do not write files
weekly-report --season 2024 --report-week 11 --dry-run --verbose
```

## Report contents (current modular version)

Markdown sections (order):
1. Title
2. Metadata (schema_version, generation timestamp, league + season, report_week, start/playoff settings, state_week, same_season flag)
3. Standings Through Week N (rank, roster_id, W/L/T, win_pct, PF, PA)
4. (If present) Weekly Results Week N (includes owners, scores, margin, ordered/enriched flags)
5. (If present) Upcoming Week Preview Week N+1 (only during regular season; omitted/hollow when out of range)
6. Streaks Through Week N (current streak plus longest win/loss spans)

JSON representation contains:
- schema_version
- metadata (flattened key/value list from Metadata section)
- standings (list of team records through the report week)
- head_to_head_week (list of matchups for the report week, with points and winner_roster_id/tie)
- weekly_results_enriched_rows (enriched weekly results: matchup_id, winner/loser roster & owner, points, margin, and a deterministic, alphabetically ordered flags/details string; very long flag lists are wrapped with `<br>` for readability)
- preview (upcoming week matchup roster IDs & owners, when available)
- streaks_table (current and historical streak information)
- playoff_rows (placeholder = 0 for now; reserved for future expansion)

Notes:
- Division standings, playoff seeding rows, and head‑to‑head matrix have been reintroduced in enriched form (including rank change, streaks, playoff hunt indicators, and head‑to‑head preview data when applicable).
- Weekly results now carry multiple contextual flags (e.g., blowout, nail_biter, upset, division_game, shootout, highest_loser_score_week, lowest_winner_score_week, etc.). The set is normalized and sorted for deterministic output.
- Very long flag detail strings are wrapped at a configurable width (currently 100 chars) using `<br>` to keep Markdown tables readable.
- All numeric points and percentages are formatted consistently (see constants for precision).

### JSON output formatting

Pretty (indented) JSON is the default when `json` is included in `--formats`.

Flags:
- `--json-pretty` (default / idempotent) – keep pretty formatting.
- `--json-compact` – emit compact JSON (no extra whitespace) for minimal file size or downstream tooling.

## Other utilities

- API sanity checks: `scripts/validate_sleeper_api.py`
- Report validator: `scripts/validate_reports.py`
- Q&A helpers: `api_answers.py` (common lookups, throttled requests)
- OpenAPI spec & smoke tests:
  - `openapi/sleeper.yaml`
  - `sleeper_tests.py`

## Testing

```powershell
python -m pytest -q
```

Unit tests cover core compute helpers and smoke-check the OpenAPI spec. Reports are validated by `scripts/validate_reports.py` to ensure structure and coherence.

## Development setup

If you plan to make changes, these dev tools and hooks will help keep everything consistent.

1) Create and activate a virtual environment (from repo root)

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

2) Install runtime + dev dependencies

```powershell
pip install -e .[dev]
```

3) Install dev tools (formatter, linter, type checker, and commit hooks)

```powershell
pip install black ruff mypy pre-commit
pre-commit install
# Optional: run once across the repo to normalize formatting
pre-commit run -a
```

4) Configure environment variables (optional)

```powershell
# Copy defaults and edit as needed
Copy-Item .env.example .env
```

## Quality checks

Run these locally before opening a PR. With the venv activated, the commands are available on PATH.

```powershell
# Lint (static checks)
ruff check .

# Format check (Black)
black --check .

# Type check
mypy

# Unit tests
python -m pytest -q
```

Tips:
- Use `black .` to auto-format files.
- `ruff check --fix .` can auto-fix many issues.
- Some long lines and modernization hints are enforced gradually. CI is configured to be helpful without blocking on large refactors.

## Continuous Integration (CI)

GitHub Actions workflow at `.github/workflows/ci.yml` runs on push and pull requests:
- Set up Python (3.11/3.12) on Windows and Linux
- Lint: Ruff
- Format check: Black
- Type check: Mypy
- Tests: Pytest

If CI fails, open the logs for the failing job and apply the suggestions (run the same commands locally to reproduce).

## Recommended editor setup

- VS Code extensions: Python, Ruff
- Line endings/formatting are normalized via `.editorconfig`

## Frontend dev (Astro site)

To avoid starting the dev server from the wrong directory, there's a small helper and recommended tasks.

1) Start the dev server (PowerShell helper)

```powershell
# From repo root (or anywhere)
powershell -ExecutionPolicy Bypass -File "site\dev.ps1"
```

2) VS Code task example (add to `.vscode/tasks.json`)

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Site: Start dev server",
      "type": "shell",
      "command": "powershell -ExecutionPolicy Bypass -File \"site\\dev.ps1\"",
      "group": "build",
      "presentation": { "reveal": "always" }
    }
  ]
}
```

This ensures the server always starts from `site/` and uses the local `package.json` scripts.

## Examples (using this league)

```powershell
# Generate a single week for 2024
weekly-report --season 2024 --report-week 11

# Generate the full regular season for 2024 (Markdown + pretty JSON)
weekly-report --season 2024 --all --formats markdown,json

# Generate full season with compact JSON only
weekly-report --season 2024 --all --formats json --json-compact

# Validate all generated files for 2024 (still legacy script path for now)
python scripts/validate_reports.py --season 2024
```

## Troubleshooting

- 429 Too Many Requests: lower SLEEPER_RPM_LIMIT or raise SLEEPER_MIN_INTERVAL_MS
- Transient 5xx: the client retries with backoff; try again later if persistent
- Empty previews on historical seasons: expected; a sentinel row is emitted
- Missing division names: ensure league metadata has division name keys (e.g., division_1_name)

## Notes

- Historical weeks: preview section is usually empty (or omitted in JSON) because future matchup data is not yet published.
- Regular season bounds are derived from league settings (playoff_week_start minus 1).

## License

MIT License. See LICENSE for details.
