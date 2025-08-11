# render.py
from __future__ import annotations
from typing import Any


def md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    def esc(v: Any) -> str:
        return md_escape(str(v))

    lines: list[str] = []
    lines.append("| " + " | ".join(esc(h) for h in headers) + " |")
    lines.append("| " + " | ".join(":---" for _ in headers) + " |")
    for r in rows:
        lines.append("| " + " | ".join(esc(c) for c in r) + " |")
    return lines
