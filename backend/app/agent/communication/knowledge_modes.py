"""V1.6 Knowledge Contract — mode separation + mutation policy (Blueprint §8, §27.5).

This is a thin, deterministic *sub-classifier and policy* layer over the
existing knowledge routing. It does NOT introduce a second router: it refines a
turn that is already on the knowledge path into one of the seven §8 modes and
encodes the mutation rule. The single binding rule (§8.2/§27.5):

    Knowledge questions do not mutate the case unless the user supplies new
    technical facts. Only ``knowledge_case_mutating`` mutates — and then ONLY
    the supplied facts run through the existing State Gate (reusing the same
    extractor + reducers as the engineering path, consistent with Patch 5).
"""

from __future__ import annotations

import re
from typing import Literal

from app.agent.state.models import GovernedSessionState, ObservedExtraction
from app.agent.state.reducers import (
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)

KnowledgeMode = Literal[
    "knowledge_general",
    "knowledge_case_aware",
    "knowledge_case_mutating",
    "comparison_general",
    "comparison_case_aware",
    "norm_documentation_knowledge",
    "why_question_active_case",
]

# §8.2 / §27.5: only knowledge_case_mutating may mutate case state.
KNOWLEDGE_MODE_MUTATES: dict[KnowledgeMode, bool] = {
    "knowledge_general": False,
    "knowledge_case_aware": False,
    "knowledge_case_mutating": True,
    "comparison_general": False,
    "comparison_case_aware": False,
    "norm_documentation_knowledge": False,
    "why_question_active_case": False,
}

_WHY_RE = re.compile(
    r"\b(?:warum|wieso|weshalb|wozu|aus\s+welchem\s+grund)\b", re.IGNORECASE
)
_COMPARISON_RE = re.compile(
    r"\b(?:vs\.?|versus|oder|besser|schlechter|vergleich(?:e|en)?|unterschied|"
    r"gegen(?:über)?|im\s+vergleich)\b",
    re.IGNORECASE,
)
# A material/medium is only a *new fact* when explicitly asserted as used —
# merely naming it in a question ("Was ist FKM?", "NBR oder FKM?") is the
# question subject, not a stated case fact (§8.4/§8.5/§8.7).
_FACT_ASSERTION_RE = re.compile(
    r"\b(?:verwenden|verwende|nutzen|nutze|benutzen|haben|setzen?\s+\w+\s+ein|"
    r"eingesetzt|verbaut|läuft\s+mit|laeuft\s+mit|ist\s+aus|besteht\s+aus|"
    r"fahren\s+mit|im\s+einsatz)\b",
    re.IGNORECASE,
)
# Unambiguous operating measurements (keys from extract_parameters).
_OPERATING_FACT_KEYS = ("temperature_c", "pressure_bar", "diameter_mm", "speed_rpm")

# Norm / regulatory / compliance documentation tokens (§8.9).
_NORM_RE = re.compile(
    r"\b(?:wras|fda|atex|dvgw|ktw|usp\s*class|ec\s*1935|din|en\s*\d|iso\s*\d|"
    r"norm|normen|zulassung|konformit(?:ä|ae)t|compliance|richtlinie|verordnung|"
    r"trinkwasserzulassung)\b",
    re.IGNORECASE,
)


def mode_mutates(mode: str) -> bool:
    """Return whether a knowledge mode is allowed to mutate case state."""
    return KNOWLEDGE_MODE_MUTATES.get(mode, False)  # type: ignore[arg-type]


def extract_knowledge_facts(
    message: str | None, *, turn_index: int = 0
) -> list[ObservedExtraction]:
    """Extract concrete technical facts from a knowledge turn.

    Reuses the canonical deterministic extractor (``extract_parameters``) and the
    same params→ObservedExtraction mapping the intake node uses — no parallel
    extraction logic.
    """
    text = str(message or "").strip()
    if not text:
        return []
    # Lazy imports: keep this contract module light and avoid import cycles.
    from app.agent.domain.normalization import extract_parameters  # noqa: PLC0415
    from app.agent.graph.nodes.intake_observe_node import (  # noqa: PLC0415
        _regex_params_to_extractions,
    )

    try:
        params = extract_parameters(text)
    except Exception:  # noqa: BLE001 - extraction is best-effort
        return []
    return _regex_params_to_extractions(params, turn_index)


def has_new_technical_facts(message: str | None) -> bool:
    """Whether a knowledge turn supplies new technical facts (→ mutating).

    A bare material/medium name in a question is the question subject, not a
    stated fact (§8.4/§8.5/§8.7). Only unambiguous operating measurements, or a
    material/medium that is explicitly asserted as used, count as new facts.
    """
    text = str(message or "").strip()
    if not text:
        return False
    from app.agent.domain.normalization import extract_parameters  # noqa: PLC0415

    try:
        params = extract_parameters(text)
    except Exception:  # noqa: BLE001
        return False

    if any(params.get(key) is not None for key in _OPERATING_FACT_KEYS):
        return True

    names_material_or_medium = any(
        params.get(key)
        for key in (
            "material_normalized",
            "material_raw",
            "medium_normalized",
            "medium_raw",
        )
    )
    if names_material_or_medium and "?" not in text and _FACT_ASSERTION_RE.search(text):
        return True
    return False


def resolve_knowledge_mode(
    message: str | None,
    *,
    has_active_case: bool,
) -> KnowledgeMode:
    """Resolve a knowledge turn into one of the seven §8 modes.

    Precedence: why-question → new facts (mutating) → norm/compliance →
    comparison → case-aware/general. Intended to run on a turn already routed to
    the knowledge path (consumes the existing active-case signal).
    """
    text = str(message or "")

    if _WHY_RE.search(text):
        return "why_question_active_case" if has_active_case else "knowledge_general"

    # Concrete new facts mutate the case (only these facts; §8.6).
    if has_new_technical_facts(text):
        return "knowledge_case_mutating"

    if _NORM_RE.search(text):
        return "norm_documentation_knowledge"

    if _COMPARISON_RE.search(text):
        return "comparison_case_aware" if has_active_case else "comparison_general"

    if has_active_case:
        return "knowledge_case_aware"
    return "knowledge_general"


def build_why_question_reply(
    *,
    opening: str,
    technical_hint: str = "",
    primary_question: str = "",
):
    """Render a why-question answer (§8.10) via the Patch-2 senior_engineer_short
    style: explains the reason, asks at most one question, never mirrors the
    whole case and never appends a routine disclaimer (No-Go guard applies).
    """
    from app.agent.templates.registry import render_chat_reply  # noqa: PLC0415

    return render_chat_reply(
        "senior_engineer_short",
        {
            "opening": opening,
            "technical_hint": technical_hint,
            "primary_question": primary_question,
        },
        primary_question={"text": primary_question} if primary_question else None,
    )


def apply_knowledge_turn(
    state: GovernedSessionState,
    message: str | None,
    *,
    has_active_case: bool,
    turn_index: int = 0,
) -> GovernedSessionState:
    """Apply a knowledge turn's mutation policy (§8.2/§27.5).

    Non-mutating modes return ``state`` unchanged (case_revision preserved). For
    ``knowledge_case_mutating``, only the supplied facts run through the State
    Gate (the same reducers as the engineering path).
    """
    mode = resolve_knowledge_mode(message, has_active_case=has_active_case)
    if not mode_mutates(mode):
        return state

    facts = extract_knowledge_facts(message, turn_index=turn_index)
    if not facts:
        return state

    observed = state.observed
    for fact in facts:
        observed = observed.with_extraction(fact)
    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)
    return state.model_copy(
        update={"observed": observed, "normalized": normalized, "asserted": asserted}
    )
