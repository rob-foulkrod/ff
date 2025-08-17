"""Output formatters for modular weekly report contexts."""
from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

from scripts.lib.report_models import WeeklyContext


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
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
    payload = ctx.to_json_payload(schema_version)
    if pretty:
        return json.dumps(payload, indent=2, sort_keys=True)
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)
