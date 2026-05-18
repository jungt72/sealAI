from __future__ import annotations

import logging
from typing import Any

from langgraph.config import get_stream_writer

from app.agent.communication.governed_answer_composer import (
    GovernedAnswerComposer,
    GovernedAnswerComposerInput,
    is_governed_answer_composer_enabled,
    render_governed_contextual_fallback,
    safe_governed_answer_composer_error_reason,
    should_render_governed_contextual_fallback,
)
from app.agent.communication.governed_answer_context import GovernedAnswerContext
from app.agent.graph import GraphState

log = logging.getLogger(__name__)


def _get_stream_writer_or_none():
    try:
        return get_stream_writer()
    except RuntimeError:
        return None
    except Exception:  # noqa: BLE001
        return None


def _emit_composer_stream_event(writer, event_type: str, **payload) -> None:  # noqa: ANN001
    if writer is None:
        return
    try:
        writer(
            {
                "event_type": f"governed_answer_{event_type}",
                "type": event_type,
                "source": "governed_answer_composer_node",
                **payload,
            }
        )
    except Exception:  # noqa: BLE001
        return


def _governed_answer_composer_required(context: GovernedAnswerContext | None) -> bool:
    """Return True when a governed user-visible answer should be LLM-written.

    The output-contract node still owns the deterministic technical basis. The
    visible chat surface, however, should not expose that basis verbatim in
    production because it reads like a template. When the governed composer is
    enabled, every governed response class gets one controlled LLM writing pass.
    """

    return context is not None


async def governed_answer_composer_node(state: GraphState) -> GraphState:
    """Optionally compose natural governed answer_markdown after output_contract.

    Text-only node: it never writes governed technical truth, deltas, risks,
    readiness, RFQ state, matching, or cockpit projections. The deterministic
    reply remains the guarded basis and emergency fallback only.
    """

    fallback_reply = str(state.output_reply or "").strip()
    existing_source = str(state.output_answer_markdown_source or "").strip()
    existing_answer = str(state.output_answer_markdown or "").strip()
    if existing_source in {"deterministic_reply", "governed_composer", "composer_fallback"} and existing_answer:
        return state

    context: GovernedAnswerContext | None = None
    try:
        context = GovernedAnswerContext.model_validate(state.governed_answer_context or {})
    except Exception:  # noqa: BLE001
        context = None

    if not is_governed_answer_composer_enabled():
        fallback_answer = (
            render_governed_contextual_fallback(context, fallback_reply)
            if should_render_governed_contextual_fallback(context, fallback_reply)
            else fallback_reply
        )
        return state.model_copy(
            update={
                "output_answer_markdown": fallback_answer,
                "output_answer_markdown_source": (
                    "composer_fallback"
                    if fallback_answer != fallback_reply
                    else "deterministic_reply"
                ),
                "governed_answer_prompt_trace": {},
                "governed_answer_composer_error": "",
            }
        )

    if context is not None and not _governed_answer_composer_required(context):
        fallback_answer = (
            render_governed_contextual_fallback(context, fallback_reply)
            if should_render_governed_contextual_fallback(context, fallback_reply)
            else fallback_reply
        )
        return state.model_copy(
            update={
                "output_answer_markdown": fallback_answer,
                "output_answer_markdown_source": (
                    "composer_fallback"
                    if fallback_answer != fallback_reply
                    else "deterministic_reply"
                ),
                "governed_answer_prompt_trace": {},
                "governed_answer_composer_error": "",
            }
        )

    try:
        if context is None:
            context = GovernedAnswerContext.model_validate(state.governed_answer_context or {})
        composer_basis_reply = render_governed_contextual_fallback(context, fallback_reply)
        if not str(composer_basis_reply or "").strip():
            composer_basis_reply = fallback_reply
        composer_input = GovernedAnswerComposerInput(
            context=context,
            deterministic_reply=composer_basis_reply,
        )
        composer = GovernedAnswerComposer()
        writer = (
            _get_stream_writer_or_none()
            if getattr(state, "stream_visible_answer_composer", False)
            else None
        )
        prompt_trace: dict[str, Any] = {}
        if writer is not None:
            final_answer = ""
            async for event in composer.stream(composer_input):
                if event.event_type == "chunk":
                    _emit_composer_stream_event(writer, "text_chunk", text=event.text)
                    continue
                if event.event_type == "reset":
                    _emit_composer_stream_event(writer, "text_reset")
                    continue
                if event.event_type == "final" and event.output is not None:
                    final_answer = event.output.answer_markdown
                    prompt_trace = (
                        event.output.prompt_trace.model_dump(mode="json")
                        if event.output.prompt_trace
                        else {}
                    )
                    _emit_composer_stream_event(
                        writer,
                        "answer_final",
                        answer_markdown_source="governed_composer",
                    )
            result_answer = final_answer
        else:
            result = await composer.compose(composer_input)
            result_answer = result.answer_markdown
            prompt_trace = result.prompt_trace.model_dump(mode="json") if result.prompt_trace else {}
        return state.model_copy(
            update={
                "output_answer_markdown": result_answer,
                "output_answer_markdown_source": "governed_composer",
                "governed_answer_prompt_trace": prompt_trace,
                "governed_answer_composer_error": "",
            }
        )
    except Exception as exc:  # noqa: BLE001
        reason = safe_governed_answer_composer_error_reason(exc)
        log.warning("[governed_answer_composer] fallback reason=%s", reason)
        fallback_answer = (
            render_governed_contextual_fallback(context, fallback_reply)
            if context is not None
            else fallback_reply
        )
        return state.model_copy(
            update={
                "output_answer_markdown": fallback_answer,
                "output_answer_markdown_source": "composer_fallback",
                "governed_answer_prompt_trace": {},
                "governed_answer_composer_error": reason,
            }
        )
