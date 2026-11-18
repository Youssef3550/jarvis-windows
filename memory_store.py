"""Long-term memory: one plain Markdown file you can open and edit yourself.

Facts are lines starting with "- ". Headings and other lines are kept as they are.
"""
from __future__ import annotations

import config


def _raw() -> list[str]:
    if not config.MEMORY_FILE.exists():
        return []
    return config.MEMORY_FILE.read_text(encoding="utf-8").splitlines()


def _write(lines: list[str]) -> None:
    config.MEMORY_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def list_facts() -> list[str]:
    return [l[2:].strip() for l in _raw() if l.startswith("- ") and l[2:].strip()]


def remember(fact: str) -> str:
    fact = " ".join(fact.split())
    if any(f.lower() == fact.lower() for f in list_facts()):
        return "Already remembered."
    lines = _raw()
    if "## Learned in conversation" not in lines:
        lines += ["", "## Learned in conversation"]
    lines.append(f"- {fact}")
    _write(lines)
    return "Remembered."


def forget(query: str) -> str:
    q = query.lower().strip()
    lines = _raw()
    keep = [l for l in lines if not (l.startswith("- ") and q in l.lower())]
    removed = len(lines) - len(keep)
    if removed:
        _write(keep)
    return f"Forgot {removed} item(s)." if removed else "Nothing matched."
