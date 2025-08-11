# Ideas backlog

This document collects ideas and proposals to improve the project. Keep entries small, scoped, and actionable. New ideas should use the template below so it’s easy to compare, prioritize, and track them.

## How to add a new idea
- Copy the template section below and fill in each field.
- Keep titles short and specific.
- Use “Status” to reflect lifecycle: proposed, planned, in-progress, done, or dropped.
- Prefer concrete acceptance criteria and a quick verification step.

### Idea template
- Title: <short, action-oriented>
- Category: <DX | Packaging | CI/CD | Reliability | Features | Docs | Testing | Performance | Tooling>
- Problem: <what pain or limitation does this solve?>
- Proposal: <what we’ll do>
- Benefits: <bullets of value/impact>
- Scope/Impact: <tiny | small | medium | large>
- Risks/Trade-offs: <notable risks or costs>
- Implementation outline:
  1. <step>
  2. <step>
- Effort: <S | M | L>
- Status: <proposed | planned | in-progress | done | dropped>
- Owner: <who>
- Acceptance criteria: <how we know it’s done>
- Validation: <quick test or command to verify>

---

## Backlog

### Package-style CLI entrypoint (console_script)
- Category: Packaging, DX
- Problem: Running the tool requires a script path and can hit import-path quirks. We want a simple command after venv activation, like `weekly-report`, without worrying about `sys.path`.
- Proposal: Publish a console_script entry point that calls `scripts.weekly_report:main`. When installed (editable or normal), this exposes a `weekly-report` command on PATH.
- Benefits:
  - One-line invocation: `weekly-report --season 2024 --all`
  - No manual `sys.path` tweaks or script path reliance
  - Works cross-platform (Windows/Linux/macOS)
  - Cleaner DX for CI and teammates; easier docs
- Scope/Impact: small
- Risks/Trade-offs:
  - Requires a minimal packaging file (`pyproject.toml` or `setup.cfg`)
  - Slight maintenance overhead for packaging metadata
- Implementation outline:
  1. Add `pyproject.toml` with project metadata and entry point mapping:  
     `[project.scripts]` → `weekly-report = "scripts.weekly_report:main"`
  2. Optionally add project name and version; keep dependencies minimal (none if not required)  
  3. Install in editable mode: `pip install -e .` (inside the venv)
  4. Run: `weekly-report --season 2024 --all`
  5. Update README with a “CLI” section
- Effort: S
- Status: proposed
- Owner: <assign>
- Acceptance criteria:
  - After `pip install -e .`, typing `weekly-report --help` works
  - Generating a week via `weekly-report --season 2024 --report-week 11` writes output and passes validator
- Validation:
  - `weekly-report --season 2024 --report-week 11 --verbose`
  - `python scripts/validate_reports.py --season 2024`

### (example) Fast local smoke task
- Category: Tooling, DX
- Problem: Repeating long commands for a quick smoke is error-prone.
- Proposal: Add a VS Code task or Makefile target that runs a single-week generation + validator.
- Benefits: One keystroke to confirm end-to-end health.
- Scope/Impact: tiny
- Risks/Trade-offs: None
- Implementation outline:
  1. Add `.vscode/tasks.json` with a `smoke:week` task
  2. Wire to `python scripts/weekly_report.py --season ${input:season} --report-week ${input:week}` then validator
- Effort: S
- Status: proposed
- Owner: <assign>
- Acceptance criteria: Task appears in VS Code list and exits 0 on success
- Validation: Run the task for a known good week

### (example) Retryable validator
- Category: Reliability, Testing
- Problem: Occasional flakiness could fail the validator unnecessarily.
- Proposal: Add `--retries` and a short backoff to the validator for reading files/IO.
- Benefits: Smoother pipelines; fewer false negatives.
- Scope/Impact: small
- Risks/Trade-offs: Slightly longer runtime on failure
- Implementation outline:
  1. Add optional `--retries` and `--retry-wait` flags
  2. Wrap file reads and parsing in a retry loop
- Effort: S
- Status: proposed
- Owner: <assign>
- Acceptance criteria: Validator succeeds on transient read issues
- Validation: Simulate a delayed write and confirm retry succeeds

---

## Done
- (empty)

## Dropped
- (empty)
