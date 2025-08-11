"""Markdown rendering helpers with deterministic formatting.

Tables are built with escaped pipe characters and stable column ordering to
ensure reproducible output suitable for parsing.
"""
from __future__ import annotations
from typing import Any


def md_escape(s: str) -> str:
    """Escape pipe characters for safe Markdown table rendering."""
    return s.replace("|", "\\|")


def md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a Markdown table into a list of lines (header, separator, rows)."""
    def esc(v: Any) -> str:
        return md_escape(str(v))

    lines: list[str] = []
    lines.append("| " + " | ".join(esc(h) for h in headers) + " |")
    lines.append("| " + " | ".join(":---" for _ in headers) + " |")
    for r in rows:
        lines.append("| " + " | ".join(esc(c) for c in r) + " |")
    return lines
