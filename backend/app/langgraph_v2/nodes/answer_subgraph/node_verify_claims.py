from __future__ import annotations

"""Verify drafted answers against contract-level Evidence Authority.

This node enforces two guarantees:
1. State-Race-Condition Protection: the draft must be bound to the same
   contract hash that was active when drafting started.
2. Claim consistency: rendered numeric claims and mandatory disclaimers must
   match the ``AnswerContract``.

The verification result routes the subgraph into deterministic patching or
safe fallback paths.
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Set

import structlog

from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState, VerificationReport
from app.mcp.calculations.chemical_resistance import lookup as _chem_lookup
from app.mcp.calculations.material_limits import check as _limits_check

logger = structlog.get_logger("langgraph_v2.answer_subgraph.verify_claims")

_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")
# Match bracket references like [1], [2], or [1-3]. These are citation/list
# markers and not factual claims, so they are excluded from numeric evidence checks.
_BRACKET_REFERENCE_PATTERN = re.compile(r"\[\s*\d+(?:\s*[-,]\s*\d+)*\s*\]")
# Match ordered list prefixes at line start (e.g. "1. ", "12. ").
# These formatting ordinals are not technical measurements.
_LIST_PREFIX_PATTERN = re.compile(r"(?m)^\s*\d+\.\s+")
_SUSPICIOUS_HOMOGLYPH_BAR_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s*[^\x00-\x7f]ar\b")
_SUSPICIOUS_DEGREE_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s*˚\s*[cC]\b")

# ── Chemical Resistance Post-Check ──────────────────────────────────────────
_CHEM_MATERIAL_RE = re.compile(
    r"\b(NBR|FKM|EPDM|PTFE|HNBR|FFKM|CR|VMQ|Viton|Kalrez|Neopren)\b",
    re.IGNORECASE,
)
_CHEM_MEDIUM_RE = re.compile(
    r"\b(Hydrauliköl|HLP|Wasser|Dampf|Diesel|Ethanol|Aceton"
    r"|Schwefelsäure|H2SO4|Natronlauge|NaOH|Wasserstoff|H2"
    r"|Sauerstoff|O2|Kohlendioxid|CO2)\b",
    re.IGNORECASE,
)
_CHEM_POSITIVE_RE = re.compile(
    r"\b(geeignet|beständig|empfohlen|einsetzbar|verwendbar|kompatibel"
    r"|suitable|resistant|compatible|recommended)\b",
    re.IGNORECASE,
)
_CHEM_NEGATIVE_RE = re.compile(
    r"nicht\s+geeignet|ungeeignet|nicht\s+beständig|nicht\s+empfohlen"
    r"|not\s+suitable|not\s+compatible",
    re.IGNORECASE,
)

# ── Material Limits Post-Check ───────────────────────────────────────────────
_LIMITS_TEMP_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*°\s*[Cc]\b")
_LIMITS_PRESSURE_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*bar\b", re.IGNORECASE)


def _strip_formatting_numbers(text: str) -> str:
    """Remove formatting-only number markers from free text.

    Args:
        text: Candidate answer text.

    Returns:
        Text with citation/list numbering removed.
    """
    sanitized = _BRACKET_REFERENCE_PATTERN.sub(" ", text or "")
    sanitized = _LIST_PREFIX_PATTERN.sub("", sanitized)
    return sanitized


def _numbers_from_text(text: str, *, ignore_formatting_numbers: bool = False) -> Set[str]:
    """Extract normalized numeric tokens from text.

    Args:
        text: Source text for extraction.
        ignore_formatting_numbers: When ``True``, citation and ordered-list
            numbers are removed before extraction to prevent false positives.

    Returns:
        Set of numeric tokens found in text.
    """
    normalized = _strip_formatting_numbers(text) if ignore_formatting_numbers else (text or "")
    return set(_NUMBER_PATTERN.findall(normalized))


def _find_suspicious_unicode_spans(text: str) -> List[str]:
    spans: List[str] = []
    for pattern in (_SUSPICIOUS_HOMOGLYPH_BAR_PATTERN, _SUSPICIOUS_DEGREE_PATTERN):
        for match in pattern.finditer(text or ""):
            spans.append(match.group(0))
    return spans


def _expected_numbers_from_user_fields(contract: AnswerContract) -> Set[str]:
    """Extract expected numeric claims from user-facing contract fields only.

    Internal identifiers like selected fact/chunk IDs are intentionally excluded.
    """
    expected: Set[str] = set()
    expected |= _numbers_from_text(json.dumps(contract.resolved_parameters, ensure_ascii=False))
    expected |= _numbers_from_text(json.dumps(contract.calc_results, ensure_ascii=False))
    for disclaimer in contract.required_disclaimers:
        expected |= _numbers_from_text(disclaimer)
    return expected


def _allowed_number_tokens_from_flags(state: SealAIState) -> Set[str]:
    flags = getattr(state, "flags", {}) or {}
    raw = flags.get("answer_subgraph_allowed_number_tokens")
    if not isinstance(raw, list):
        return set()
    out: Set[str] = set()
    for token in raw:
        text = str(token or "").strip()
        if text:
            out.add(text)
    return out


def _numbers_from_sources(state: SealAIState) -> Set[str]:
    numbers: Set[str] = set()
    for source in list(getattr(state, "sources", []) or []):
        snippet = ""
        if isinstance(source, dict):
            snippet = str(source.get("snippet") or source.get("text") or "")
        else:
            snippet = str(getattr(source, "snippet", "") or getattr(source, "text", "") or "")
        numbers |= _numbers_from_text(snippet)
    numbers |= _numbers_from_text(str(getattr(state, "context", "") or ""))
    return numbers


def _skip_strict_number_checks(state: SealAIState) -> bool:
    flags = getattr(state, "flags", {}) or {}
    if bool(flags.get("number_verification_skip_active")):
        return True
    goal = str(getattr(getattr(state, "intent", None), "goal", "") or "").strip().lower()
    if goal == "explanation_or_comparison":
        return True
    category = str(
        getattr(state, "intent_category", None)
        or flags.get("frontdoor_intent_category")
        or ""
    ).strip().upper()
    return category == "MATERIAL_RESEARCH"


def _build_failure_span(
    *,
    reason: str,
    expected_value: str,
    wrong_span: str = "",
) -> Dict[str, str]:
    """Create a structured verification failure span.

    Args:
        reason: Machine-readable failure reason.
        expected_value: Required value from contract/evidence.
        wrong_span: Observed mismatching value in draft text.

    Returns:
        Serializable failure span record.
    """
    return {
        "reason": reason,
        "expected_value": expected_value,
        "wrong_span": wrong_span,
    }


def _check_resistance_claims(draft_text: str) -> List[Dict[str, str]]:
    """Scannt draft_text auf positive Beständigkeitsaussagen (Material × Medium)
    und prüft jede deterministisch gegen chemical_resistance.lookup().
    Gibt failure spans zurück wenn lookup() → C (nicht beständig).
    Bereits korrigierte Paare (Korrekturhinweis vorhanden) werden übersprungen.
    """
    spans: List[Dict[str, str]] = []
    sentences = re.split(r"[.!?\n]+", draft_text or "")
    for sentence in sentences:
        # Nur Sätze mit positivem Framing prüfen
        if not _CHEM_POSITIVE_RE.search(sentence):
            continue
        # Sätze die bereits negieren sind korrekt — überspringen
        if _CHEM_NEGATIVE_RE.search(sentence):
            continue
        materials = [m.group(0) for m in _CHEM_MATERIAL_RE.finditer(sentence)]
        mediums = [m.group(0) for m in _CHEM_MEDIUM_RE.finditer(sentence)]
        for mat in materials:
            for med in mediums:
                try:
                    result = _chem_lookup(med, mat)
                except KeyError:
                    continue  # Unbekannte Kombination → X, kein hard fail
                if result.rating != "C":
                    continue
                # Nicht erneut melden wenn Korrekturhinweis bereits im Text
                if f"Korrekturhinweis: {result.material} ist für {med} nicht beständig" in draft_text:
                    continue
                spans.append(_build_failure_span(
                    reason="chemical_resistance_contradiction",
                    expected_value=(
                        f"{result.material} ist für {med} nicht beständig "
                        f"(Bewertung C – {result.source})."
                    ),
                    wrong_span="",  # Kein Replace — Disclaimer via targeted_patch Pass 2
                ))
    return spans


def _check_limits_claims(draft_text: str) -> List[Dict[str, str]]:
    """Scannt draft_text auf Material × Temperatur/Druck-Kombinationen
    und prüft deterministisch gegen material_limits.check().
    Gibt failure spans zurück wenn temp_ok is False oder pressure_ok is False.
    """
    spans: List[Dict[str, str]] = []
    sentences = re.split(r"[.!?\n]+", draft_text or "")
    for sentence in sentences:
        materials = [m.group(0) for m in _CHEM_MATERIAL_RE.finditer(sentence)]
        if not materials:
            continue
        temps = [
            float(m.group(1).replace(",", "."))
            for m in _LIMITS_TEMP_RE.finditer(sentence)
        ]
        pressures = [
            float(m.group(1).replace(",", "."))
            for m in _LIMITS_PRESSURE_RE.finditer(sentence)
        ]
        if not temps and not pressures:
            continue
        for mat in materials:
            for temp_c in temps:
                try:
                    result = _limits_check(mat, temp_c=temp_c)
                except KeyError:
                    continue
                if result.temp_ok is False:
                    lim = result.limits
                    spans.append(_build_failure_span(
                        reason="material_temp_exceeded",
                        expected_value=(
                            f"{result.material} max. Dauertemperatur: "
                            f"{lim.temp_max_c} °C (Peak: {lim.temp_peak_c} °C) "
                            f"— {lim.norm_ref}"
                        ),
                        wrong_span=f"{mat} bei {temp_c} °C",
                    ))
            for pressure_bar in pressures:
                try:
                    result = _limits_check(mat, pressure_bar=pressure_bar)
                except KeyError:
                    continue
                if result.pressure_ok is False:
                    lim = result.limits
                    spans.append(_build_failure_span(
                        reason="material_pressure_exceeded",
                        expected_value=(
                            f"{result.material} max. Druck (statisch): "
                            f"{lim.pressure_static_max_bar} bar — {lim.norm_ref}"
                        ),
                        wrong_span=f"{mat} bei {pressure_bar} bar",
                    ))
    return spans


def node_verify_claims(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Validate drafted answer content against the answer contract.

    The check sequence is intentionally strict:
    - verify contract hash continuity (State-Race-Condition Protection),
    - reject empty drafts,
    - compare numeric claims against contract Evidence Authority,
    - ensure required disclaimers are present.

    Formatting-only numbers (e.g., ``[1]`` or ``1.`` list markers) are ignored
    during rendered-text extraction so they do not trigger
    ``unexpected_number`` failures.

    Args:
        state: Current graph state.
        *_args: Unused positional arguments for LangGraph compatibility.
        **_kwargs: Unused keyword arguments for LangGraph compatibility.

    Returns:
        State patch with ``verification_report`` and node marker.
    """
    draft_text = str(state.draft_text or "")
    draft_hash = hashlib.sha256(draft_text.encode()).hexdigest()

    # CRITICAL GUARD
    if state.answer_contract is None or hashlib.sha256(state.answer_contract.model_dump_json().encode()).hexdigest() != state.draft_base_hash:
        contract_hash = (
            hashlib.sha256(state.answer_contract.model_dump_json().encode()).hexdigest()
            if state.answer_contract is not None
            else ""
        )
        report = VerificationReport(
            contract_hash=contract_hash,
            draft_hash=draft_hash,
            status="fail",
            failure_type="state_race_condition",
            failed_claim_spans=[
                _build_failure_span(
                    reason="state_race_condition",
                    expected_value=state.draft_base_hash or "",
                    wrong_span=contract_hash,
                )
            ],
        )
        logger.error(
            "verify_claims.state_race_condition",
            contract_hash=contract_hash,
            draft_base_hash=state.draft_base_hash,
        )
        return {"verification_report": report, "last_node": "node_verify_claims"}

    if not draft_text.strip():
        report = VerificationReport(
            contract_hash=state.draft_base_hash or "",
            draft_hash=draft_hash,
            status="fail",
            failure_type="abort",
            failed_claim_spans=[_build_failure_span(reason="empty_draft", expected_value="non_empty_draft")],
        )
        logger.error("verify_claims.empty_draft")
        return {"verification_report": report, "last_node": "node_verify_claims"}

    contract = state.answer_contract
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    expected_numbers = _expected_numbers_from_user_fields(contract)
    allowed_numbers = _allowed_number_tokens_from_flags(state) | _numbers_from_sources(state)
    rendered_numbers = _numbers_from_text(draft_text, ignore_formatting_numbers=True)
    strict_numbers_disabled = _skip_strict_number_checks(state)

    if strict_numbers_disabled:
        missing_numbers = []
        unexpected_numbers = []
    else:
        missing_numbers = sorted(expected_numbers - rendered_numbers)
        unexpected_numbers = sorted(
            token for token in (rendered_numbers - expected_numbers) if token not in allowed_numbers
        )
    missing_disclaimers = [text for text in contract.required_disclaimers if text not in draft_text]
    suspicious_unicode_spans = _find_suspicious_unicode_spans(draft_text)
    resistance_spans = _check_resistance_claims(draft_text)
    limits_spans = _check_limits_claims(draft_text)

    failed_claim_spans: List[Dict[str, str]] = []
    for number in missing_numbers:
        failed_claim_spans.append(_build_failure_span(reason="missing_number", expected_value=number))
    for number in unexpected_numbers:
        failed_claim_spans.append(
            _build_failure_span(reason="unexpected_number", expected_value="", wrong_span=number)
        )
    for disclaimer in missing_disclaimers:
        failed_claim_spans.append(
            _build_failure_span(reason="missing_disclaimer", expected_value=disclaimer)
        )
    for span in suspicious_unicode_spans:
        failed_claim_spans.append(
            _build_failure_span(reason="suspicious_unicode", expected_value="", wrong_span=span)
        )
    failed_claim_spans.extend(resistance_spans)
    failed_claim_spans.extend(limits_spans)

    status = "pass" if not failed_claim_spans else "fail"
    failure_type = None if status == "pass" else "render_mismatch"
    report = VerificationReport(
        contract_hash=contract_hash,
        draft_hash=draft_hash,
        status=status,
        failure_type=failure_type,
        failed_claim_spans=failed_claim_spans,
    )
    logger.info(
        "verify_claims.done",
        status=status,
        strict_numbers_disabled=strict_numbers_disabled,
        missing_numbers=len(missing_numbers),
        unexpected_numbers=len(unexpected_numbers),
        missing_disclaimers=len(missing_disclaimers),
        suspicious_unicode=len(suspicious_unicode_spans),
        resistance_contradictions=len(resistance_spans),
        limits_contradictions=len(limits_spans),
    )
    return {"verification_report": report, "last_node": "node_verify_claims"}


__all__ = ["node_verify_claims"]
