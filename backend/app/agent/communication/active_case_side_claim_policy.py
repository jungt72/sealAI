from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


_FORBIDDEN_CLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("final_freigegeben", re.compile(r"\bfinal(?:e|er|es)?\s+freigegeben\b", re.IGNORECASE)),
    ("technisch_freigegeben", re.compile(r"\btechnisch\s+freigegeben\b", re.IGNORECASE)),
    ("freigegeben", re.compile(r"\bfreigegeben\b", re.IGNORECASE)),
    ("zugelassen", re.compile(r"\bzugelassen\b", re.IGNORECASE)),
    ("zertifiziert", re.compile(r"\bzertifiziert\b", re.IGNORECASE)),
    ("garantiert_geeignet", re.compile(r"\bgarantiert\s+geeignet\b", re.IGNORECASE)),
    ("garantiert_bestaendig", re.compile(r"\bgarantiert\s+best[aä]ndig\b", re.IGNORECASE)),
    ("beste_loesung", re.compile(r"\bbeste\s+l(?:oe|ö)sung\b", re.IGNORECASE)),
    ("endgueltige_loesung", re.compile(r"\b(?:endg(?:ue|ü)ltige|finale)\s+l(?:oe|ö)sung\b", re.IGNORECASE)),
    ("validated_solution", re.compile(r"\bvalidated\s+solution\b", re.IGNORECASE)),
    ("approved_solution", re.compile(r"\bapproved\s+solution\b", re.IGNORECASE)),
    ("certified_recommendation", re.compile(r"\bcertified\s+recommendation\b", re.IGNORECASE)),
    ("final_approval", re.compile(r"\bfinal\s+approval\b", re.IGNORECASE)),
    ("guaranteed_suitable", re.compile(r"\bguaranteed\s+suitable\b", re.IGNORECASE)),
    ("sicher_geeignet", re.compile(r"\bsicher\s+geeignet\b", re.IGNORECASE)),
)


_MATERIAL_TOKENS = ("fkm", "nbr", "epdm", "ptfe", "ffkm", "vmq", "hnbr")
_MAX_EVIDENCE_SNIPPET_CHARS = 220


@dataclass(frozen=True, slots=True)
class ActiveCaseSideEvidenceContext:
    evidence_available: bool = False
    evidence_refs: tuple[str, ...] = ()
    source_titles: tuple[str, ...] = ()
    short_evidence_snippets: tuple[str, ...] = ()
    source_validation_status: tuple[str, ...] = ()
    retrieval_query: str | None = None
    evidence_fallback_reason: str | None = None

    def as_trace(self) -> dict[str, Any]:
        return {
            "evidence_context_built": True,
            "evidence_context_available": self.evidence_available,
            "evidence_refs_count": len(self.evidence_refs),
            "evidence_source_validation_status": list(self.source_validation_status),
            "evidence_fallback_reason": self.evidence_fallback_reason,
        }


@dataclass(frozen=True, slots=True)
class ActiveCaseSideEvidenceEnrichmentResult:
    answer_markdown: str
    evidence_used_in_answer: bool = False


@dataclass(frozen=True, slots=True)
class SpeakableCaseFact:
    field_name: str
    value: Any
    fact_status: str
    provenance: str
    confidence: str
    evidence_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ActiveCaseSideSpeakableFacts:
    known_case_facts: tuple[SpeakableCaseFact, ...] = ()
    pending_question_field: str | None = None
    pending_question_text: str | None = None
    missing_fields: tuple[str, ...] = ()
    calculated_values: tuple[SpeakableCaseFact, ...] = ()
    uncertainty_notes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    evidence_context: ActiveCaseSideEvidenceContext | None = None
    forbidden_claims: tuple[str, ...] = field(
        default_factory=lambda: tuple(name for name, _pattern in _FORBIDDEN_CLAIM_PATTERNS)
    )
    required_qualification_phrases: tuple[str, ...] = (
        "vorlaeufige technische Einordnung",
        "Herstellerpruefung oder Spezialistenpruefung",
        "keine technische Freigabe",
    )

    @property
    def evidence_context_available(self) -> bool:
        return bool(self.evidence_refs) or bool(
            self.evidence_context and self.evidence_context.evidence_available
        )

    def as_trace(self) -> dict[str, Any]:
        return {
            "known_case_fact_count": len(self.known_case_facts),
            "missing_field_count": len(self.missing_fields),
            "calculated_value_count": len(self.calculated_values),
            "evidence_context_available": self.evidence_context_available,
        }


@dataclass(frozen=True, slots=True)
class ActiveCaseSideClaimPolicyResult:
    answer_markdown: str
    claim_policy_result: str
    forbidden_claims_detected: tuple[str, ...] = ()
    answer_safety_rewritten: bool = False
    answer_safety_fallback_used: bool = False
    speakable_facts_built: bool = True
    claim_policy_applied: bool = True
    evidence_context_available: bool = False

    def as_trace(self) -> dict[str, Any]:
        return {
            "speakable_facts_built": self.speakable_facts_built,
            "claim_policy_applied": self.claim_policy_applied,
            "claim_policy_result": self.claim_policy_result,
            "forbidden_claims_detected": list(self.forbidden_claims_detected),
            "answer_safety_rewritten": self.answer_safety_rewritten,
            "answer_safety_fallback_used": self.answer_safety_fallback_used,
            "evidence_context_available": self.evidence_context_available,
        }


def build_active_case_side_speakable_facts(
    governed_state: Any | None,
    *,
    evidence_context: ActiveCaseSideEvidenceContext | None = None,
) -> ActiveCaseSideSpeakableFacts:
    pending = getattr(governed_state, "pending_question", None) if governed_state is not None else None
    pending_field = str(getattr(pending, "target_field", "") or "").strip() or None
    pending_text = str(getattr(pending, "question_text", "") or "").strip() or None

    asserted = getattr(governed_state, "asserted", None) if governed_state is not None else None
    assertions = getattr(asserted, "assertions", {}) or {}
    known_facts: list[SpeakableCaseFact] = []
    evidence_refs: list[str] = []
    for field_name, claim in sorted(assertions.items()):
        value = getattr(claim, "asserted_value", None)
        if value is None or str(value).strip() == "":
            continue
        refs = tuple(str(ref) for ref in list(getattr(claim, "evidence_refs", []) or []) if str(ref).strip())
        evidence_refs.extend(ref for ref in refs if ref not in evidence_refs)
        known_facts.append(
            SpeakableCaseFact(
                field_name=str(field_name),
                value=value,
                fact_status=str(getattr(claim, "status", "") or "confirmed"),
                provenance=str(getattr(claim, "provenance", "") or "confirmed"),
                confidence=str(getattr(claim, "confidence", "") or "confirmed"),
                evidence_refs=refs,
            )
        )

    missing_fields: list[str] = []
    for field in list(getattr(asserted, "blocking_unknowns", []) or []):
        field_name = str(field or "").strip()
        if field_name and field_name not in missing_fields:
            missing_fields.append(field_name)
    if pending_field and pending_field not in {fact.field_name for fact in known_facts} and pending_field not in missing_fields:
        missing_fields.append(pending_field)

    uncertainty_notes: list[str] = []
    if missing_fields:
        uncertainty_notes.append("case_incomplete_missing_fields")
    if pending_field:
        uncertainty_notes.append("pending_question_active")

    return ActiveCaseSideSpeakableFacts(
        known_case_facts=tuple(known_facts),
        pending_question_field=pending_field,
        pending_question_text=pending_text,
        missing_fields=tuple(missing_fields),
        uncertainty_notes=tuple(uncertainty_notes),
        evidence_refs=tuple(dict.fromkeys(evidence_refs + list(getattr(evidence_context, "evidence_refs", ()) or ()))),
        evidence_context=evidence_context,
    )


def build_active_case_side_evidence_context(
    *,
    knowledge_response: Any | None,
    latest_user_message: str,
) -> ActiveCaseSideEvidenceContext:
    answer_view = getattr(knowledge_response, "knowledge_answer_view", None)
    evidence_items = list(getattr(answer_view, "knowledge_evidence", ()) or ())
    citations = list(getattr(knowledge_response, "citations", ()) or ())
    refs: list[str] = []
    titles: list[str] = []
    snippets: list[str] = []
    statuses: list[str] = []

    for item in evidence_items:
        source_type = str(getattr(item, "source_type", "") or "").strip()
        if source_type not in {"rag", "fact_card"}:
            continue
        title = _safe_text(getattr(item, "title", None) or getattr(item, "source_name", None))
        snippet = _safe_text(getattr(item, "content", None), limit=_MAX_EVIDENCE_SNIPPET_CHARS)
        ref = title or str(getattr(item, "source_name", "") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
        if title and title not in titles:
            titles.append(title)
        if snippet and snippet not in snippets:
            snippets.append(snippet)

    for source in citations:
        title = _safe_text(getattr(source, "title", None))
        source_id = _safe_text(getattr(source, "source_id", None))
        evidence_ref = _safe_text(getattr(source, "evidence_ref", None))
        snippet = _safe_text(getattr(source, "excerpt", None), limit=_MAX_EVIDENCE_SNIPPET_CHARS)
        ref = evidence_ref or source_id or title
        if ref and ref not in refs:
            refs.append(ref)
        if title and title not in titles:
            titles.append(title)
        if snippet and snippet not in snippets:
            snippets.append(snippet)
        status = str(getattr(getattr(source, "validation_status", None), "value", getattr(source, "validation_status", "") or "")).strip()
        if status and status not in statuses:
            statuses.append(status)

    for badge in tuple(getattr(answer_view, "source_validation_badges", ()) or ()):
        status = str(getattr(getattr(badge, "validation_status", None), "value", getattr(badge, "validation_status", "") or "")).strip()
        if status and status not in statuses:
            statuses.append(status)

    evidence_available = bool(refs or titles or snippets)
    fallback_reason = None
    if not evidence_available:
        fallback_reason = "rag_miss" if bool(getattr(answer_view, "rag_miss", False)) else "no_retrieval_evidence_available"

    return ActiveCaseSideEvidenceContext(
        evidence_available=evidence_available,
        evidence_refs=tuple(refs[:3]),
        source_titles=tuple(titles[:3]),
        short_evidence_snippets=tuple(snippets[:3]),
        source_validation_status=tuple(statuses[:3]) or (("documented",) if evidence_available else ()),
        retrieval_query=_safe_text(latest_user_message, limit=160) or None,
        evidence_fallback_reason=fallback_reason,
    )


def enrich_active_case_side_answer_with_evidence(
    *,
    latest_user_message: str,
    answer_markdown: str,
    evidence_context: ActiveCaseSideEvidenceContext,
) -> ActiveCaseSideEvidenceEnrichmentResult:
    answer = str(answer_markdown or "").strip()
    if not evidence_context.evidence_available:
        return ActiveCaseSideEvidenceEnrichmentResult(answer_markdown=answer)
    answer_lower = _normalize(answer)
    if any(token in answer_lower for token in ("evidenzkontext", "quelle", "dokumentiert", "rag")):
        return ActiveCaseSideEvidenceEnrichmentResult(
            answer_markdown=answer,
            evidence_used_in_answer=True,
        )
    title = evidence_context.source_titles[0] if evidence_context.source_titles else "dokumentierter Wissenskontext"
    snippet = evidence_context.short_evidence_snippets[0] if evidence_context.short_evidence_snippets else ""
    context_line = (
        f"Evidenzkontext: {title} stuetzt diese allgemeine Einordnung"
        if not snippet
        else f"Evidenzkontext: {title}: {snippet}"
    )
    context_line += (
        ". Ich nutze diesen Kontext als Orientierung fuer die Anfragebasis, "
        "nicht als technische Freigabe oder abschliessende Eignungsaussage."
    )
    return ActiveCaseSideEvidenceEnrichmentResult(
        answer_markdown=f"{answer}\n\n{context_line}".strip(),
        evidence_used_in_answer=True,
    )


def enforce_active_case_side_claim_policy(
    *,
    latest_user_message: str,
    answer_markdown: str,
    speakable_facts: ActiveCaseSideSpeakableFacts,
) -> ActiveCaseSideClaimPolicyResult:
    answer = str(answer_markdown or "").strip()
    forbidden = tuple(_detect_forbidden_claims(answer))
    if forbidden:
        return ActiveCaseSideClaimPolicyResult(
            answer_markdown=_deterministic_safe_side_answer(
                latest_user_message=latest_user_message,
                speakable_facts=speakable_facts,
            ),
            claim_policy_result="fallback",
            forbidden_claims_detected=forbidden,
            answer_safety_fallback_used=True,
            evidence_context_available=speakable_facts.evidence_context_available,
        )

    enriched = _ensure_required_context(
        latest_user_message=latest_user_message,
        answer_markdown=answer,
        speakable_facts=speakable_facts,
    )
    forbidden_after_enrichment = tuple(_detect_forbidden_claims(enriched))
    if forbidden_after_enrichment:
        return ActiveCaseSideClaimPolicyResult(
            answer_markdown=_deterministic_safe_side_answer(
                latest_user_message=latest_user_message,
                speakable_facts=speakable_facts,
            ),
            claim_policy_result="fallback",
            forbidden_claims_detected=forbidden_after_enrichment,
            answer_safety_fallback_used=True,
            evidence_context_available=speakable_facts.evidence_context_available,
        )

    rewritten = enriched != answer
    return ActiveCaseSideClaimPolicyResult(
        answer_markdown=enriched,
        claim_policy_result="rewritten" if rewritten else "passed",
        answer_safety_rewritten=rewritten,
        evidence_context_available=speakable_facts.evidence_context_available,
    )


def _detect_forbidden_claims(text: str) -> list[str]:
    detected: list[str] = []
    for name, pattern in _FORBIDDEN_CLAIM_PATTERNS:
        for match in pattern.finditer(text or ""):
            if _is_negated_or_scoped(text, match.start(), match.end()):
                continue
            detected.append(name)
            break
    return detected


def _is_negated_or_scoped(text: str, start: int, end: int) -> bool:
    lowered = (text or "").casefold()
    before = lowered[max(0, start - 48):start]
    after = lowered[end:end + 48]
    if any(token in before for token in ("keine ", "kein ", "nicht ", "ohne ", "no ")):
        return True
    return any(token in after for token in (" nur durch hersteller", " muss geprueft", " muss geprüft"))


def _ensure_required_context(
    *,
    latest_user_message: str,
    answer_markdown: str,
    speakable_facts: ActiveCaseSideSpeakableFacts,
) -> str:
    additions: list[str] = []
    message = _normalize(latest_user_message)
    answer = str(answer_markdown or "").strip()
    answer_lower = _normalize(answer)

    if _is_medium_question(message) and not any(
        token in answer_lower
        for token in ("bestaendigkeit", "beständigkeit", "quellung", "verschleiss", "verschleiß", "reibung", "schmierung", "korrosion")
    ):
        additions.append(
            "Fuer die Dichtung ist das Medium wichtig, weil es Werkstoffbestaendigkeit, "
            "Quellung, Verschleiss, Reibung, Schmierung, Korrosion und die Qualitaet der Anfragebasis beeinflusst."
        )
    if (
        _is_medium_question(message)
        and "medium" in speakable_facts.missing_fields
        and "ich setze kein medium voraus" not in answer_lower
        and not _message_contains_explicit_medium_answer(message)
    ):
        additions.append("Ich setze dabei kein Medium voraus; dieser Wert ist im aktuellen Fall noch offen.")

    if _is_temperature_question(message) and "werkstoff" not in answer_lower:
        additions.append(
            "Temperatur beeinflusst Werkstoffverhalten, Alterung, Haerte, Reibung und Sicherheitsreserven; "
            "die Bewertung bleibt ohne Medium, Druck, Bewegung und Einbauraum vorlaeufig."
        )

    if _is_material_question(message) and not any(token in answer_lower for token in ("hersteller", "spezialist", "spezialisten", "pruef", "prüf")):
        additions.append(_manufacturer_review_phrase())
    elif _is_material_question(message) and "keine technische freigabe" not in answer_lower:
        additions.append("Das ist keine technische Freigabe und keine abschliessende Werkstoffauswahl.")

    if not additions:
        return answer
    return f"{answer}\n\n" + "\n\n".join(additions)


def _deterministic_safe_side_answer(
    *,
    latest_user_message: str,
    speakable_facts: ActiveCaseSideSpeakableFacts,
) -> str:
    message = _normalize(latest_user_message)
    if _is_material_question(message):
        materials = _extract_material_tokens(message)
        label = " und ".join(materials[:2]).upper() if len(materials) >= 2 else "die genannten Werkstoffe"
        return (
            f"Als vorlaeufige technische Einordnung zu {label}: FKM wird haeufig betrachtet, wenn Oele, "
            "Kraftstoffe, Temperatur oder chemische Belastung eine Rolle spielen. NBR wird haeufig bei "
            "Oelen, Fetten und moderaten Bedingungen betrachtet. PTFE ist eher ein chemisch breiter "
            "einsetzbarer Hochleistungswerkstoff, aber mit anderem mechanischem Verhalten. "
            "Die konkrete Bewertung haengt von Medium, Temperatur, Druck, Bewegung, Drehzahl, Welle, "
            "Einbauraum und Compliance-Anforderungen ab.\n\n"
            f"{_manufacturer_review_phrase()}"
        )
    if _is_medium_question(message):
        return (
            "Mit Medium ist der Stoff oder die Kontaktumgebung gemeint, der die Dichtung ausgesetzt ist. "
            "Das kann z. B. Wasser, Oel, Gas, Dampf, Reinigungsmedium oder eine Chemikalie sein. "
            "Das Medium beeinflusst Werkstoffbestaendigkeit, Quellung, Verschleiss, Reibung, Schmierung, "
            "Korrosion und die Qualitaet der Anfragebasis. Ich setze dabei kein Medium voraus; dieser Wert "
            "ist im aktuellen Fall noch offen."
        )
    if _is_temperature_question(message):
        return (
            "Die Temperatur ist wichtig, weil sie Werkstoffverhalten, Alterung, Haerte, Reibung und "
            "Sicherheitsreserven beeinflusst. Ohne Medium, Druck, Bewegung und Einbauraum bleibt das eine "
            "vorlaeufige technische Einordnung fuer die Anfragebasis."
        )
    pending_field = speakable_facts.pending_question_field or "naechste Angabe"
    return (
        "Ich kann das als vorlaeufige technische Einordnung erklaeren, ohne daraus eine technische "
        f"Freigabe oder einen bestaetigten Fallwert zu machen. Fuer die Anfragebasis bleibt {pending_field} "
        "als offener Punkt relevant."
    )


def _manufacturer_review_phrase() -> str:
    return (
        "Das ist eine vorlaeufige technische Einordnung fuer die Anfragebasis; "
        "die konkrete Auswahl muss durch Herstellerpruefung oder Spezialistenpruefung erfolgen."
    )


def _is_material_question(normalized_message: str) -> bool:
    material_count = len(_extract_material_tokens(normalized_message))
    return material_count >= 2 or any(
        phrase in normalized_message
        for phrase in ("vergleich", "unterschied zwischen", "unterschied von")
    )


def _is_medium_question(normalized_message: str) -> bool:
    return "medium" in normalized_message and any(
        phrase in normalized_message
        for phrase in ("was bedeutet", "warum", "wieso", "weshalb", "wichtige", "wichtig")
    )


def _is_temperature_question(normalized_message: str) -> bool:
    return "temperatur" in normalized_message and any(
        phrase in normalized_message
        for phrase in ("warum", "wieso", "weshalb", "rolle", "wichtig")
    )


def _extract_material_tokens(normalized_message: str) -> list[str]:
    seen: list[str] = []
    for token in _MATERIAL_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", normalized_message, re.IGNORECASE) and token not in seen:
            seen.append(token)
    return seen


def _message_contains_explicit_medium_answer(normalized_message: str) -> bool:
    return bool(
        re.search(
            r"\b(?:das\s+)?medium\s+(?:ist|waere|wäre|is|=|:)\s+\S+",
            normalized_message,
            re.IGNORECASE,
        )
    )


def _safe_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    return text[:limit].rstrip()


def _normalize(text: str) -> str:
    return " ".join(str(text or "").casefold().split())
