from __future__ import annotations

from typing import Any

from app.agent.v91.contracts import (
    IntelligenceSlice,
    IntelligenceState,
    TabState,
    V91WorkspaceProjection,
)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _strings(value: Any, *, limit: int = 6) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item) for item in value]
    else:
        candidates = [str(value)]

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = " ".join(str(candidate or "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _candidate_label(candidate: Any) -> str | None:
    label = str(
        _get(candidate, "label") or _get(candidate, "material_key") or ""
    ).strip()
    if not label:
        return None
    status = str(
        _get(candidate, "plausibility_label")
        or _get(candidate, "status_label")
        or _get(candidate, "confidence")
        or ""
    ).strip()
    return f"{label}: {status}" if status else label


def _unique_refs(*values: Any, limit: int = 12) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _strings(value, limit=limit):
            if item in seen:
                continue
            seen.add(item)
            refs.append(item)
            if len(refs) >= limit:
                return refs
    return refs


def _medium_slice(medium_context: Any) -> IntelligenceSlice:
    label = str(_get(medium_context, "medium_label") or "").strip()
    summary = str(_get(medium_context, "summary") or "").strip()
    properties = _strings(_get(medium_context, "properties"))
    challenges = _strings(_get(medium_context, "challenges"))
    followup = _strings(_get(medium_context, "followup_points"))
    signals = _strings([label, *properties], limit=6)
    blockers = _strings([*challenges, *followup], limit=8)
    return IntelligenceSlice(
        slice_id="medium",
        status=str(_get(medium_context, "status") or "unavailable"),
        claim_level="screening",
        summary=summary
        or (
            f"Medium-Kontext fuer {label} liegt orientierend vor."
            if label
            else "Medium-Kontext ist noch nicht belastbar vorhanden."
        ),
        signals=signals,
        blockers=blockers,
        evidence_ref_ids=[],
        not_for_release_decisions=bool(
            _get(medium_context, "not_for_release_decisions", True)
        ),
    )


def _material_slice(material_intelligence: Any) -> IntelligenceSlice:
    candidates = list(_get(material_intelligence, "candidate_materials", []) or [])
    labels = [
        label
        for label in (_candidate_label(candidate) for candidate in candidates)
        if label
    ]
    blockers: list[str] = []
    evidence_refs: list[str] = []
    for candidate in candidates:
        blockers.extend(_strings(_get(candidate, "blocking_unknowns"), limit=4))
        blockers.extend(_strings(_get(candidate, "counterindicators"), limit=4))
        evidence_refs.extend(_strings(_get(candidate, "evidence_ref_ids"), limit=6))
    blockers.extend(
        _strings(_get(material_intelligence, "missing_field_hints"), limit=6)
    )
    for evidence in list(_get(material_intelligence, "evidence", []) or []):
        evidence_refs.extend(_strings(_get(evidence, "id"), limit=1))

    return IntelligenceSlice(
        slice_id="material",
        status=str(_get(material_intelligence, "status") or "insufficient_context"),
        claim_level="screening",
        summary=(
            "; ".join(labels[:3])
            if labels
            else "Werkstoff-Screening braucht mehr Fallkontext."
        ),
        signals=_strings(labels, limit=6),
        blockers=_strings(blockers, limit=8),
        evidence_ref_ids=_unique_refs(evidence_refs),
        not_for_release_decisions=bool(
            _get(material_intelligence, "not_for_release_decisions", True)
        ),
    )


def _challenge_slice(challenge_intelligence: Any) -> IntelligenceSlice:
    findings = list(_get(challenge_intelligence, "findings", []) or [])
    hypotheses = list(_get(challenge_intelligence, "hypotheses", []) or [])
    finding_titles = _strings(
        [_get(finding, "title") or _get(finding, "summary") for finding in findings],
        limit=6,
    )
    hypothesis_labels = _strings(
        [_get(hypothesis, "label") for hypothesis in hypotheses], limit=4
    )
    blockers: list[str] = []
    evidence_refs: list[str] = []
    for finding in findings:
        severity = str(_get(finding, "severity") or "").strip()
        title = str(_get(finding, "title") or _get(finding, "summary") or "").strip()
        if severity in {"blocking", "critical"} and title:
            blockers.append(title)
        evidence_refs.extend(_strings(_get(finding, "evidence_ref_ids"), limit=6))
    for hypothesis in hypotheses:
        blockers.extend(_strings(_get(hypothesis, "blocking_unknowns"), limit=4))
        blockers.extend(_strings(_get(hypothesis, "counterindicators"), limit=4))

    return IntelligenceSlice(
        slice_id="challenge",
        status=str(_get(challenge_intelligence, "status") or "not_run"),
        claim_level="case_projection",
        summary=(
            f"{len(findings)} Befund(e), {len(hypotheses)} Pruefhypothese(n)."
            if findings or hypotheses
            else "Noch keine Challenge-Befunde."
        ),
        signals=_strings([*finding_titles, *hypothesis_labels], limit=8),
        blockers=_strings(blockers, limit=8),
        evidence_ref_ids=_unique_refs(evidence_refs),
        not_for_release_decisions=True,
    )


def _document_slice(evidence_summary: Any) -> IntelligenceSlice:
    evidence_present = bool(_get(evidence_summary, "evidence_present", False))
    supported = _strings(_get(evidence_summary, "evidence_supported_topics"), limit=6)
    source_findings = _strings(
        _get(evidence_summary, "source_backed_findings"), limit=6
    )
    evidence_gaps = _strings(_get(evidence_summary, "evidence_gaps"), limit=6)
    open_points = _strings(_get(evidence_summary, "unresolved_open_points"), limit=6)
    count = int(_get(evidence_summary, "evidence_count", 0) or 0)
    return IntelligenceSlice(
        slice_id="document",
        status="documented" if evidence_present else "no_document_evidence",
        claim_level="screening",
        summary=(
            f"{count} Dokument-/RAG-Evidenzpunkt(e) im Workspace sichtbar."
            if evidence_present
            else "Keine dokumentierte Evidenz im aktuellen Workspace."
        ),
        signals=_strings([*supported, *source_findings], limit=8),
        blockers=_strings([*evidence_gaps, *open_points], limit=8),
        evidence_ref_ids=[],
        not_for_release_decisions=True,
    )


def _rfq_slice(rfq_status: Any, manufacturer_questions: Any) -> IntelligenceSlice:
    blockers = _strings(_get(rfq_status, "blockers"), limit=8)
    open_points = _strings(_get(rfq_status, "open_points"), limit=8)
    questions = _strings(_get(manufacturer_questions, "mandatory"), limit=6)
    rfq_ready = bool(_get(rfq_status, "rfq_ready", False))
    handover_ready = bool(_get(rfq_status, "handover_ready", False))
    return IntelligenceSlice(
        slice_id="rfq",
        status=(
            "handover_ready"
            if handover_ready
            else ("rfq_basis_ready" if rfq_ready else "not_ready")
        ),
        claim_level="manufacturer_review",
        summary=(
            "Anfragebasis ist fuer Herstellerpruefung vorbereitet."
            if rfq_ready or handover_ready
            else "Anfragebasis bleibt blockiert, bis offene Punkte geklaert sind."
        ),
        signals=questions,
        blockers=_strings([*blockers, *open_points], limit=8),
        evidence_ref_ids=[],
        not_for_release_decisions=True,
    )


def _overall_status(
    *,
    medium: IntelligenceSlice,
    material: IntelligenceSlice,
    challenge: IntelligenceSlice,
    document: IntelligenceSlice,
    rfq: IntelligenceSlice,
) -> str:
    if rfq.status in {"rfq_basis_ready", "handover_ready"}:
        return "rfq_basis"
    if any(slice_.blockers for slice_ in (challenge, material, document, rfq)):
        return "review_needed"
    if (
        medium.status != "unavailable"
        or material.status != "insufficient_context"
        or challenge.status != "not_run"
    ):
        return "screening"
    return "empty"


def _tab(
    *,
    tab_id: str,
    label: str,
    source: IntelligenceSlice,
    next_action: str | None = None,
) -> TabState:
    return TabState(
        tab_id=tab_id,  # type: ignore[arg-type]
        label=label,
        status=source.status,
        source_slice_id=source.slice_id,
        summary=source.summary,
        primary_items=source.signals,
        warnings=source.blockers,
        next_action=next_action,
        evidence_ref_ids=source.evidence_ref_ids,
        not_for_release_decisions=source.not_for_release_decisions,
    )


def build_v91_workspace_projection(
    *,
    case_revision: int,
    medium_context: Any,
    material_intelligence: Any,
    challenge_intelligence: Any,
    evidence_summary: Any,
    rfq_status: Any,
    manufacturer_questions: Any,
    communication_context: Any,
    completeness: Any,
) -> V91WorkspaceProjection:
    """Build the canonical V9.1 workspace intelligence projection.

    This is a read-only adapter over existing workspace slices. It does not
    mutate case truth and does not create release decisions.
    """

    medium = _medium_slice(medium_context)
    material = _material_slice(material_intelligence)
    challenge = _challenge_slice(challenge_intelligence)
    document = _document_slice(evidence_summary)
    rfq = _rfq_slice(rfq_status, manufacturer_questions)
    primary_question = str(
        _get(communication_context, "primary_question") or ""
    ).strip()
    open_points = _strings(_get(communication_context, "open_points_summary"), limit=6)
    coverage_gaps = _strings(_get(completeness, "coverage_gaps"), limit=6)
    parameter_source = IntelligenceSlice(
        slice_id="challenge",
        status="open" if open_points or coverage_gaps else "available",
        claim_level="case_projection",
        summary=("Parameterstatus aus governed Case- und Completeness-Projektion."),
        signals=_strings(
            _get(communication_context, "confirmed_facts_summary"), limit=6
        ),
        blockers=_strings([*open_points, *coverage_gaps], limit=8),
        not_for_release_decisions=True,
    )

    intelligence_state = IntelligenceState(
        case_revision=case_revision,
        overall_status=_overall_status(
            medium=medium,
            material=material,
            challenge=challenge,
            document=document,
            rfq=rfq,
        ),
        medium=medium,
        material=material,
        challenge=challenge,
        document=document,
        rfq=rfq,
    )
    overview_source = IntelligenceSlice(
        slice_id="challenge",
        status=intelligence_state.overall_status,
        claim_level="case_projection",
        summary=(
            primary_question
            or challenge.summary
            or material.summary
            or "Workspace wartet auf den naechsten fallbezogenen Input."
        ),
        signals=_strings(
            [medium.summary, material.summary, challenge.summary], limit=5
        ),
        blockers=_strings(
            [*challenge.blockers, *material.blockers, *rfq.blockers], limit=8
        ),
        not_for_release_decisions=True,
    )
    tab_state = [
        _tab(
            tab_id="overview",
            label="Ueberblick",
            source=overview_source,
            next_action=primary_question or None,
        ),
        _tab(
            tab_id="parameters",
            label="Parameter",
            source=parameter_source,
            next_action=primary_question or None,
        ),
        _tab(tab_id="medium", label="Medium", source=medium),
        _tab(tab_id="material", label="Werkstoff", source=material),
        _tab(
            tab_id="challenge",
            label="Challenge",
            source=challenge,
            next_action=primary_question or None,
        ),
        _tab(tab_id="documents", label="Dokumente", source=document),
        _tab(tab_id="rfq", label="Anfragebasis", source=rfq),
    ]
    return V91WorkspaceProjection(
        intelligence_state=intelligence_state,
        tab_state=tab_state,
    )
