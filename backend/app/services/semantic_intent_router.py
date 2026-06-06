from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agent.prompts import prompts
from app.domain.pre_gate_classification import PreGateClassification
from app.llm.factory import get_async_llm
from app.observability.langsmith import traceable
from app.services.openai_payload import use_responses_api
from app.services.pre_gate_classifier import ClassificationResult

log = logging.getLogger(__name__)

SemanticIntent = Literal[
    "smalltalk",
    "meta_question",
    "knowledge_explain",
    "knowledge_followup",
    "knowledge_compare",
    "governed_case_intake",
    "blocked",
    "recovery",
    "unclear",
]

_KNOWLEDGE_INTENTS = {
    "knowledge_explain",
    "knowledge_followup",
    "knowledge_compare",
}
_OVERRIDE_THRESHOLD = 0.74

_CONCRETE_CASE_FACT_RE = re.compile(
    r"\b(?:ich\s+habe|wir\s+haben|bei\s+uns|bei\s+meiner\s+anlage|"
    r"in\s+unserer\s+anwendung|meine[rmn]?\s+anwendung|unsere[rmn]?\s+anwendung)\b"
    r"|\b(?:brauche|ben[oö]tige|suche)\s+(?:eine\s+)?"
    r"(?:dichtung|dichtring|dichtungsl[oö]sung|seal|rwdr|o[- ]?ring)\b"
    r"|\b(?:dichtungssituation|dichtungsfall|dichtungsl[oö]sung|dichtstelle)\b"
    r"|\b(?:medium|fluid)\s*(?:ist|=)\b"
    r"|\b\d+(?:[.,]\d+)?\s*(?:mm|bar|barg|bara|psi|°?\s*[cCfF]|grad|rpm|u\.?/?min|m/s)\b"
    r"|\b(?:rotierende?\s+welle|welle|pumpe|getriebe|r[üu]hrwerk|kolben|flansch)\b.*"
    r"\b(?:dichtung|dichtstelle|seal|medium|[oö]l|bar|grad|rpm|mm)\b",
    re.IGNORECASE | re.UNICODE,
)
_BOUNDARY_CANDIDATE_RE = re.compile(
    r"\b(?:dar[uü]ber|dazu|damit|das|die\s+beiden|beide|erz[aä]hl|erzaehl|"
    r"info|infos|informationen|was\s+kannst\s+du|was\s+wei[ßs]t\s+du|"
    r"vergleich|vergleiche|unterschied|besser|schlechter|werkstoff|material|"
    r"ptfe|fkm|ffkm|epdm|nbr|hnbr|pom|peek|pa|tpu|vmq|silikon)\b",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True, slots=True)
class SemanticIntentRouterDecision:
    original_classification: PreGateClassification
    classification: PreGateClassification
    confidence: float
    intent: SemanticIntent
    reason: str
    applied: bool = False
    case_facts_present: bool = False
    materials: tuple[str, ...] = field(default_factory=tuple)
    compared_entities: tuple[str, ...] = field(default_factory=tuple)
    needs_history_resolution: bool = False
    model: str | None = None
    source: str = "semantic_intent_router"

    def classification_result(
        self, deterministic: ClassificationResult
    ) -> ClassificationResult:
        if not self.applied:
            return deterministic
        return ClassificationResult(
            classification=self.classification,
            confidence=self.confidence,
            reasoning=f"semantic_intent_router:{self.intent}:{deterministic.reasoning}",
            escalate_to_graph=self.classification
            in {PreGateClassification.DOMAIN_INQUIRY, PreGateClassification.RECOVERY},
        )

    def as_trace(self) -> dict[str, Any]:
        return {
            "semantic_pre_gate_applied": self.applied,
            "semantic_pre_gate_source": self.source,
            "semantic_pre_gate_original": self.original_classification.value,
            "semantic_pre_gate_classification": self.classification.value,
            "semantic_pre_gate_intent": self.intent,
            "semantic_pre_gate_confidence": round(float(self.confidence), 3),
            "semantic_pre_gate_case_facts_present": self.case_facts_present,
            "semantic_pre_gate_materials": list(self.materials),
            "semantic_pre_gate_compared_entities": list(self.compared_entities),
            "semantic_pre_gate_needs_history_resolution": self.needs_history_resolution,
            "semantic_pre_gate_model": self.model,
            "semantic_pre_gate_reason": self.reason[:240],
        }


def semantic_intent_router_enabled() -> bool:
    return os.environ.get("SEALAI_ENABLE_SEMANTIC_INTENT_ROUTER", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def semantic_pre_gate_candidate(
    message: str,
    deterministic: ClassificationResult,
) -> bool:
    if not semantic_intent_router_enabled():
        return False
    if deterministic.classification in {
        PreGateClassification.BLOCKED,
        PreGateClassification.RECOVERY,
    }:
        return False
    if _hard_case_facts_present(message):
        return False
    if deterministic.classification is PreGateClassification.DOMAIN_INQUIRY:
        return True
    if deterministic.classification is PreGateClassification.META_QUESTION:
        return bool(_BOUNDARY_CANDIDATE_RE.search(str(message or "")))
    if deterministic.classification is PreGateClassification.GREETING:
        return bool(_BOUNDARY_CANDIDATE_RE.search(str(message or "")))
    return False


@traceable(name="sealai.semantic_intent_router", run_type="chain")
def _router_timeout_s() -> float:
    """Stage B (Rang 3 / W1): cap the router LLM; deterministic fallback on timeout."""
    try:
        from app.core.config import settings  # noqa: PLC0415

        return float(settings.semantic_router_timeout_s)
    except Exception:  # noqa: BLE001
        return 10.0


async def refine_pre_gate_classification(
    *,
    message: str,
    deterministic: ClassificationResult,
    recent_history: tuple[Any, ...] = (),
) -> SemanticIntentRouterDecision:
    if not semantic_pre_gate_candidate(message, deterministic):
        return _unchanged(deterministic, reason="not_a_semantic_router_candidate")

    try:
        client, model = get_async_llm("semantic_intent_router")
        payload = _router_payload(
            message=message,
            deterministic=deterministic,
            recent_history=recent_history,
        )
        # Stage B (Rang 3 / W1): bound the unbounded router-LLM tail. A timeout
        # raises TimeoutError, caught by the except below → safe deterministic
        # fallback (the audit's first_progress tail driver, §1.1/§2.5).
        raw = await asyncio.wait_for(
            _call_structured_router(client=client, model=model, payload=payload),
            timeout=_router_timeout_s(),
        )
        decision = _decision_from_payload(
            raw,
            deterministic=deterministic,
            model=model,
            hard_case_facts=_hard_case_facts_present(message),
        )
        return decision
    except Exception as exc:  # noqa: BLE001
        log.info("[semantic_intent_router] unavailable (%s)", type(exc).__name__)
        return _unchanged(
            deterministic, reason=f"semantic_router_unavailable:{type(exc).__name__}"
        )


def _decision_from_payload(
    payload: dict[str, Any],
    *,
    deterministic: ClassificationResult,
    model: str,
    hard_case_facts: bool,
) -> SemanticIntentRouterDecision:
    intent = _safe_intent(payload.get("intent"))
    confidence = _safe_confidence(payload.get("confidence"))
    llm_case_facts = bool(payload.get("case_facts_present"))
    materials = _safe_str_tuple(payload.get("materials"))
    compared_entities = _safe_str_tuple(payload.get("compared_entities"))
    needs_history_resolution = bool(payload.get("needs_history_resolution"))
    reason = str(payload.get("reason") or "").strip()[:500]

    classification = _classification_for_intent(intent, deterministic)
    # D (T3.1): case_facts_present is the fact-presence signal and must be honored
    # independent of the LLM intent label. Previously it was ANDed with
    # intent == "governed_case_intake", so a true case_facts_present was discarded
    # whenever the LLM picked a non-intake label -> the facts fell to the knowledge
    # route. AC9 is preserved: with no facts present this stays False (knowledge).
    case_facts = hard_case_facts or llm_case_facts
    applied = False

    if confidence >= _OVERRIDE_THRESHOLD:
        if case_facts:
            classification = PreGateClassification.DOMAIN_INQUIRY
            applied = deterministic.classification is not classification
        elif intent in _KNOWLEDGE_INTENTS:
            classification = PreGateClassification.KNOWLEDGE_QUERY
            applied = deterministic.classification is not classification
        elif intent == "smalltalk":
            classification = PreGateClassification.GREETING
            applied = deterministic.classification is not classification
        elif intent == "meta_question":
            classification = (
                deterministic.classification
                if materials
                else PreGateClassification.META_QUESTION
            )
            applied = deterministic.classification is not classification
        elif intent == "blocked":
            classification = PreGateClassification.BLOCKED
            applied = deterministic.classification is not classification
        elif intent == "recovery":
            classification = PreGateClassification.RECOVERY
            applied = deterministic.classification is not classification
        elif intent == "governed_case_intake":
            classification = PreGateClassification.DOMAIN_INQUIRY
            applied = deterministic.classification is not classification

    return SemanticIntentRouterDecision(
        original_classification=deterministic.classification,
        classification=classification,
        confidence=confidence,
        intent=intent,
        reason=reason or "semantic_router_result",
        applied=applied,
        case_facts_present=case_facts,
        materials=materials,
        compared_entities=compared_entities,
        needs_history_resolution=needs_history_resolution,
        model=model,
    )


async def _call_structured_router(
    *,
    client: Any,
    model: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    system = prompts.render("communication/semantic_pre_gate_router.j2", {})
    user_payload = json.dumps(payload, ensure_ascii=False)
    schema = _router_schema()
    if use_responses_api(model):
        try:
            response_or_awaitable = client.responses.create(
                model=model,
                instructions=system,
                input=[
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_payload}],
                    }
                ],
                max_output_tokens=320,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "sealai_semantic_intent_router",
                        "strict": True,
                        "schema": schema,
                    }
                },
            )
            response = (
                await response_or_awaitable
                if inspect.isawaitable(response_or_awaitable)
                else response_or_awaitable
            )
            return json.loads(_extract_responses_text(response) or "{}")
        except Exception as exc:
            if type(exc).__name__ not in {"BadRequestError", "TypeError"}:
                raise
            log.info(
                "[semantic_intent_router] responses schema unsupported; retrying plain JSON"
            )

        response_or_awaitable = client.responses.create(
            model=model,
            instructions=f"{system}\nReturn one valid JSON object only.",
            input=[
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_payload}],
                }
            ],
            max_output_tokens=320,
        )
        response = (
            await response_or_awaitable
            if inspect.isawaitable(response_or_awaitable)
            else response_or_awaitable
        )
        return json.loads(_extract_responses_text(response) or "{}")

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_payload},
        ],
        temperature=0,
        max_tokens=320,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "sealai_semantic_intent_router",
                "strict": True,
                "schema": schema,
            },
        },
    )
    return json.loads(str(response.choices[0].message.content or "{}"))


def _router_payload(
    *,
    message: str,
    deterministic: ClassificationResult,
    recent_history: tuple[Any, ...],
) -> dict[str, Any]:
    return {
        "latest_user_message": str(message or ""),
        "deterministic_pre_gate": {
            "classification": deterministic.classification.value,
            "confidence": deterministic.confidence,
            "reasoning": deterministic.reasoning,
            "escalate_to_graph": deterministic.escalate_to_graph,
        },
        "hard_case_facts_present": _hard_case_facts_present(message),
        "recent_history": _compact_history(recent_history),
    }


def _compact_history(recent_history: tuple[Any, ...]) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for turn in recent_history[-8:]:
        role = _turn_value(turn, "role")
        content = _turn_value(turn, "content")
        if role not in {"user", "assistant"} or not content:
            continue
        turns.append({"role": role, "content": content[:700]})
    return turns


def _turn_value(turn: Any, key: str) -> str:
    if isinstance(turn, dict):
        return str(turn.get(key) or "").strip()
    return str(getattr(turn, key, "") or "").strip()


def _hard_case_facts_present(message: str) -> bool:
    return bool(_CONCRETE_CASE_FACT_RE.search(str(message or "")))


def _classification_for_intent(
    intent: SemanticIntent,
    deterministic: ClassificationResult,
) -> PreGateClassification:
    if intent in _KNOWLEDGE_INTENTS:
        return PreGateClassification.KNOWLEDGE_QUERY
    if intent == "smalltalk":
        return PreGateClassification.GREETING
    if intent == "meta_question":
        return PreGateClassification.META_QUESTION
    if intent == "blocked":
        return PreGateClassification.BLOCKED
    if intent == "recovery":
        return PreGateClassification.RECOVERY
    if intent == "governed_case_intake":
        return PreGateClassification.DOMAIN_INQUIRY
    return deterministic.classification


def _safe_intent(value: Any) -> SemanticIntent:
    intent = str(value or "unclear").strip()
    valid = {
        "smalltalk",
        "meta_question",
        "knowledge_explain",
        "knowledge_followup",
        "knowledge_compare",
        "governed_case_intake",
        "blocked",
        "recovery",
        "unclear",
    }
    return intent if intent in valid else "unclear"  # type: ignore[return-value]


def _safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _safe_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    seen: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.append(text[:80])
    return tuple(seen)


def _unchanged(
    deterministic: ClassificationResult,
    *,
    reason: str,
) -> SemanticIntentRouterDecision:
    return SemanticIntentRouterDecision(
        original_classification=deterministic.classification,
        classification=deterministic.classification,
        confidence=deterministic.confidence,
        intent="unclear",
        reason=reason,
        applied=False,
        case_facts_present=False,
    )


def _extract_responses_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            content_text = getattr(content, "text", None)
            if isinstance(content_text, str):
                chunks.append(content_text)
            elif isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks).strip()


def _router_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "smalltalk",
                    "meta_question",
                    "knowledge_explain",
                    "knowledge_followup",
                    "knowledge_compare",
                    "governed_case_intake",
                    "blocked",
                    "recovery",
                    "unclear",
                ],
            },
            "confidence": {"type": "number"},
            "case_facts_present": {"type": "boolean"},
            "materials": {"type": "array", "items": {"type": "string"}},
            "compared_entities": {"type": "array", "items": {"type": "string"}},
            "needs_history_resolution": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": [
            "intent",
            "confidence",
            "case_facts_present",
            "materials",
            "compared_entities",
            "needs_history_resolution",
            "reason",
        ],
    }
