from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional, TypedDict

from app.agent.communication.llm_service import OpenAIHumanCommunicationLLMService
from app.agent.communication.orchestrator import ConversationOrchestrator
from app.agent.runtime.reply_composition import (
    GovernedAllowedSurfaceClaims,
    build_governed_render_prompt,
    guard_governed_rendered_text,
)
from app.agent.runtime.outward_names import normalize_outward_response_class, normalize_outward_status
from app.agent.runtime.response_renderer import render_chunk, render_response
from app.agent.runtime.surface_claims import get_surface_claims_spec
from app.agent.state.models import TurnContextContract
from prompts.builder import PromptBuilder

_log = logging.getLogger(__name__)
_prompt_builder = PromptBuilder()
_GOVERNED_REFORMULATE_MODEL = os.environ.get("SEALAI_CONVERSATION_MODEL", "gpt-4o-mini")
_UNSAFE_USER_INSTRUCTION_RE = re.compile(
    r"\b(ignore|ignoriere|vergiss)\b.*\b(rule|rules|regeln|system|developer|sicherheits)\b",
    re.IGNORECASE | re.UNICODE,
)
_FORCED_TECHNICAL_CLAIM_RE = re.compile(
    r"\b(sag(?:e)?|behaupte|bestaetige|bestätige)\b.*\b(geeignet|freigegeben|garantiert|passend|sicher)\b",
    re.IGNORECASE | re.UNICODE,
)


class UserFacingReplyPayload(TypedDict):
    reply: str | None
    answer_markdown: str | None
    structured_state: Optional[dict[str, Any]]
    policy_path: Optional[str]
    run_meta: Optional[dict[str, Any]]
    response_class: str


async def collect_governed_visible_reply(
    *,
    response_class: str,
    turn_context: TurnContextContract | None,
    fallback_text: str,
    latest_user_message: str | None = None,
    allowed_surface_claims: GovernedAllowedSurfaceClaims | list[str] | None = None,
    applicable_norms: list[str] | None = None,
    requirement_class_id: str | None = None,
    evidence_summary_lines: list[str] | None = None,
    material_candidates: list[str] | None = None,
) -> str:
    """Central governed visible-reply anchor for the user-facing layer.

    C2 decision (2026-04-12): Style-Pass retained.
    Role: pure reformulation — no content authority.
    - fallback_text (= output_reply after C1) is the SSOT for content.
    - LLM reformulates into natural German, temp=0.2, max_tokens=400.
    - guard_governed_rendered_text() strips any output that violates
      the surface-claims whitelist and falls back to fallback_text.
    - On any LLM error: returns fallback_text directly.
    Adding or removing content is not permitted — only style.
    """
    guarded_user_instruction = _guard_unsafe_user_instruction(
        latest_user_message=latest_user_message,
        turn_context=turn_context,
    )
    if guarded_user_instruction is not None:
        return guarded_user_instruction

    claims_spec: GovernedAllowedSurfaceClaims | list[str]
    claims_spec = get_surface_claims_spec(
        response_class,
        fallback_text=fallback_text,
    )
    if isinstance(allowed_surface_claims, dict):
        claims_spec.update(
            {
                key: value
                for key, value in allowed_surface_claims.items()
                if key != "fallback_text"
            }
        )
    elif isinstance(allowed_surface_claims, list):
        claims_spec = allowed_surface_claims

    effective_fallback_text = str(
        fallback_text
        or (
            claims_spec.get("fallback_text")
            if isinstance(claims_spec, dict)
            else ""
        )
        or ""
    ).strip()
    if isinstance(claims_spec, dict):
        claims_spec["fallback_text"] = effective_fallback_text

    if os.environ.get("HUMAN_COMMUNICATION_LAYER_ENABLED", "true").lower() != "false":
        try:
            import openai  # noqa: PLC0415

            orchestrator = ConversationOrchestrator(
                llm_service=OpenAIHumanCommunicationLLMService(
                    model_name=_GOVERNED_REFORMULATE_MODEL,
                    client_factory=openai.AsyncOpenAI,
                )
            )
            result = await orchestrator.handle_governed_reply(
                response_class=response_class,
                turn_context=turn_context,
                fallback_text=effective_fallback_text,
                latest_user_message=latest_user_message,
            )
            _log.info(
                "[human_communication] turn_id=%s case_id=%s mode=%s guard=%s claims=%s model=%s",
                result.trace.turn_id,
                result.trace.case_id,
                result.trace.mode,
                result.trace.guard_result,
                ",".join(result.trace.allowed_claim_ids_used[:12]),
                result.trace.model_name,
            )
            if result.used_fallback:
                rendered_fallback = render_response(result.assistant_message, path="GOVERNED")
                return str(rendered_fallback.text or result.assistant_message or effective_fallback_text).strip()
            # The Human Communication Layer has already validated claim usage,
            # evidence refs, forbidden phrases and fallback safety. Do not route
            # successful HCL output through the legacy surface corridor again;
            # that corridor can collapse natural answers back into formular-like
            # deterministic labels.
            rendered = render_response(result.assistant_message, path="GOVERNED")
            return str(rendered.text or effective_fallback_text).strip()
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "[user_facing_reply] human communication layer failed (%s) — using deterministic fallback unless legacy renderer is explicitly enabled",
                exc,
            )
            if os.environ.get("SEALAI_ENABLE_LEGACY_VISIBLE_RENDERER", "false").lower() != "true":
                return effective_fallback_text

    system_prompt = _prompt_builder.conversation()
    render_prompt = build_governed_render_prompt(
        response_class=response_class,
        turn_context=turn_context,
        fallback_text=effective_fallback_text,
        allowed_surface_claims=claims_spec,
        applicable_norms=applicable_norms,
        requirement_class_id=requirement_class_id,
        evidence_summary_lines=evidence_summary_lines,
        material_candidates=material_candidates,
    )

    try:
        import openai  # noqa: PLC0415

        client = openai.AsyncOpenAI()
        accumulated_chunks: list[str] = []
        stream = await client.chat.completions.create(
            model=_GOVERNED_REFORMULATE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": render_prompt},
            ],
            stream=True,
            temperature=0.2,
            max_tokens=400,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            text = getattr(delta, "content", None) if delta else None
            if not text:
                continue
            clean = render_chunk(text, path="GOVERNED")
            if clean:
                accumulated_chunks.append(clean)

        guarded_text = guard_governed_rendered_text(
            "".join(accumulated_chunks),
            fallback_text=effective_fallback_text,
            allowed_surface_claims=claims_spec,
        )
        rendered = render_response(guarded_text, path="GOVERNED")
        visible_reply = rendered.text or effective_fallback_text
        return str(visible_reply or "").strip()
    except Exception as exc:
        _log.warning(
            "[user_facing_reply] governed LLM render failed (%s) — using deterministic fallback",
            exc,
        )
        return effective_fallback_text


def _guard_unsafe_user_instruction(
    *,
    latest_user_message: str | None,
    turn_context: TurnContextContract | None,
) -> str | None:
    user_text = str(latest_user_message or "").strip()
    lowered = user_text.casefold()
    if not user_text:
        return None
    if not (_UNSAFE_USER_INSTRUCTION_RE.search(lowered) or _FORCED_TECHNICAL_CLAIM_RE.search(lowered)):
        return None

    next_question = str(getattr(turn_context, "primary_question", "") or "").strip()
    parts = [
        "Das kann ich so nicht seriös bestätigen.",
        "Ob ein Werkstoff, Dichtungstyp oder eine Lösung passt, prüfe ich nur gegen den aktuellen Fallstand, offene Punkte und nachvollziehbare Quellen.",
    ]
    if next_question:
        parts.append(next_question)
    else:
        parts.append("Wenn du möchtest, klären wir als Nächstes den fehlenden technischen Punkt im Fall.")
    return "\n\n".join(parts)


def derive_public_response_class(
    *,
    structured_state: Optional[dict[str, Any]],
    state_update: bool,
) -> str:
    response_class = "conversational_answer"
    output_status = normalize_outward_status((structured_state or {}).get("output_status"), default="")

    if state_update and structured_state is not None:
        return "governed_state_update"
    if structured_state is None:
        return response_class
    if output_status == "inquiry_ready":
        return "inquiry_ready"
    if output_status == "candidate_shortlist":
        return "candidate_shortlist"
    if output_status == "technical_preselection":
        return "technical_preselection"
    if output_status == "clarification_needed":
        return "structured_clarification"
    return "structured_clarification"


def assemble_user_facing_reply(
    *,
    reply: str | None,
    structured_state: Optional[dict[str, Any]] = None,
    policy_path: Optional[str] = None,
    run_meta: Optional[dict[str, Any]] = None,
    state_update: bool = False,
    response_class: str | None = None,
    fallback_text: str | None = None,
) -> UserFacingReplyPayload:
    resolved_response_class = normalize_outward_response_class(
        response_class
        or derive_public_response_class(
            structured_state=structured_state,
            state_update=state_update,
        )
    )
    guarded_reply = None if reply is None else str(reply or "")
    if guarded_reply is not None and resolved_response_class != "conversational_answer":
        claims_spec = get_surface_claims_spec(
            resolved_response_class,
            fallback_text=fallback_text,
        )
        guarded_reply = guard_governed_rendered_text(
            guarded_reply,
            fallback_text=claims_spec["fallback_text"],
            allowed_surface_claims=claims_spec,
        )
        guarded_reply = render_response(guarded_reply, path="GOVERNED").text

    return {
        "reply": guarded_reply,
        "answer_markdown": guarded_reply,
        "structured_state": structured_state,
        "policy_path": policy_path,
        "run_meta": run_meta,
        "response_class": resolved_response_class,
    }
