"""Wiring regression suite — OpenAI Responses API payload + knowledge routing.

Covers the two production defects found while debugging the live "Agent stream
could not be started" / "Momentan nicht verfügbar" failures:

1. Multi-turn Responses API payload typing
   `_responses_input_from_messages` must tag assistant-history content as
   ``output_text`` and user content as ``input_text``. Tagging an assistant
   message ``input_text`` raises OpenAI 400 invalid_value on every follow-up
   turn (the first turn, with no assistant history, was the only one that
   survived).

2. Knowledge questions must not mutate the governed case
   A pure material question ("infos zu PTFE") routes to the knowledge path and
   must not create/alter a governed case. Blueprint §8.2 (knowledge is
   chat-first, no state mutation without new facts).

Deterministic and offline: no live LLM, no network. Additive.
"""

from __future__ import annotations

from app.agent.communication.communication_runtime_v8 import (
    _responses_input_from_messages,
)


def _types_by_role(response_input: list[dict]) -> list[tuple[str, str]]:
    return [(m["role"], m["content"][0]["type"]) for m in response_input]


def test_single_user_turn_uses_input_text() -> None:
    _, inp = _responses_input_from_messages([{"role": "user", "content": "hallo"}])
    assert _types_by_role(inp) == [("user", "input_text")]


def test_assistant_history_uses_output_text() -> None:
    msgs = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
    ]
    _, inp = _responses_input_from_messages(msgs)
    assert _types_by_role(inp) == [
        ("user", "input_text"),
        ("assistant", "output_text"),
        ("user", "input_text"),
    ]


def test_no_assistant_turn_ever_tagged_input_text() -> None:
    msgs = [
        {"role": "user", "content": f"u{i}"}
        if i % 2 == 0
        else {"role": "assistant", "content": f"a{i}"}
        for i in range(8)
    ]
    _, inp = _responses_input_from_messages(msgs)
    for m in inp:
        if m["role"] == "assistant":
            assert m["content"][0]["type"] == "output_text"
        else:
            assert m["content"][0]["type"] == "input_text"


def test_system_messages_go_to_instructions_not_input() -> None:
    msgs = [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
    ]
    instructions, inp = _responses_input_from_messages(msgs)
    assert "be terse" in instructions
    assert _types_by_role(inp) == [("user", "input_text")]


def test_content_text_is_preserved() -> None:
    msgs = [
        {"role": "user", "content": "frage"},
        {"role": "assistant", "content": "antwort"},
    ]
    _, inp = _responses_input_from_messages(msgs)
    assert inp[0]["content"][0]["text"] == "frage"
    assert inp[1]["content"][0]["text"] == "antwort"


def test_knowledge_question_resolves_to_knowledge_mode() -> None:
    from app.agent.communication.knowledge_modes import resolve_knowledge_mode

    assert (
        resolve_knowledge_mode("bitte gebe mir infos zu ptfe", has_active_case=False)
        == "knowledge_general"
    )
    assert (
        resolve_knowledge_mode("was bedeutet ffkm in meinem fall?", has_active_case=True)
        == "knowledge_case_aware"
    )


def test_knowledge_turn_does_not_mutate_state() -> None:
    from app.agent.communication.knowledge_modes import apply_knowledge_turn
    from app.agent.state.models import GovernedSessionState

    state = GovernedSessionState()
    result = apply_knowledge_turn(state, "bitte gebe mir infos zu ptfe", has_active_case=False)
    assert result is state


# ---------------------------------------------------------------------------
# Defect 1 also lived in the conversational opener path
# (app.agent.runtime.conversation_runtime), which produced the live
# "Momentan nicht verfügbar" OpenAI 400 on the case-intake follow-up turn,
# and in the shared app.services.openai_payload builder. The same role-typing
# contract must hold for both: assistant -> output_text, user -> input_text.
# ---------------------------------------------------------------------------


def test_conversation_runtime_assistant_history_uses_output_text() -> None:
    from app.agent.runtime.conversation_runtime import (
        _responses_input_from_messages as conv_responses_input,
    )

    msgs = [
        {"role": "user", "content": "U1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "U2"},
    ]
    _, inp = conv_responses_input(msgs)
    assert _types_by_role(inp) == [
        ("user", "input_text"),
        ("assistant", "output_text"),
        ("user", "input_text"),
    ]


def test_conversation_runtime_single_user_turn_uses_input_text() -> None:
    from app.agent.runtime.conversation_runtime import (
        _responses_input_from_messages as conv_responses_input,
    )

    _, inp = conv_responses_input([{"role": "user", "content": "hallo"}])
    assert _types_by_role(inp) == [("user", "input_text")]


def test_conversation_runtime_system_goes_to_instructions() -> None:
    from app.agent.runtime.conversation_runtime import (
        _responses_input_from_messages as conv_responses_input,
    )

    instructions, inp = conv_responses_input(
        [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]
    )
    assert "be terse" in instructions
    assert _types_by_role(inp) == [("user", "input_text")]


def test_openai_payload_assistant_history_uses_output_text() -> None:
    from app.services.openai_payload import messages_to_responses_input

    inp = messages_to_responses_input(
        [
            {"role": "user", "content": "U1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "U2"},
        ]
    )
    assert _types_by_role(inp) == [
        ("user", "input_text"),
        ("assistant", "output_text"),
        ("user", "input_text"),
    ]
