from __future__ import annotations

from pathlib import Path


def test_frontdoor_smalltalk_reply_is_not_a_greeting() -> None:
    # Avoid importing nodes_frontdoor directly to prevent import-time circularities.
    # Resolve the nodes_frontdoor.py path relative to this test file so it works both
    # in-repo and inside Docker images where the repo root is typically /app.
    base = Path(__file__).resolve().parents[1]  # .../app/langgraph_v2
    path = base / "nodes" / "nodes_frontdoor.py"

    with path.open("r", encoding="utf-8") as f:
        content = f.read()

    # Keep this test intentionally simple: no meta preamble / greeting in the smalltalk path.
    # (Exact assertions depend on your current implementation; keep your existing assertions below.)
    assert "Guten Tag" not in content
    assert "Hallo" not in content
    assert "Hi" not in content
