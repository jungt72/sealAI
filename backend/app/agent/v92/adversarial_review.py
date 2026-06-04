"""Structured V9.2 adversarial review.

MVP note: this is deterministic and prompt-registry-ready. It does not write a
second assistant answer. It only emits a typed verdict over a draft.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.prompts import prompts
from app.agent.v92.contracts import AdversarialReviewVerdict, FinalAnswerContext
from app.agent.v92.prompt_audit import build_prompt_trace
from app.llm.factory import get_async_llm
from app.llm.registry import get_registry_default_model_for_role


ADVERSARIAL_REVIEW_PROMPT_VERSION = "sealai_v92_adversarial_reviewer_v1"
_MODEL_FALLBACK_ERROR_NAMES = {"BadRequestError", "NotFoundError"}

_SUITABILITY_RE = re.compile(
    r"\b(?:ist|sind)\s+(?:sicher\s+|final\s+|gut\s+)?geeignet\b",
    re.IGNORECASE | re.UNICODE,
)
_FINALITY_RE = re.compile(
    r"\b(?:freigegeben|zugelassen|final\s+freigegeben|technisch\s+validiert|garantiert)\b",
    re.IGNORECASE | re.UNICODE,
)
_CONFORMITY_RE = re.compile(
    r"\b(?:konform|zertifiziert|normkonform|fda[-\s]?konform|atex[-\s]?zertifiziert)\b",
    re.IGNORECASE | re.UNICODE,
)
_ROOT_CAUSE_RE = re.compile(
    r"\b(?:die\s+ursache\s+ist|root\s+cause\s+is|eindeutige\s+ursache)\b",
    re.IGNORECASE | re.UNICODE,
)
_COMPOUND_PRODUCT_RE = re.compile(
    r"\b(?:compound|mischung|artikel|produkt)\b.{0,80}\b(?:geeignet|freigegeben|passt|zugelassen)\b",
    re.IGNORECASE | re.UNICODE,
)


class AdversarialReviewError(ValueError):
    pass


def review_answer_draft(
    draft: str,
    context: FinalAnswerContext,
) -> AdversarialReviewVerdict:
    text = str(draft or "")
    forbidden_claims: list[str] = []
    unsupported_claims: list[str] = []
    missing_context: list[str] = []
    stale_concerns: list[str] = []
    calculation_concerns: list[str] = []
    evidence_concerns: list[str] = []
    standards_concerns: list[str] = []
    downgrade: list[str] = []
    revision_instructions: list[str] = []
    warnings: list[str] = []

    if _FINALITY_RE.search(text):
        forbidden_claims.append("final_release_or_approval_claim")
        revision_instructions.append("Remove release, approval and guarantee language.")
    if _SUITABILITY_RE.search(text) and context.allowed_claim_level != "L6_expert_approved":
        forbidden_claims.append("suitability_claim_without_expert_scope")
        downgrade.append("suitability_language")
        revision_instructions.append("Downgrade suitability to screening or hypothesis language.")
    if _CONFORMITY_RE.search(text):
        forbidden_claims.append("standards_or_conformity_claim")
        standards_concerns.append("Conformity wording requires licensed rule evidence or expert review.")
        revision_instructions.append("Replace conformity wording with standards-reference boundary language.")
    if _ROOT_CAUSE_RE.search(text):
        forbidden_claims.append("definitive_root_cause_claim")
        downgrade.append("root_cause_language")
        revision_instructions.append("Downgrade root cause language to hypothesis/indicator language.")
    if _COMPOUND_PRODUCT_RE.search(text):
        has_compound_evidence = bool(context.compound_candidates or context.product_candidates)
        if not has_compound_evidence:
            unsupported_claims.append("compound_or_product_claim_without_layer_evidence")
            revision_instructions.append("Do not derive compound/product claims from material-family context.")

    if context.stale_items:
        stale_concerns.append("stale_items_present")
        warnings.append("Some calculations or derived outputs are stale and must not be used as current basis.")
    if context.review_required:
        missing_context.extend(context.human_review_reasons or ["human_review_required"])
        warnings.append("Expert review is required before release-level claims.")
    if context.evidence_summary.get("unresolved_gaps"):
        evidence_concerns.append("unresolved_evidence_gaps")
    for result in context.calculation_results:
        status = str(result.get("status") or result.get("validity_status") or "")
        if status in {"stale", "input_missing", "insufficient_data", "blocked"}:
            calculation_concerns.append(
                str(result.get("calculation_id") or result.get("calculator") or status)
            )

    if forbidden_claims:
        decision = "revise"
        severity = "high"
    elif unsupported_claims or stale_concerns or standards_concerns:
        decision = "revise"
        severity = "medium"
    elif missing_context:
        decision = "human_review"
        severity = "medium"
    else:
        decision = "pass"
        severity = "none"

    summary = "Keine fachliche Gegenpruefung hat blockierende Punkte gefunden."
    if decision != "pass":
        summary = (
            "Gegenpruefung: Die Antwort braucht Claim-Downgrade, sichtbare Grenzen "
            "oder Review, bevor sie als technische Empfehlung erscheinen darf."
        )

    return AdversarialReviewVerdict(
        decision=decision,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        unsupported_claims=unsupported_claims,
        forbidden_claims=forbidden_claims,
        missing_context=missing_context,
        stale_state_concerns=stale_concerns,
        calculation_concerns=calculation_concerns,
        evidence_concerns=evidence_concerns,
        standards_concerns=standards_concerns,
        risk_warnings_to_add=warnings,
        claims_to_downgrade=downgrade,
        required_revision_instructions=revision_instructions,
        user_visible_challenge_summary=summary,
    )


def build_adversarial_review_messages(
    *,
    draft: str,
    context: FinalAnswerContext,
) -> list[dict[str, str]]:
    system_prompt = prompts.render(
        "governed/adversarial_reviewer.j2",
        {
            "prompt_version": ADVERSARIAL_REVIEW_PROMPT_VERSION,
            "trace_id": context.turn_id,
        },
    )
    payload = {
        "draft": str(draft or ""),
        "final_answer_context": context.model_dump(mode="json"),
        "required_output_schema": "AdversarialReviewVerdict",
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True, default=str)},
    ]


def parse_adversarial_review_output(raw_content: Any) -> AdversarialReviewVerdict:
    try:
        payload = json.loads(str(raw_content or "{}"))
    except json.JSONDecodeError as exc:
        raise AdversarialReviewError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise AdversarialReviewError("invalid_payload")
    try:
        return AdversarialReviewVerdict.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        raise AdversarialReviewError("invalid_adversarial_review_schema") from exc


async def _create_completion_with_registry_fallback(
    *,
    client: Any,
    model: str,
    role: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> Any:
    try:
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # noqa: BLE001
        fallback_model = get_registry_default_model_for_role(role)
        if model != fallback_model and exc.__class__.__name__ in _MODEL_FALLBACK_ERROR_NAMES:
            return await client.chat.completions.create(
                model=fallback_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
        raise


class LLMAdversarialReviewer:
    """LLM-backed reviewer that emits only a structured verdict.

    The deterministic reviewer remains the fallback and the final guard remains
    the hard enforcement layer.
    """

    def __init__(self, *, temperature: float = 0.0, max_tokens: int = 900) -> None:
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def review(self, draft: str, context: FinalAnswerContext) -> AdversarialReviewVerdict:
        messages = build_adversarial_review_messages(draft=draft, context=context)
        client, model = get_async_llm("critique")
        response = await _create_completion_with_registry_fallback(
            client=client,
            model=model,
            role="critique",
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        raw_content = response.choices[0].message.content
        verdict = parse_adversarial_review_output(raw_content)
        trace = build_prompt_trace(
            prompt_template_id="governed/adversarial_reviewer.j2",
            prompt_template_version=ADVERSARIAL_REVIEW_PROMPT_VERSION,
            messages=messages,
            input_schema_version="FinalAnswerContext.v1+draft",
            output_schema_version="AdversarialReviewVerdict.v1",
            model_role="critique",
            case_revision=context.case_revision,
            trace_id=context.turn_id,
        )
        verdict.prompt_trace = trace
        return verdict


async def review_answer_draft_with_llm_fallback(
    draft: str,
    context: FinalAnswerContext,
    *,
    reviewer: LLMAdversarialReviewer | None = None,
) -> AdversarialReviewVerdict:
    try:
        return await (reviewer or LLMAdversarialReviewer()).review(draft, context)
    except Exception:  # noqa: BLE001
        return review_answer_draft(draft, context)


__all__ = [
    "ADVERSARIAL_REVIEW_PROMPT_VERSION",
    "AdversarialReviewError",
    "LLMAdversarialReviewer",
    "build_adversarial_review_messages",
    "parse_adversarial_review_output",
    "review_answer_draft",
    "review_answer_draft_with_llm_fallback",
]
