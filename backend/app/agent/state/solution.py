"""Deterministic SolutionProfile derivation (V1.8 §6.4 — Solution Companion).

Pure code: no LLM, no I/O, no side effects. The State Gate / post-graph commit
calls these helpers; modules never write case truth directly (single-writer).

Datasheet/offer document evidence (``DocumentEvidenceState.candidate_facts``,
already extracted by the v92 orchestrator) is projected into a candidate
``SolutionProfile`` per source document, with each field stamped
``origin="datasheet_extracted"`` and its source document (+ page, when the
candidate carries it). Candidates start ``pending_confirmation`` — never
``confirmed``: a datasheet value is an explanation, never a release
(Safety-Formel "laut Datenblatt …", Erklärung ≠ Freigabe).
"""

from __future__ import annotations

from typing import Any

from app.agent.state.models import (
    DocumentEvidenceState,
    SolutionField,
    SolutionProfile,
)

#: Document types whose extracted facts describe a *solution* (offer/datasheet),
#: not the requirement profile (drawing / sds stay requirement-side evidence).
_SOLUTION_DOC_TYPES = frozenset({"datasheet", "offer"})


def _document_types_by_ref(doc_evidence: DocumentEvidenceState) -> dict[str, str]:
    """Map ``document_ref → document_type`` from ``documents_seen``."""
    mapping: dict[str, str] = {}
    for doc in doc_evidence.documents_seen or []:
        if not isinstance(doc, dict):
            continue
        ref = str(doc.get("document_ref") or "").strip()
        if ref:
            mapping[ref] = str(doc.get("document_type") or "").strip()
    return mapping


def _coerce_page(fact: dict[str, Any]) -> int | None:
    """Source page, when the candidate carries one (chunk-level today)."""
    raw = fact.get("source_page") or fact.get("page") or fact.get("page_number")
    if isinstance(raw, bool):  # bool is an int subclass — reject it
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        return int(raw.strip())
    return None


def solution_profiles_from_document_evidence(
    doc_evidence: DocumentEvidenceState,
) -> list[SolutionProfile]:
    """Build candidate ``SolutionProfile``s (one per datasheet/offer document).

    Returns ``[]`` when no solution-document candidates are present, so the
    caller is a no-op for the inquiry half.
    """
    types_by_ref = _document_types_by_ref(doc_evidence)
    fields_by_doc: dict[str, list[SolutionField]] = {}

    for fact in doc_evidence.candidate_facts or []:
        if not isinstance(fact, dict):
            continue
        ref = str(fact.get("source_ref") or "").strip()
        field = fact.get("field")
        if not ref or not field:
            continue
        if types_by_ref.get(ref) not in _SOLUTION_DOC_TYPES:
            continue  # requirement-side evidence (drawing/sds/unknown) — skip
        fields_by_doc.setdefault(ref, []).append(
            SolutionField(
                field=str(field),
                value=fact.get("value"),
                status="pending_confirmation",
                origin="datasheet_extracted",
                source_doc=ref,
                source_page=_coerce_page(fact),
            )
        )

    return [
        SolutionProfile(
            solution_id=f"sol_doc_{ref}",
            label=f"Datenblatt {ref}",
            state="candidate",
            fields=fields_by_doc[ref],
        )
        for ref in sorted(fields_by_doc)
    ]


def merge_solution_profiles(
    existing: list[SolutionProfile],
    derived: list[SolutionProfile],
) -> list[SolutionProfile]:
    """Idempotent merge by ``solution_id``.

    A re-derived datasheet profile replaces its prior version (re-extraction is
    not a duplicate); profiles not in ``derived`` (e.g. manually curated or
    manufacturer-response ones) are preserved in their original order.
    """
    by_id: dict[str, SolutionProfile] = {p.solution_id: p for p in existing}
    order: list[str] = [p.solution_id for p in existing]
    for profile in derived:
        if profile.solution_id not in by_id:
            order.append(profile.solution_id)
        by_id[profile.solution_id] = profile
    return [by_id[solution_id] for solution_id in order]
