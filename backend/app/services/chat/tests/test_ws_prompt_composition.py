from __future__ import annotations

from types import SimpleNamespace

from app.services.chat.prompt_utils import truncate_history_for_prompt


def _msg(text: str):
    return SimpleNamespace(content=text)


def test_truncate_history_keeps_recent():
    system = "System prompt"
    history = [_msg(f"m{i}") for i in range(10)]
    # set max_chars small so only last messages kept
    kept = truncate_history_for_prompt(system, history, max_chars=20)
    assert isinstance(kept, list)
    assert len(kept) <= len(history)
    # last message should be present
    assert kept and kept[-1].content == "m9"
