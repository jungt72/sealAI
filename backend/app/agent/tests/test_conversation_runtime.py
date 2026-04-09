"""
Tests for runtime/conversation_runtime.py — Phase F-A.4

No network I/O — OpenAI client is fully mocked.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator, NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.agent.boundaries import FAST_PATH_DISCLAIMER
from app.agent.runtime.reply_composition import build_turn_context_instruction
from app.agent.runtime.conversation_runtime import (
    ConversationResult,
    _build_conversation_turn_context,
    _build_conversation_strategy_contract,
    _build_messages,
    _conversation_visible_event,
    _sse,
    _sse_end,
    _sse_error,
    iter_conversation_events,
    run_conversation,
    stream_conversation,
)
from app.agent.runtime.turn_context import build_turn_context_contract


# ---------------------------------------------------------------------------
# SSE helpers unit tests
# ---------------------------------------------------------------------------

class TestSSEHelpers:
    def test_conversation_visible_event_is_canonical_text_adapter(self):
        assert _conversation_visible_event("text_chunk", "Hallo") == {
            "type": "text_chunk",
            "text": "Hallo",
        }

    def test_sse_produces_valid_format(self):
        result = _sse("text_chunk", "Hallo")
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        payload = json.loads(result[6:])
        assert payload == {"type": "text_chunk", "text": "Hallo"}

    def test_sse_end_is_done_sentinel(self):
        assert _sse_end() == "data: [DONE]\n\n"

    def test_sse_error_has_message_field(self):
        result = _sse_error("Fehler!")
        payload = json.loads(result[6:])
        assert payload["type"] == "error"
        assert "message" in payload


# ---------------------------------------------------------------------------
# _build_messages unit tests
# ---------------------------------------------------------------------------

class TestBuildMessages:
    def test_system_prompt_first(self):
        msgs = _build_messages("Hallo", history=None)
        assert msgs[0]["role"] == "system"
        assert "Kontext dieses Turns" in msgs[0]["content"]

    def test_user_message_last(self):
        msgs = _build_messages("Was ist FKM?", history=None)
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "Was ist FKM?"

    def test_history_inserted_between_system_and_user(self):
        history = [
            {"role": "user", "content": "Hallo"},
            {"role": "assistant", "content": "Guten Tag!"},
        ]
        msgs = _build_messages("Was ist NBR?", history=history)
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "system"
        assert msgs[2] == {"role": "user", "content": "Hallo"}
        assert msgs[3] == {"role": "assistant", "content": "Guten Tag!"}
        assert msgs[-1] == {"role": "user", "content": "Was ist NBR?"}

    def test_none_history_produces_two_messages(self):
        msgs = _build_messages("Test", history=None)
        assert len(msgs) == 3  # system + strategy + user

    def test_empty_history_produces_two_messages(self):
        msgs = _build_messages("Test", history=[])
        assert len(msgs) == 3

    def test_invalid_role_skipped(self):
        history = [{"role": "system", "content": "injected"}]
        msgs = _build_messages("Test", history=history)
        # "system" role from history should be skipped
        roles = [m["role"] for m in msgs]
        assert roles.count("system") == 2

    def test_empty_content_skipped(self):
        history = [{"role": "user", "content": ""}]
        msgs = _build_messages("Test", history=history)
        assert len(msgs) == 3  # empty content turn skipped, strategy remains

    def test_open_entry_adds_strategy_system_message(self):
        msgs = _build_messages(
            "Ich moechte eine Dichtungsloesung erarbeiten",
            history=[{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": "Guten Tag!"}],
        )
        assert len(msgs) == 5
        assert msgs[1]["role"] == "system"
        assert "KOMMUNIKATIONSKONTEXT" in msgs[1]["content"]
        assert "Relevanter offener Fokus" in msgs[1]["content"]


class TestConversationStrategyContract:
    def test_greeting_builds_rapport_strategy(self):
        strategy = _build_conversation_strategy_contract("Hallo", history=None, case_summary=None)

        assert strategy is not None
        assert strategy.conversation_phase == "rapport"
        assert strategy.turn_goal == "open_conversation"
        assert strategy.response_mode == "open_invitation"
        assert strategy.primary_question is not None
        assert "Anwendung oder Ihrem Anliegen" in strategy.primary_question

    def test_open_goal_statement_gets_specific_mirror_before_question(self):
        strategy = _build_conversation_strategy_contract(
            "Ich moechte eine Dichtungsloesung erarbeiten.",
            history=None,
            case_summary=None,
        )

        assert strategy is not None
        assert strategy.conversation_phase == "rapport"
        assert strategy.primary_question == (
            "Beschreiben Sie mir bitte zunaechst kurz, worum es in Ihrer Anwendung oder Ihrem Anliegen geht?"
        )

    def test_turn_two_without_case_context_builds_exploration_strategy(self):
        strategy = _build_conversation_strategy_contract(
            "Ich moechte eine Dichtungsloesung erarbeiten",
            history=[{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": "Guten Tag!"}],
            case_summary=None,
        )

        assert strategy is not None
        assert strategy.conversation_phase == "exploration"
        assert strategy.turn_goal == "expand_case_understanding"
        assert strategy.response_mode == "open_invitation"
        assert strategy.primary_question is not None
        assert strategy.primary_question == (
            "Welche Anwendung oder Situation sollen wir uns dafuer als Erstes genauer ansehen?"
        )

    def test_problem_statement_in_exploration_stays_problem_led(self):
        strategy = _build_conversation_strategy_contract(
            "Wir haben immer wieder Leckageprobleme.",
            history=[{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": "Guten Tag!"}],
            case_summary=None,
        )

        assert strategy is not None
        assert strategy.conversation_phase == "exploration"
        assert strategy.primary_question == (
            "In welcher Situation zeigt sich die Leckage oder das Problem am deutlichsten?"
        )

    def test_later_turn_with_case_context_uses_recommendation_strategy(self):
        strategy = _build_conversation_strategy_contract(
            "Wir haben 180 bar und 90 C an der Welle.",
            history=[
                {"role": "user", "content": "Hallo"},
                {"role": "assistant", "content": "Guten Tag!"},
                {"role": "user", "content": "Es geht um eine Pumpendichtung."},
                {"role": "assistant", "content": "Verstanden."},
            ],
            case_summary="Medium: Wasser | Druck: 12 bar",
        )
        assert strategy is not None
        assert strategy.conversation_phase == "narrowing"
        assert strategy.primary_question == "Welche Drehzahl liegt ungefähr an?"

    def test_explicit_instant_mode_uses_guided_explanation_without_primary_question(self):
        strategy = _build_conversation_strategy_contract(
            "Hallo",
            history=None,
            case_summary=None,
            mode="CONVERSATION",
        )

        assert strategy is not None
        assert strategy.turn_goal == "answer_light_request"
        assert strategy.response_mode == "guided_explanation"
        assert strategy.primary_question is None

    def test_explicit_EXPLORATION_mode_forces_exploration_focus(self):
        strategy = _build_conversation_strategy_contract(
            "Wir haben immer wieder Leckageprobleme.",
            history=None,
            case_summary=None,
            mode="EXPLORATION",
        )

        assert strategy is not None
        assert strategy.conversation_phase == "exploration"
        assert strategy.response_mode == "open_invitation"
        assert strategy.primary_question is not None

    def test_strategy_instruction_invites_story_not_parameter_list(self):
        strategy = _build_conversation_strategy_contract(
            "Ich moechte eine Dichtungsloesung erarbeiten",
            history=[{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": "Guten Tag!"}],
            case_summary=None,
        )

        instruction = build_turn_context_instruction(
            build_turn_context_contract(strategy=strategy)
        )

        assert instruction is not None
        assert "KOMMUNIKATIONSKONTEXT" in instruction
        assert "Der Nutzer befindet sich noch in einer offenen Orientierungsphase." in instruction
        assert "Relevanter offener Fokus" in instruction
        assert "Beginne die sichtbare Antwort IMMER mit diesem ersten Satz" not in instruction
        assert "Reagiere zuerst konkret auf die letzte Nutzeraeusserung" not in instruction
        assert "Das Problembild wird noch eingeordnet." in instruction

    def test_rapport_instruction_blocks_technical_single_field_opening(self):
        strategy = _build_conversation_strategy_contract("Hallo", history=None, case_summary=None)

        instruction = build_turn_context_instruction(
            build_turn_context_contract(strategy=strategy)
        )

        assert instruction is not None
        assert "Im Einstieg steht Orientierung im Vordergrund." in instruction

    def test_correction_strategy_sets_user_signal_mirror(self):
        strategy = _build_conversation_strategy_contract(
            "Ich korrigiere: Der Druck liegt nicht bei 12, sondern bei 18 bar.",
            history=[{"role": "user", "content": "Der Druck liegt bei 12 bar."}],
            case_summary="- Druck: 12 bar",
            mode="EXPLORATION",
        )

        assert strategy is not None
        assert strategy.user_signal_mirror == "Verstanden, ich gehe jetzt von Ihrer Korrektur aus"

    def test_turn_context_includes_confirmed_facts_and_open_focus_from_case_context(self):
        turn_context = _build_conversation_turn_context(
            "Ich korrigiere: Der Druck liegt bei 18 bar.",
            history=[
                {"role": "user", "content": "Wir haben Leckage am Wellenaustritt."},
                {"role": "assistant", "content": "Wo genau tritt sie auf?"},
            ],
            case_summary="- Medium: Wasser\n- Druck: 12 bar",
            mode="EXPLORATION",
        )

        assert turn_context is not None
        assert turn_context.confirmed_facts_summary == ["Medium: Wasser", "Druck: 12 bar", "Wir haben Leckage am Wellenaustritt."]
        assert turn_context.open_points_summary
        assert "Einbausituation" in turn_context.open_points_summary[0]

    def test_known_medium_and_rotary_context_shift_focus_to_speed(self):
        strategy = _build_conversation_strategy_contract(
            "Es ist eine rotierende Welle.",
            history=[{"role": "user", "content": "Wir dichten Salzwasser ab."}],
            case_summary="- Medium: Salzwasser",
        )

        assert strategy is not None
        assert strategy.conversation_phase == "narrowing"
        assert strategy.primary_question == "Welche Drehzahl liegt ungefähr an?"
        assert "rotierenden Welle" in strategy.primary_question_reason

    def test_known_rotary_context_prioritizes_geometry_before_pressure_temperature(self):
        strategy = _build_conversation_strategy_contract(
            "Es geht um eine bestehende Wellenabdichtung an einer Pumpe.",
            history=[{"role": "user", "content": "Wir dichten Wasser ab."}],
            case_summary="- Medium: Wasser\n- Wellen-Ø: 50 mm\n- Drehzahl: 2900 rpm\n- Einbausituation: rotierende Welle",
        )

        assert strategy is not None
        assert strategy.conversation_phase == "narrowing"
        assert strategy.primary_question == "Welche Geometrie oder vorhandene Bauform liegt an der Dichtstelle vor?"

    def test_known_geometry_and_pressure_shift_focus_to_gap_and_tolerance(self):
        strategy = _build_conversation_strategy_contract(
            "Die Dichtung sitzt in einer Nut im Gehaeuse.",
            history=[{"role": "user", "content": "Es geht um eine Hydraulikanwendung."}],
            case_summary="- Medium: Hydraulikoel\n- Geometrie: Nut im Gehaeuse\n- Druck: 180 bar\n- Temperatur: 80 C",
        )

        assert strategy is not None
        assert strategy.primary_question == "Mit welchem Spalt- oder Toleranzbereich muessen wir an der Dichtstelle rechnen?"

    def test_linear_correction_reframes_focus_away_from_rotary_followup(self):
        strategy = _build_conversation_strategy_contract(
            "Korrektur: keine rotierende Welle, sondern lineare Bewegung.",
            history=[{"role": "user", "content": "Es geht um eine rotierende Welle."}],
            case_summary="- Medium: Wasser\n- Wellen-Ø: 50 mm\n- Drehzahl: 2900 rpm",
        )

        assert strategy is not None
        assert strategy.primary_question == "Welche Geometrie oder vorhandene Bauform liegt an der Dichtstelle vor?"
        assert "rotierenden Welle" not in strategy.primary_question_reason


# ---------------------------------------------------------------------------
# Fake OpenAI streaming infrastructure
# ---------------------------------------------------------------------------

class _FakeDelta(NamedTuple):
    content: str | None


class _FakeChoice(NamedTuple):
    delta: _FakeDelta


class _FakeChunk(NamedTuple):
    choices: list[_FakeChoice]


def _make_stream_chunks(texts: list[str]):
    """Build fake OpenAI stream chunks from a list of text deltas."""
    return [_FakeChunk(choices=[_FakeChoice(delta=_FakeDelta(content=t))]) for t in texts]


class _FakeStream:
    """Async context manager that yields fake chunks."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for chunk in self._chunks:
            yield chunk


def _patch_openai(chunks: list[str]):
    """Return a context manager that patches OpenAI with the given text chunks."""
    fake_stream = _FakeStream(_make_stream_chunks(chunks))
    mock_client = MagicMock()
    # create() is now called with `await` — AsyncMock makes the return value awaitable.
    mock_client.chat.completions.create = AsyncMock(return_value=fake_stream)
    mock_openai = MagicMock()
    mock_openai.AsyncOpenAI.return_value = mock_client
    return patch("app.agent.runtime.conversation_runtime.openai", mock_openai)


# ---------------------------------------------------------------------------
# stream_conversation integration tests
# ---------------------------------------------------------------------------

async def _collect(gen: AsyncGenerator[str, None]) -> list[str]:
    """Collect all SSE events from the generator."""
    events = []
    async for event in gen:
        events.append(event)
    return events


async def _collect_canonical_reply(message: str, *, history: list[dict[str, str]] | None = None) -> str:
    result = await run_conversation(message, history=history)
    return result.reply_text


def _parse_events(events: list[str]) -> list[dict]:
    """Parse SSE data lines into dicts, skipping [DONE]."""
    result = []
    for e in events:
        if not e.startswith("data: "):
            continue
        raw = e[6:].strip()
        if raw == "[DONE]":
            result.append({"type": "__DONE__"})
            continue
        result.append(json.loads(raw))
    return result


class TestStreamConversation:
    @pytest.mark.asyncio
    async def test_text_chunks_emitted(self):
        with _patch_openai(["FKM ist ", "ein Fluorelastomer."]):
            events = await _collect(stream_conversation("Was ist FKM?"))
        parsed = _parse_events(events)
        text_chunks = [e for e in parsed if e.get("type") == "text_chunk"]
        assert len(text_chunks) >= 1
        combined = "".join(e["text"] for e in text_chunks)
        assert "FKM" in combined
        assert all(e.get("preview_only") is True for e in text_chunks)

    @pytest.mark.asyncio
    async def test_final_state_update_reflects_case_context_in_light_reply(self):
        with _patch_openai(["Dann schaue ich als Naechstes auf die Einbausituation."]):
            events = await _collect(
                stream_conversation(
                    "Ich korrigiere: Der Druck liegt bei 18 bar.",
                    history=[{"role": "user", "content": "Wir haben Leckage am Wellenaustritt."}],
                    case_summary="- Medium: Wasser\n- Druck: 12 bar",
                    mode="EXPLORATION",
                )
            )
        parsed = _parse_events(events)
        state_update = next(e for e in parsed if e.get("type") == "state_update")
        assert state_update["reply"].startswith("Verstanden, ich gehe jetzt von Ihrer Korrektur aus.")
        assert "Dann schaue ich als Naechstes auf die Einbausituation." in state_update["reply"]

    @pytest.mark.asyncio
    async def test_final_state_update_uses_llm_reply_without_prefix_injection_when_no_context_exists(self):
        with _patch_openai(["FKM ist ein Fluorelastomer."]):
            events = await _collect(stream_conversation("Was ist FKM?"))
        parsed = _parse_events(events)
        state_update = next(e for e in parsed if e.get("type") == "state_update")
        assert state_update["reply"] == "FKM ist ein Fluorelastomer."
        assert state_update["response_class"] == "conversational_answer"

    @pytest.mark.asyncio
    async def test_CONVERSATION_hallo_keeps_natural_llm_greeting_without_template_prefix(self):
        with _patch_openai(["Hallo, womit kann ich Ihnen helfen?"]):
            events = await _collect(stream_conversation("Hallo", mode="CONVERSATION"))
        parsed = _parse_events(events)
        state_update = next(e for e in parsed if e.get("type") == "state_update")
        assert state_update["reply"] == "Hallo, womit kann ich Ihnen helfen?"

    @pytest.mark.asyncio
    async def test_CONVERSATION_smalltalk_keeps_human_llm_answer_without_template_prefix(self):
        with _patch_openai(["Danke, gut. Wie kann ich bei der Dichtungstechnik helfen?"]):
            events = await _collect(stream_conversation("Wie geht es dir?", mode="CONVERSATION"))
        parsed = _parse_events(events)
        state_update = next(e for e in parsed if e.get("type") == "state_update")
        assert state_update["reply"] == "Danke, gut. Wie kann ich bei der Dichtungstechnik helfen?"

    @pytest.mark.asyncio
    async def test_EXPLORATION_phase_prompt_keeps_domain_entry_natural(self):
        with _patch_openai(["Dann ordnen wir das Problem zuerst nach der konkreten Betriebssituation. Wann zeigt sich die Leckage am deutlichsten?"]):
            events = await _collect(
                stream_conversation("Wir haben immer wieder Leckageprobleme.", mode="EXPLORATION")
            )
        parsed = _parse_events(events)
        state_update = next(e for e in parsed if e.get("type") == "state_update")
        assert state_update["reply"].startswith(
            "Verstanden, Sie beschreiben ein konkretes Leckage- oder Ausfallbild."
        )
        assert "Dann ordnen wir das Problem zuerst nach der konkreten Betriebssituation." in state_update["reply"]
        assert "Wann zeigt sich die Leckage am deutlichsten?" in state_update["reply"]

    @pytest.mark.asyncio
    async def test_focus_reply_trims_deficit_language_and_multiple_questions(self):
        with _patch_openai(["Es fehlen noch Drehzahl und Einbausituation. Welche Drehzahl liegt an? Und wie ist die Einbausituation?"]):
            events = await _collect(
                stream_conversation(
                    "Es ist eine rotierende Welle.",
                    history=[{"role": "user", "content": "Wir dichten Salzwasser ab."}],
                    case_summary="- Medium: Salzwasser",
                )
            )

        parsed = _parse_events(events)
        state_update = next(e for e in parsed if e.get("type") == "state_update")
        assert "Es fehlen noch" not in state_update["reply"]
        assert state_update["reply"].count("?") == 1
        assert "Welche Drehzahl liegt ungefähr an?" in state_update["reply"]

    @pytest.mark.asyncio
    async def test_CONVERSATION_mode_avoids_primary_question_prompting(self):
        captured_messages = []
        mock_client = MagicMock()

        def _capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return _FakeStream(_make_stream_chunks(["Hallo."]))

        mock_client.chat.completions.create.side_effect = _capture_create
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = mock_client

        with patch("app.agent.runtime.conversation_runtime.openai", mock_openai):
            await _collect(stream_conversation("Hallo", mode="CONVERSATION"))

        joined = "\n".join(m["content"] for m in captured_messages if m["role"] == "system")
        assert "Stelle genau diese eine priorisierte Frage" not in joined

    @pytest.mark.asyncio
    async def test_EXPLORATION_mode_keeps_single_focus_prompting(self):
        captured_messages = []
        mock_client = MagicMock()

        def _capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return _FakeStream(_make_stream_chunks(["Verstanden."]))

        mock_client.chat.completions.create.side_effect = _capture_create
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = mock_client

        with patch("app.agent.runtime.conversation_runtime.openai", mock_openai):
            await _collect(stream_conversation("Wir haben immer wieder Leckageprobleme.", mode="EXPLORATION"))

        joined = "\n".join(m["content"] for m in captured_messages if m["role"] == "system")
        assert "Relevanter offener Fokus" in joined
        assert joined.count("In welcher Situation zeigt sich die Leckage oder das Problem am deutlichsten?") == 1
        assert "Der sichtbarste Auftretensmoment macht die naechste Eingrenzung am belastbarsten." not in joined
        assert "Beginne die sichtbare Antwort IMMER mit diesem ersten Satz" not in joined

    @pytest.mark.asyncio
    async def test_boundary_block_always_appended(self):
        with _patch_openai(["Hallo!"]):
            events = await _collect(stream_conversation("Hallo"))
        parsed = _parse_events(events)
        boundary_events = [e for e in parsed if e.get("type") == "boundary_block"]
        assert len(boundary_events) == 1
        assert FAST_PATH_DISCLAIMER in boundary_events[0]["text"]

    @pytest.mark.asyncio
    async def test_done_sentinel_always_last(self):
        with _patch_openai(["Text."]):
            events = await _collect(stream_conversation("Test"))
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_stream_end_event_before_done(self):
        with _patch_openai(["Text."]):
            events = await _collect(stream_conversation("Test"))
        parsed = _parse_events(events)
        stream_end = [e for e in parsed if e.get("type") == "stream_end"]
        assert len(stream_end) == 1
        # stream_end must come before __DONE__
        end_idx = next(i for i, e in enumerate(parsed) if e.get("type") == "stream_end")
        done_idx = next(i for i, e in enumerate(parsed) if e.get("type") == "__DONE__")
        assert end_idx < done_idx

    @pytest.mark.asyncio
    async def test_artifacts_in_chunks_filtered(self):
        """UUIDs in LLM output are stripped via render_chunk."""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        with _patch_openai([f"Trace {uuid} — FKM."]):
            events = await _collect(stream_conversation("Was ist FKM?"))
        parsed = _parse_events(events)
        all_text = "".join(
            e.get("text", "") for e in parsed if e.get("type") == "text_chunk"
        )
        assert uuid not in all_text
        assert "FKM" in all_text

    @pytest.mark.asyncio
    async def test_policy_violation_emits_replacement(self):
        """When full assembled text violates policy, a text_replacement event is emitted."""
        # Output with recommendation language → policy violation
        with _patch_openai(["Ich empfehle FKM für diese Dichtung."]):
            events = await _collect(stream_conversation("Welches Material?"))
        parsed = _parse_events(events)
        replacements = [e for e in parsed if e.get("type") == "text_replacement"]
        assert len(replacements) == 1
        # Replacement text is the safe fallback, not the original
        assert "empfehle" not in replacements[0]["text"]
        state_update = next(e for e in parsed if e.get("type") == "state_update")
        assert state_update["reply"] == replacements[0]["text"]
        assert "empfehle" not in state_update["reply"]

    @pytest.mark.asyncio
    async def test_clean_text_no_replacement(self):
        """Clean text produces no text_replacement event."""
        with _patch_openai(["FKM ist ein Fluorelastomer aus der Gruppe der Hochleistungswerkstoffe."]):
            events = await _collect(stream_conversation("Was ist FKM?"))
        parsed = _parse_events(events)
        replacements = [e for e in parsed if e.get("type") == "text_replacement"]
        assert len(replacements) == 0

    @pytest.mark.asyncio
    async def test_llm_error_yields_error_event_then_done(self):
        """LLM exception → error SSE event + [DONE], no crash."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ConnectionError("network down")
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = mock_client

        with patch("app.agent.runtime.conversation_runtime.openai", mock_openai):
            events = await _collect(stream_conversation("Test"))

        parsed = _parse_events(events)
        error_events = [e for e in parsed if e.get("type") == "error"]
        assert len(error_events) == 1
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_llm_error_no_boundary_block(self):
        """On LLM error, boundary block is NOT appended (no partial output)."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = TimeoutError("timeout")
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = mock_client

        with patch("app.agent.runtime.conversation_runtime.openai", mock_openai):
            events = await _collect(stream_conversation("Test"))

        parsed = _parse_events(events)
        boundary_events = [e for e in parsed if e.get("type") == "boundary_block"]
        assert len(boundary_events) == 0

    @pytest.mark.asyncio
    async def test_empty_llm_response_still_sends_boundary_and_done(self):
        """Even with empty LLM output, boundary block and [DONE] are sent."""
        with _patch_openai([]):
            events = await _collect(stream_conversation("Test"))
        parsed = _parse_events(events)
        boundary_events = [e for e in parsed if e.get("type") == "boundary_block"]
        assert len(boundary_events) == 1
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_history_passed_to_llm(self):
        """Conversation history is included in the messages sent to the LLM."""
        captured_messages = []

        class _CapturingStream(_FakeStream):
            pass

        mock_client = MagicMock()

        def _capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return _FakeStream(["OK"])

        mock_client.chat.completions.create.side_effect = _capture_create
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = mock_client

        history = [
            {"role": "user", "content": "Hallo"},
            {"role": "assistant", "content": "Guten Tag!"},
        ]
        with patch("app.agent.runtime.conversation_runtime.openai", mock_openai):
            await _collect(stream_conversation("Was ist NBR?", history=history))

        contents = [m["content"] for m in captured_messages]
        assert "Hallo" in contents
        assert "Guten Tag!" in contents
        assert "Was ist NBR?" in contents

    @pytest.mark.asyncio
    async def test_null_delta_content_skipped(self):
        """Chunks with None content do not emit events."""
        chunks = [
            _FakeChunk(choices=[_FakeChoice(delta=_FakeDelta(content=None))]),
            _FakeChunk(choices=[_FakeChoice(delta=_FakeDelta(content="FKM."))]),
        ]
        fake_stream = _FakeStream(chunks)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = fake_stream
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = mock_client

        with patch("app.agent.runtime.conversation_runtime.openai", mock_openai):
            events = await _collect(stream_conversation("Was ist FKM?"))

        parsed = _parse_events(events)
        text_chunks = [e for e in parsed if e.get("type") == "text_chunk"]
        assert all(e["text"] for e in text_chunks)  # no empty text chunks


class TestConversationParity:
    @pytest.mark.asyncio
    async def test_run_conversation_matches_stream_state_update_reply(self):
        with _patch_openai(["FKM ist ", "ein Fluorelastomer."]):
            result = await run_conversation("Was ist FKM?")
        with _patch_openai(["FKM ist ", "ein Fluorelastomer."]):
            events = await _collect(stream_conversation("Was ist FKM?"))

        parsed = _parse_events(events)
        state_update = next(e for e in parsed if e.get("type") == "state_update")
        assert isinstance(result, ConversationResult)
        assert result.error_message is None
        assert result.reply_text == state_update["reply"]

    @pytest.mark.asyncio
    async def test_run_conversation_applies_same_replacement_semantics_as_stream(self):
        with _patch_openai(["Ich empfehle FKM für diese Dichtung."]):
            result = await run_conversation("Welches Material?")
        with _patch_openai(["Ich empfehle FKM für diese Dichtung."]):
            canonical_from_shared_runtime = await _collect_canonical_reply("Welches Material?")

        assert result.reply_text == canonical_from_shared_runtime
        assert "empfehle" not in result.reply_text

    @pytest.mark.asyncio
    async def test_run_conversation_returns_same_error_text_as_stream(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = TimeoutError("timeout")
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = mock_client

        with patch("app.agent.runtime.conversation_runtime.openai", mock_openai):
            result = await run_conversation("Test")
        with patch("app.agent.runtime.conversation_runtime.openai", mock_openai):
            events = await _collect(stream_conversation("Test"))

        parsed = _parse_events(events)
        error_message = next(e["message"] for e in parsed if e.get("type") == "error")
        assert result.reply_text == error_message
        assert result.error_message == error_message

    @pytest.mark.asyncio
    async def test_iter_conversation_events_has_no_done_sentinel_transport_detail(self):
        with _patch_openai(["Hallo"]):
            events = [event async for event in iter_conversation_events("Hallo")]
        assert [event["type"] for event in events][-3:] == ["state_update", "boundary_block", "stream_end"]
