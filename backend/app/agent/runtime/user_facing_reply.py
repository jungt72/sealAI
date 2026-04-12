from __future__ import annotations

import logging
import os
from typing import Any, Optional, TypedDict

import openai

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


class UserFacingReplyPayload(TypedDict):
    reply: str | None
    structured_state: Optional[dict[str, Any]]
    policy_path: Optional[str]
    run_meta: Optional[dict[str, Any]]
    response_class: str


async def collect_governed_visible_reply(
    *,
    response_class: str,
    turn_context: TurnContextContract | None,
    fallback_text: str,
    allowed_surface_claims: GovernedAllowedSurfaceClaims | list[str] | None = None,
    applicable_norms: list[str] | None = None,
    requirement_class_id: str | None = None,
    evidence_summary_lines: list[str] | None = None,
    material_candidates: list[str] | None = None,
) -> str:
    """Central governed visible-reply anchor for the user-facing layer."""
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
        "structured_state": structured_state,
        "policy_path": policy_path,
        "run_meta": run_meta,
        "response_class": resolved_response_class,
    }
