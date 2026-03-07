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
from typing import Any, Dict, List, Optional, Set

import structlog

from app.langgraph_v2.nodes.answer_subgraph.state import AnswerSubgraphState
from app.langgraph_v2.state.sealai_state import AnswerContract, ConflictRecord, SealAIState, VerificationReport
from app.langgraph_v2.utils.assertion_cycle import stamp_patch_with_assertion_binding
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

# ── Compound Specificity Post-Check ──────────────────────────────────────────
# Detects material family + numeric grade (e.g., NBR 70, FKM 75)
_COMPOUND_INDICATOR_RE = re.compile(
    r"\b(NBR|FKM|EPDM|PTFE|HNBR|FFKM|CR|VMQ|Viton|Kalrez|Neopren)\s+[0-9]{2,}\b",
    re.IGNORECASE,
)
# Detects specific brand names that imply compound-level specificity
_SPECIFIC_BRAND_INDICATOR_RE = re.compile(
    r"\b(Kalrez|Chemraz|Simriz|Zalak|Simrit|Garlock)\b",
    re.IGNORECASE,
)


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
    flags = getattr(state.reasoning, "flags", {}) or {}
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
    for source in list(getattr(state.system, "sources", []) or []):
        snippet = ""
        if isinstance(source, dict):
            snippet = str(source.get("snippet") or source.get("text") or "")
        else:
            snippet = str(getattr(source, "snippet", "") or getattr(source, "text", "") or "")
        numbers |= _numbers_from_text(snippet)
    numbers |= _numbers_from_text(str(getattr(state.reasoning, "context", "") or ""))
    return numbers


def _skip_strict_number_checks(state: SealAIState) -> bool:
    flags = getattr(state.reasoning, "flags", {}) or {}
    if bool(flags.get("number_verification_skip_active")):
        return True
    goal = str(getattr(getattr(state.conversation, "intent", None), "goal", "") or "").strip().lower()
    if goal == "explanation_or_comparison":
        return True
    category = str(
        getattr(state.reasoning, "intent_category", None)
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


def _as_numeric(value: Any) -> "Optional[float]":
    """Convert value to float, return None if not convertible."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_parameter_conflicts(
    draft_text: str, contract: AnswerContract
) -> List[ConflictRecord]:
    """Compare draft-stated parameter values against contract-authoritative values.

    Raises PARAMETER_CONFLICT/WARNING when draft mentions a numeric value for
    pressure_bar or temperature_C that does not match the contract authority.
    Tolerates minor rounding differences (±0.5 bar, ±1.0 °C).

    Only fires when the contract has an authoritative value AND the draft
    mentions the same parameter with a different value. Never adds to
    failed_claim_spans — severity WARNING only, no hard routing impact.
    """
    conflicts: List[ConflictRecord] = []
    params = contract.resolved_parameters

    contract_pressure = _as_numeric(params.get("pressure_bar"))
    if contract_pressure is not None:
        draft_pressures = [
            float(m.group(1).replace(",", "."))
            for m in _LIMITS_PRESSURE_RE.finditer(draft_text)
        ]
        if draft_pressures and not any(
            abs(dp - contract_pressure) < 0.5 for dp in draft_pressures
        ):
            conflicts.append(ConflictRecord(
                conflict_type="PARAMETER_CONFLICT",
                severity="WARNING",
                summary=(
                    f"Draft pressure values {[round(p, 1) for p in draft_pressures]} bar "
                    f"differ from contract authority: {contract_pressure} bar."
                ),
                sources_involved=["draft", "contract.resolved_parameters"],
                scope_note=(
                    "Mismatch between draft-stated pressure and contract-authoritative value. "
                    "Verify which value is correct."
                ),
                resolution_status="OPEN",
            ))

    contract_temp = _as_numeric(
        params.get("temperature_C") or params.get("temperature_c")
    )
    if contract_temp is not None:
        draft_temps = [
            float(m.group(1).replace(",", "."))
            for m in _LIMITS_TEMP_RE.finditer(draft_text)
        ]
        if draft_temps and not any(
            abs(dt - contract_temp) < 1.0 for dt in draft_temps
        ):
            conflicts.append(ConflictRecord(
                conflict_type="PARAMETER_CONFLICT",
                severity="WARNING",
                summary=(
                    f"Draft temperature values {[round(t, 1) for t in draft_temps]} °C "
                    f"differ from contract authority: {contract_temp} °C."
                ),
                sources_involved=["draft", "contract.resolved_parameters"],
                scope_note=(
                    "Mismatch between draft-stated temperature and contract-authoritative value. "
                    "Verify which value is correct."
                ),
                resolution_status="OPEN",
            ))

    return conflicts


def _check_blocking_unknowns(
    draft_text: str, contract: AnswerContract
) -> List[ConflictRecord]:
    """Identify cases where the draft makes technical claims (pressure/temp)
    but the contract has no authoritative value for these parameters.

    This is a governance-level conflict with severity BLOCKING_UNKNOWN.
    """
    conflicts: List[ConflictRecord] = []
    params = contract.resolved_parameters

    # Check for missing pressure while draft claims pressure
    if _as_numeric(params.get("pressure_bar")) is None:
        if _LIMITS_PRESSURE_RE.search(draft_text):
            conflicts.append(ConflictRecord(
                conflict_type="PARAMETER_CONFLICT",
                severity="BLOCKING_UNKNOWN",
                summary="Draft mentions pressure values but contract has no authoritative pressure.",
                sources_involved=["draft", "contract.resolved_parameters"],
                scope_note=(
                    "Technical release blocked: pressure is unknown in contract authority "
                    "but specified in draft. Manufacturer validation or user input required."
                ),
                resolution_status="OPEN",
            ))

    # Check for missing temperature while draft claims temperature
    if _as_numeric(params.get("temperature_C") or params.get("temperature_c")) is None:
        if _LIMITS_TEMP_RE.search(draft_text):
            conflicts.append(ConflictRecord(
                conflict_type="PARAMETER_CONFLICT",
                severity="BLOCKING_UNKNOWN",
                summary="Draft mentions temperature values but contract has no authoritative temperature.",
                sources_involved=["draft", "contract.resolved_parameters"],
                scope_note=(
                    "Technical release blocked: temperature is unknown in contract authority "
                    "but specified in draft. Manufacturer validation or user input required."
                ),
                resolution_status="OPEN",
            ))

    return conflicts


def _check_specificity_conflicts(
    draft_text: str, contract: AnswerContract
) -> List[ConflictRecord]:
    """Identify cases where the draft makes compound-specific claims but the
    contract only provides family-level evidence.
    """
    conflicts: List[ConflictRecord] = []

    # Check if we have ANY compound-specific candidate in the contract
    has_compound_specific = any(
        str(c.get("specificity") or "") == "compound_specific"
        for c in contract.candidate_semantics
    )

    if not has_compound_specific:
        # 1. Family + numeric grade (e.g. NBR 70)
        compound_match = _COMPOUND_INDICATOR_RE.search(draft_text)
        if compound_match:
            conflicts.append(ConflictRecord(
                conflict_type="COMPOUND_SPECIFICITY_CONFLICT",
                severity="RESOLUTION_REQUIRES_MANUFACTURER_SCOPE",
                summary=(
                    f"Draft mentions specific grade '{compound_match.group(0)}' "
                    "but contract only carries family-level evidence."
                ),
                sources_involved=["draft", "contract.candidate_semantics"],
                scope_note=(
                    "The draft makes a compound-specific grade claim. Since the contract "
                    "only contains family data, manufacturer validation is required."
                ),
                resolution_status="OPEN",
            ))
            return conflicts  # Avoid duplicate specificity conflicts

        # 2. Specific brand names not explicitly in contract as compound_specific
        brand_match = _SPECIFIC_BRAND_INDICATOR_RE.search(draft_text)
        if brand_match:
            brand_name = brand_match.group(0).lower()
            # If the brand name isn't already a value in the contract, it's a specificity jump
            if not any(brand_name in str(c.get("value") or "").lower() for c in contract.candidate_semantics):
                conflicts.append(ConflictRecord(
                    conflict_type="COMPOUND_SPECIFICITY_CONFLICT",
                    severity="RESOLUTION_REQUIRES_MANUFACTURER_SCOPE",
                    summary=(
                        f"Draft mentions specific brand '{brand_match.group(0)}' "
                        "but contract only carries generic family evidence."
                    ),
                    sources_involved=["draft", "contract.candidate_semantics"],
                    scope_note=(
                        "Manufacturer-specific products require direct confirmation; "
                        "generic family suitability is insufficient for brand-level claims."
                    ),
                    resolution_status="OPEN",
                ))

    return conflicts


def _check_condition_conflicts(draft_text: str, contract: AnswerContract) -> List[ConflictRecord]:
    """Identify cases where the draft claims suitability but mandatory
    operational conditions are missing or unconfirmed in RequirementSpec.
    """
    conflicts: List[ConflictRecord] = []
    spec = contract.requirement_spec
    if not spec:
        return conflicts

    # Rule: Positive claim + missing critical parameters (e.g. Shaft Runout for PTFE)
    if _CHEM_POSITIVE_RE.search(draft_text):
        missing = spec.missing_critical_parameters
        if missing:
            # Check if the draft at least mentions the missing parameters as a condition
            mentions_conditions = any(str(p).lower() in draft_text.lower() for p in missing)
            if not mentions_conditions:
                conflicts.append(
                    ConflictRecord(
                        conflict_type="CONDITION_CONFLICT",
                        severity="HARD",
                        summary=(
                            f"Technical suitability claimed but critical conditions {missing} "
                            "are missing and not conditioned in draft."
                        ),
                        sources_involved=["draft", "requirement_spec.missing_critical_parameters"],
                        scope_note=(
                            "High-performance seals require confirmed shaft runout/hardness "
                            "which are currently unknown."
                        ),
                        resolution_status="OPEN",
                    )
                )
    return conflicts


def _check_assumption_conflicts(draft_text: str, contract: AnswerContract) -> List[ConflictRecord]:
    """Identify cases where the draft makes definitive claims based on
    unconfirmed assumptions flagged in GovernanceMetadata.
    """
    conflicts: List[ConflictRecord] = []
    gov = contract.governance_metadata

    # Rule: Definitive claim in draft vs. "Antwort basiert auf begrenzter Evidenz" in assumptions_active
    has_limited_evidence_assumption = any(
        "begrenzter Evidenz" in a or "Unsicherheits-Hinweis" in a for a in gov.assumptions_active
    )

    if has_limited_evidence_assumption:
        # If draft does NOT contain uncertainty markers but contract says it's based on assumptions
        uncertainty_markers = [
            "vorausgesetzt",
            "angenommen",
            "unsicher",
            "begrenzte",
            "uncertain",
            "assuming",
        ]
        if not any(m in draft_text.lower() for m in uncertainty_markers):
            conflicts.append(
                ConflictRecord(
                    conflict_type="ASSUMPTION_CONFLICT",
                    severity="WARNING",
                    summary=(
                        "Draft presents definitive recommendation while contract is based on "
                        "limited evidence assumptions."
                    ),
                    sources_involved=["draft", "governance_metadata.assumptions_active"],
                    scope_note="The system flagged this as an uncertain case, but the draft sounds too certain.",
                    resolution_status="OPEN",
                )
            )
    return conflicts


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


def node_verify_claims(state: AnswerSubgraphState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
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
    draft_text = str(state.system.draft_text or "")
    draft_hash = hashlib.sha256(draft_text.encode()).hexdigest()

    # CRITICAL GUARD
    if state.system.answer_contract is None or hashlib.sha256(state.system.answer_contract.model_dump_json().encode()).hexdigest() != state.system.draft_base_hash:
        contract_hash = (
            hashlib.sha256(state.system.answer_contract.model_dump_json().encode()).hexdigest()
            if state.system.answer_contract is not None
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
                    expected_value=state.system.draft_base_hash or "",
                    wrong_span=contract_hash,
                )
            ],
        )
        logger.error(
            "verify_claims.state_race_condition",
            contract_hash=contract_hash,
            draft_base_hash=state.system.draft_base_hash,
        )
        return stamp_patch_with_assertion_binding(state, {
                   "system": {
                       "verification_report": report,
                   },
                   "reasoning": {
                       "last_node": "node_verify_claims",
                   },
               })

    if not draft_text.strip():
        report = VerificationReport(
            contract_hash=state.system.draft_base_hash or "",
            draft_hash=draft_hash,
            status="fail",
            failure_type="abort",
            failed_claim_spans=[_build_failure_span(reason="empty_draft", expected_value="non_empty_draft")],
        )
        logger.error("verify_claims.empty_draft")
        return stamp_patch_with_assertion_binding(state, {
                   "system": {
                       "verification_report": report,
                   },
                   "reasoning": {
                       "last_node": "node_verify_claims",
                   },
               })

    contract = state.system.answer_contract
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

    warning_claim_spans: List[Dict[str, str]] = []
    failed_claim_spans: List[Dict[str, str]] = []
    conflicts: List[ConflictRecord] = []
    
    for number in missing_numbers:
        span = _build_failure_span(reason="missing_number", expected_value=number)
        span["severity"] = "warning"
        warning_claim_spans.append(span)
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
        
    for span in resistance_spans:
        failed_claim_spans.append(span)
        conflicts.append(ConflictRecord(
            conflict_type="SOURCE_CONFLICT",
            severity="HARD",
            summary=f"Chemical resistance contradiction detected: {span['expected_value']}",
            sources_involved=["draft", "chemical_resistance_lookup"],
            scope_note="Draft claims compatibility while lookup denies it.",
            resolution_status="OPEN",
        ))

    for span in limits_spans:
        failed_claim_spans.append(span)
        conflicts.append(ConflictRecord(
            conflict_type="SOURCE_CONFLICT",
            severity="HARD",
            summary=f"Material limit contradiction detected: {span['wrong_span']}",
            sources_involved=["draft", "material_limits_lookup"],
            scope_note="Draft claims viability beyond defined operational limits.",
            resolution_status="OPEN",
        ))

    # Basic SCOPE_CONFLICT heuristic: check if draft makes a claim that is conditionally true
    if "aber" in draft_text.lower() or "jedoch" in draft_text.lower() or "nur bedingt" in draft_text.lower():
        # Minimal extraction of conditional clauses indicating potential scope mismatch
        if any("geeignet" in s.lower() and "nicht" in s.lower() for s in re.split(r"[.!?\n]+", draft_text)):
             conflicts.append(ConflictRecord(
                conflict_type="SCOPE_CONFLICT",
                severity="WARNING",
                summary="Potential scope conflict or conditional viability detected in text.",
                sources_involved=["draft"],
                scope_note="Text contains contradictory suitability statements that may depend on unclarified scope.",
                resolution_status="OPEN",
            ))

    # BLOCKING_UNKNOWN: draft-stated technical parameters vs. missing contract authority
    conflicts.extend(_check_blocking_unknowns(draft_text, contract))

    # PARAMETER_CONFLICT: draft-stated values vs. contract-authoritative values
    conflicts.extend(_check_parameter_conflicts(draft_text, contract))

    # COMPOUND_SPECIFICITY_CONFLICT: draft-stated specific grades vs. contract-authoritative generic evidence
    conflicts.extend(_check_specificity_conflicts(draft_text, contract))

    # CONDITION_CONFLICT: missing technical conditions in RequirementSpec
    conflicts.extend(_check_condition_conflicts(draft_text, contract))

    # ASSUMPTION_CONFLICT: definitive claims vs. active governance assumptions
    conflicts.extend(_check_assumption_conflicts(draft_text, contract))

    status = "pass" if not failed_claim_spans else "fail"
    failure_type = None if status == "pass" else "render_mismatch"
    report_spans = [*failed_claim_spans, *warning_claim_spans]
    report = VerificationReport(
        contract_hash=contract_hash,
        draft_hash=draft_hash,
        status=status,
        failure_type=failure_type,
        failed_claim_spans=report_spans,
        conflicts=conflicts,
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
        conflict_count=len(conflicts),
    )
    return stamp_patch_with_assertion_binding(state, {
               "system": {
                   "verification_report": report,
               },
               "reasoning": {
                   "last_node": "node_verify_claims",
               },
           })


__all__ = ["node_verify_claims"]
