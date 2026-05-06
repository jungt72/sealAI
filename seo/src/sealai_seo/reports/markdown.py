from __future__ import annotations

from pathlib import Path


def write_report(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"
