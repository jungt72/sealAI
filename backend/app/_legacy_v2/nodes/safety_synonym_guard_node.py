"""Deterministic pre-router safety synonym guard.

This node runs before any LLM-based router/frontdoor logic and intercepts
messages that contain safety-critical terms (e.g., H2/O2/HF/AED).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

import structlog
from langchain_core.messages import AIMessage
from langgraph.types import Command

from app._legacy_v2.phase import PHASE
from app._legacy_v2.state import SealAIState

logger = structlog.get_logger("langgraph_v2.safety_synonym_guard")


SAFETY_SYNONYM_REGEX: Dict[str, tuple[str, ...]] = {
    "hydrogen_h2": (
        r"\bh\s*[-_/]?\s*2\b",
        r"\bh₂\b",
        r"\bwasserstoff(?:gas)?\b",
        r"\bhydrogen\b",
        r"\bformiergas\b",
        r"\bforming\s+gas\b",
        r"\breforming\s+gas\b",
        r"\bpem(?:[-\s]?brennstoffzelle)?\b",
        r"\bfuel\s*cell\b",
        r"\bbrennstoffzelle\b",
        r"\belektrolytisch(?:er|es)?\s+wasserstoff\b",
        r"\bgr[üu]ner\s+wasserstoff\b",
        r"\bgruener\s+wasserstoff\b",
        r"\belectrolytic\s+hydrogen\b",
        r"\brenewable\s+hydrogen\b",
        r"\bpower-to-gas\b",
    ),
    "oxygen_o2": (
        r"\bo\s*[-_/]?\s*2\b",
        r"\bo₂\b",
        r"\bsauerstoff\b",
        r"\boxygen\b",
        r"\blox\b",
        r"\bmedical\s+oxygen\b",
        r"\boxidizer\b",
        r"\bbeatmungsgas\b",
        r"\boxy\b",
    ),
    "hydrofluoric_acid_hf": (
        r"\bhf\b",
        r"\bflusss?[äa]ure\b",
        r"\bhydrofluoric\s+acid\b",
        r"\bfluorwasserstoff\b",
        r"\bfluoride?\b",
    ),
    "amines": (
        r"\bfilming\s+amines?\b",
        r"\baggressive?\s+amines?\b",
        r"\bamines?\b",
        r"\bmonoethanolamin(?:e)?\b",
        r"\bmea\b",
        r"\bdea\b",
        r"\bcyclohexylamin(?:e)?\b",
        r"\bmorpholin(?:e)?\b",
        r"\bkorrosionsinhibitor(?:en)?\b",
    ),
    "aed_rgd_context": (
        r"\baed\b",
        r"\brgd\b",
        r"\brapid\s+gas\s+decompression\b",
        r"\bexplosive\s+decompression\b",
        r"\bschnelle?\s+druckentlastung\b",
        r"\bdruckentlastung\b",
        r"\bdruckabfall\b",
        r"\bco\s*[-_/]?\s*2\b",
        r"\bco₂\b",
        r"\blpg\b",
        r"\bpropan\b",
        r"\bbutan\b",
        r"\bnh\s*[-_/]?\s*3\b",
        r"\bammoniak\b",
        r"\bh2s\b",
        r"\bschwefelwasserstoff\b",
    ),
}

COMPILED_SAFETY_SYNONYM_REGEX: Dict[str, tuple[re.Pattern[str], ...]] = {
    category: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for category, patterns in SAFETY_SYNONYM_REGEX.items()
}

_SAFETY_SYNONYM_ALLOWLIST_BY_CATEGORY: Dict[str, set[str]] = {
    # Domain terms often used in sealing/media context and should not trigger HITL by themselves.
    "amines": {"amine", "amines", "filming amine", "filming amines"},
}


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text is not None:
                    parts.append(str(text))
            else:
                parts.append(str(item))
        return " ".join(parts)
    if content is None:
        return ""
    return str(content)


def _user_message_texts(state: SealAIState) -> List[str]:
    texts: List[str] = []
    for message in list(state.conversation.messages or []):
        role = (getattr(message, "type", None) or getattr(message, "role", None) or "").strip().lower()
        if role not in {"human", "user"}:
            continue
        text = _message_content_to_text(getattr(message, "content", None)).strip()
        if text:
            texts.append(text)
    return texts


def _iter_category_matches(text: str, patterns: Iterable[re.Pattern[str]]) -> List[str]:
    hits: List[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            normalized = value.lower()
            if not value or normalized in seen:
                continue
            seen.add(normalized)
            hits.append(value)
    return hits


def _normalize_allowlist_token(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _apply_category_allowlist(category: str, matches: List[str]) -> List[str]:
    allowlist = _SAFETY_SYNONYM_ALLOWLIST_BY_CATEGORY.get(category)
    if not allowlist or not matches:
        return matches
    filtered: List[str] = []
    for match in matches:
        if _normalize_allowlist_token(match) in allowlist:
            continue
        filtered.append(match)
    return filtered


def detect_safety_synonym_hits(state: SealAIState) -> Dict[str, List[str]]:
    combined_text = "\n".join(_user_message_texts(state))
    if not combined_text:
        return {}
    results: Dict[str, List[str]] = {}
    for category, patterns in COMPILED_SAFETY_SYNONYM_REGEX.items():
        matches = _iter_category_matches(combined_text, patterns)
        matches = _apply_category_allowlist(category, matches)
        if matches:
            results[category] = matches
    return results


def safety_synonym_guard_node(state: SealAIState) -> Command:
    """Deterministic safety pre-check before any LLM router execution."""
    hits = detect_safety_synonym_hits(state)
    flags = dict(state.reasoning.flags or {})

    if hits:
        matched_categories = sorted(hits.keys())
        flags["safety_synonym_guard_triggered"] = True
        flags["safety_synonym_categories"] = matched_categories
        flags["safety_synonym_hits"] = hits
        logger.warning(
            "safety_synonym_guard_hitl_bypass_triggered",
            categories=matched_categories,
            hits=hits,
            thread_id=state.conversation.thread_id,
            run_id=state.system.run_id,
        )

        hitl_notice = (
            "⚠️ Ihre Anfrage enthält sicherheitsrelevante Substanzen "
            f"({', '.join(sorted(matched_categories))}). "
            "Diese Kombination erfordert eine Prüfung durch einen "
            "zertifizierten Fachingenieur (HITL-SEV-1/2-Review).\n\n"
            "Sie erhalten eine qualifizierte Rückmeldung innerhalb der "
            "vereinbarten SLA-Zeit. Für dringende Fälle: "
            "Direktkontakt mit dem Hersteller-Anwendungstechniker empfohlen."
        )

        return Command(
            update={
                "conversation": {"messages": [AIMessage(content=hitl_notice)]},
                "reasoning": {
                    "phase": PHASE.CONFIRM,
                    "last_node": "safety_synonym_guard_node",
                    "awaiting_user_input": False,
                    "streaming_complete": True,
                    "flags": flags,
                },
                "system": {
                    "final_answer": hitl_notice,
                    "requires_human_review": True,
                    "safety_class": "SEV-1",
                    "awaiting_user_confirmation": True,
                    "pending_action": "human_review",
                    "confirm_status": "pending",
                    "error": (
                        "Safety-critical term detected by deterministic synonym guard. "
                        "Routed directly to human review."
                    ),
                },
            },
            goto="human_review_node",
        )

    flags["safety_synonym_guard_triggered"] = False
    return Command(
        update={
            "reasoning": {
                "last_node": "safety_synonym_guard_node",
                "flags": flags,
            },
        },
        goto="combinatorial_chemistry_guard_node",
    )


__all__ = [
    "SAFETY_SYNONYM_REGEX",
    "COMPILED_SAFETY_SYNONYM_REGEX",
    "detect_safety_synonym_hits",
    "safety_synonym_guard_node",
]
