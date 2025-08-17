## Sleeper Weekly Reports

Deterministic, machine-readable weekly Markdown reports for a Sleeper fantasy football league. Includes standings, division standings, playoff picture, head-to-head grid/results, upcoming preview, streaks, and enriched weekly results. Designed to be stable for downstream parsing and safe to regenerate for entire seasons.

## Quick start

1) Prerequisites
- Python 3.11+
- A Sleeper league ID (default wired for this repo: 1180276953741729792)

2) Create a virtual environment and install deps (PowerShell/pwsh on Windows):

```powershell
# From repo root
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3) Generate a weekly report

```powershell
# Single week for a season
python scripts/weekly_report.py --season 2024 --report-week 11

# The file will be written to: reports/weekly/2024/week-11.md
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
- Throttling and retries are built-in. The client uses a requests.Session with backoff for transient errors (429/5xx) and a simple min-interval rate limiter.
- Writes are atomic: the report file is written to a temp file and then replaced.

## CLI usage

Weekly report generator

```powershell
python scripts/weekly_report.py `
  --league-id 1180276953741729792 `
  --season 2024 `
  --report-week 11 `
  --out-dir reports/weekly `
  --verbose
```

Range/all generation

```powershell
# All regular-season weeks for a season (based on league settings.playoff_week_start)
python scripts/weekly_report.py --season 2024 --all

# Custom range
python scripts/weekly_report.py --season 2024 --from-week 3 --to-week 8
```

Dry run

```powershell
# Build but do not write files
python scripts/weekly_report.py --season 2024 --report-week 11 --dry-run --verbose
```

## What’s in the report

Sections (in order):
- Metadata: key/value block including schema_version, weeks, counts, and scoring context
- Roster Directory
- Weekly Results Week N (with enriched details)
- Standings Through Week N (includes current_streak and rank_change)
- Division Standings Through Week N
- Playoff Standings Through Week N
  - Two division winners + two best wildcards regardless of division
  - “In the Hunt”: any non-seeded teams tied in W-L-T with a seeded team
- Head-to-Head Grid Through Week N (NxN matrix by overall standings)
- Head-to-Head Results Week N
- Upcoming Week Preview Week N+1 (sentinel row when out of range)
- Streaks Through Week N (current + longest win/loss)

Output is deterministic and pipes are escaped for parsing. Schema version is centralized in `scripts/lib/constants.py`.

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

2) Install runtime dependencies (already used by the scripts and tests)

```powershell
pip install -r requirements.txt
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
python scripts/weekly_report.py --season 2024 --report-week 11

# Generate the full regular season for 2024
python scripts/weekly_report.py --season 2024 --all

# Validate all generated files for 2024
python scripts/validate_reports.py --season 2024
```

## Troubleshooting

- 429 Too Many Requests: lower SLEEPER_RPM_LIMIT or raise SLEEPER_MIN_INTERVAL_MS
- Transient 5xx: the client retries with backoff; try again later if persistent
- Empty previews on historical seasons: expected; a sentinel row is emitted
- Missing division names: ensure league metadata has division name keys (e.g., division_1_name)

## Notes

- Playoff logic is: two division winners plus the two best remaining teams irrespective of division. Tied non-seeded teams are appended as “In the Hunt”.
- Head-to-Head Grid shows W-L or W-L-T; diagonal is “-”, and “--” means not played.

## License

MIT License. See LICENSE for details.
