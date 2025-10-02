from __future__ import annotations

from app.services.langgraph.prompting import build_system_prompt_from_parts, count_tokens


def test_build_system_prompt_truncation_basic():
    template = "Base system prompt with some fixed instructions."
    rag = ["Doc A: " + "x" * 2000, "Doc B: " + "y" * 2000]
    # very small max_tokens to force truncation
    out = build_system_prompt_from_parts(template, summary=None, rag_docs=rag, max_tokens=10, model="gpt-4o")
    assert isinstance(out, str)
    # Base template must still be present
    assert "Base system prompt" in out


def test_count_tokens_estimate():
    s = "Hello world! " * 10
    t = count_tokens(s, model="gpt-4o")
    assert isinstance(t, int) and t > 0

