"""Chat-style Jinja2 template registry (Blueprint §10.3 / §10.4 / §18).

Patch 2 scope — additive only:

* A small, versioned registry that maps each ``ChatReply.style`` (Patch-1
  contract) to a Jinja2 template plus metadata (``template_id``,
  ``allowed_modes``, ``max_questions``, ``disclaimer_policy``,
  ``forbidden_phrases``) per Blueprint §10.4.
* Rendering via the **existing** :class:`app.agent.prompts.PromptRegistry`
  class (the canonical Jinja seam), pointed at ``app/agent/templates/``. No
  second template engine and no change to the shared ``prompts`` singleton.
* The No-Go phrase guard (§18.3 / §31) runs on the rendered markdown.
* ``disclaimer_mode`` is derived from the template's ``disclaimer_policy`` so
  normal case turns suppress the per-turn liability disclaimer (§22.2), while
  boundary turns keep explicit boundary wording.

Runtime wiring into the live composer/dispatch is intentionally out of scope
for this patch; the registry is a tested, additive capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.agent.prompts import PromptRegistry
from app.agent.templates.no_go_guard import (
    FORBIDDEN_NORMAL_TURN_PHRASES,
    VISUAL_FORBIDDEN_PHRASES,
    assert_no_no_go,
)
from app.agent.v92.contracts import ChatReply, ChatReplyStyle, DisclaimerMode

TEMPLATES_DIR = Path(__file__).resolve().parent

# Reuse the canonical PromptRegistry class against the templates/ root. Same
# Jinja configuration (StrictUndefined, trim/lstrip blocks) as all other agent
# prompts — not a parallel engine.
_template_env = PromptRegistry(prompts_dir=TEMPLATES_DIR)


@dataclass(frozen=True)
class ChatTemplateMeta:
    """Metadata contract for a chat-style template (Blueprint §10.4)."""

    template_id: str
    path: str
    style: ChatReplyStyle
    allowed_modes: tuple[str, ...]
    max_questions: int
    disclaimer_policy: DisclaimerMode
    forbidden_phrases: tuple[str, ...]
    required_fields: tuple[str, ...]
    output_type: str = "markdown"
    # Whether the affirmative final-release patterns also apply (always True for
    # the V1.6 chat styles; refusals are not matched by those patterns).
    block_final_release: bool = True


CHAT_TEMPLATE_REGISTRY: dict[ChatReplyStyle, ChatTemplateMeta] = {
    "senior_engineer_short": ChatTemplateMeta(
        template_id="chat.senior_engineer_short.v1",
        path="chat/senior_engineer_short.j2",
        style="senior_engineer_short",
        allowed_modes=(
            "case_building",
            "leakage_diagnosis",
            "pending_slot_answer",
            "unknown_seal_scoping",
        ),
        max_questions=1,
        disclaimer_policy="suppress_normal_turn",
        forbidden_phrases=FORBIDDEN_NORMAL_TURN_PHRASES,
        required_fields=("opening", "technical_hint", "primary_question"),
    ),
    "smalltalk_fast": ChatTemplateMeta(
        template_id="chat.smalltalk_fast.v1",
        path="chat/smalltalk_fast.j2",
        style="smalltalk_fast",
        allowed_modes=("smalltalk", "ui_help"),
        max_questions=1,
        disclaimer_policy="suppress_normal_turn",
        forbidden_phrases=FORBIDDEN_NORMAL_TURN_PHRASES,
        required_fields=("greeting", "invitation"),
    ),
    "mobile_triage": ChatTemplateMeta(
        template_id="chat.mobile_triage.v1",
        path="chat/mobile_triage.j2",
        style="mobile_triage",
        allowed_modes=("mobile_leakage_triage",),
        max_questions=1,
        disclaimer_policy="suppress_normal_turn",
        forbidden_phrases=FORBIDDEN_NORMAL_TURN_PHRASES,
        required_fields=("immediate_context", "primary_question", "action_chips"),
    ),
    "visual_low_confidence_guidance": ChatTemplateMeta(
        template_id="chat.visual_low_confidence_guidance.v1",
        path="chat/visual_low_confidence_guidance.j2",
        style="visual_low_confidence_guidance",
        allowed_modes=("visual_low_confidence_guidance",),
        max_questions=1,
        disclaimer_policy="suppress_normal_turn",
        forbidden_phrases=FORBIDDEN_NORMAL_TURN_PHRASES + VISUAL_FORBIDDEN_PHRASES,
        required_fields=("uncertainty_statement", "useful_next_step", "action_chips"),
    ),
    "blocked_boundary": ChatTemplateMeta(
        template_id="chat.blocked_boundary.v1",
        path="chat/blocked_boundary.j2",
        style="blocked_boundary",
        allowed_modes=("blocked_boundary",),
        max_questions=1,
        # Boundary turns keep explicit boundary wording (§22.2).
        disclaimer_policy="explicit_boundary_required",
        # Boundary turns legitimately refuse release; no structural-phrase ban.
        forbidden_phrases=(),
        required_fields=("boundary_statement", "constructive_alternative", "offer_question"),
    ),
}


def render_template(path: str, context: Mapping[str, Any]) -> str:
    """Render any template in the V1.6 family via the shared registry env.

    Lets non-chat documents (e.g. the RFQ one-pager) reuse the same Jinja seam
    as the chat styles, instead of spinning up a parallel engine.
    """
    return _template_env.render(path, dict(context))


def get_chat_template_meta(style: ChatReplyStyle) -> ChatTemplateMeta:
    try:
        return CHAT_TEMPLATE_REGISTRY[style]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"unknown chat style: {style!r}") from exc


def render_chat_reply(
    style: ChatReplyStyle,
    fields: Mapping[str, Any] | None = None,
    *,
    primary_question: dict[str, Any] | None = None,
    action_chips: Sequence[str] | None = None,
    enforce_guard: bool = True,
) -> ChatReply:
    """Render a :class:`ChatReply` for ``style`` from its registered template.

    ``fields`` provides the template variables; any declared ``required_fields``
    not supplied default to an empty string so StrictUndefined is satisfied. The
    rendered markdown is passed through the No-Go phrase guard (raising on a
    violation when ``enforce_guard`` is True), and ``disclaimer_mode`` is taken
    from the template's ``disclaimer_policy``.
    """
    meta = get_chat_template_meta(style)
    supplied = dict(fields or {})

    context: dict[str, Any] = {key: supplied.get(key, "") for key in meta.required_fields}
    if "action_chips" in meta.required_fields:
        context["action_chips"] = list(action_chips or supplied.get("action_chips") or [])

    markdown = _template_env.render(meta.path, context).strip()

    if enforce_guard:
        assert_no_no_go(
            markdown,
            meta.forbidden_phrases,
            include_final_release=meta.block_final_release,
        )

    return ChatReply(
        style=meta.style,
        markdown=markdown,
        primary_question=primary_question,
        disclaimer_mode=meta.disclaimer_policy,
        template_id=meta.template_id,
    )
