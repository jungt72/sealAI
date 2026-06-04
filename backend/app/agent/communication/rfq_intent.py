from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.domain.checks_registry import build_registered_check_results
from app.agent.communication.templates import render_communication_template
from app.agent.communication.v7_contracts import RuntimeActionType
from app.agent.v92.calculation_projection import calculation_ledger_derivations


@dataclass(frozen=True, slots=True)
class RfqReadinessIntent:
    detected: bool
    rfq_action_type: str = "none"
    reason: str = ""
    asks_readiness: bool = False
    asks_missing_fields: bool = False
    asks_build_basis: bool = False
    asks_preview_or_pdf: bool = False
    asks_external_contact: bool = False

    def as_trace(self) -> dict[str, Any]:
        return {
            "rfq_intent_detected": self.detected,
            "rfq_action_type": self.rfq_action_type,
            "rfq_intent_reason": self.reason,
            "rfq_asks_readiness": self.asks_readiness,
            "rfq_asks_missing_fields": self.asks_missing_fields,
            "rfq_asks_build_basis": self.asks_build_basis,
            "rfq_asks_preview_or_pdf": self.asks_preview_or_pdf,
            "rfq_asks_external_contact": self.asks_external_contact,
        }


@dataclass(frozen=True, slots=True)
class RfqReadinessAnswer:
    answer_markdown: str
    rfq_action_type: str
    action_type: RuntimeActionType
    projection: "RfqReadinessProjection"
    trace: dict[str, Any]


class RfqReadinessProjection(BaseModel):
    manufacturer_review_ready: bool = False
    rfq_basis_ready: bool = False
    readiness_band: str = "in_progress"
    known_missing_fields: list[str] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    pending_question: dict[str, str | None] | None = None
    known_case_facts_count: int = 0
    known_case_summary: list[str] = Field(default_factory=list)
    professional_check_groups: list[dict[str, Any]] = Field(default_factory=list)
    professional_check_blockers: list[str] = Field(default_factory=list)
    evidence_status: str = "not_available"
    consent_required: bool = True
    dispatch_allowed: bool = False
    external_contact_allowed: bool = False
    final_approval_claim_allowed: bool = False
    preview_available: bool = False
    preview_possible: bool = False
    preview_id: str | None = None
    preview_requires_explicit_endpoint: bool = True
    preview_action_available: bool = False
    preview_action_name: str = "create_rfq_preview"
    preview_endpoint: str = "/api/v1/rfq/preview"
    preview_creation_requires_explicit_user_intent: bool = True
    preview_export_requires_consent: bool = True
    preview_service_boundary: str = "RfqPreviewService.create_preview_for_case"
    preview_blocking_reason: str | None = None
    projection_source: str = "governed_session_state"
    projection_version: str = "rfq_readiness_projection_v1"

    model_config = ConfigDict(extra="forbid")

    def as_trace(self) -> dict[str, Any]:
        return {
            "rfq_readiness_projection_built": True,
            "manufacturer_review_ready": self.manufacturer_review_ready,
            "rfq_basis_ready": self.rfq_basis_ready,
            "readiness_band": self.readiness_band,
            "known_missing_fields_count": len(self.known_missing_fields),
            "open_points_count": len(self.open_points),
            "blocking_reasons_count": len(self.blocking_reasons),
            "known_case_facts_count": self.known_case_facts_count,
            "professional_check_groups_count": len(self.professional_check_groups),
            "professional_check_blockers_count": len(self.professional_check_blockers),
            "evidence_status": self.evidence_status,
            "preview_available": self.preview_available,
            "preview_possible": self.preview_possible,
            "preview_id": self.preview_id,
            "preview_requires_explicit_endpoint": self.preview_requires_explicit_endpoint,
            "preview_action_available": self.preview_action_available,
            "preview_action_name": self.preview_action_name,
            "preview_endpoint": self.preview_endpoint,
            "preview_creation_requires_explicit_user_intent": self.preview_creation_requires_explicit_user_intent,
            "preview_export_requires_consent": self.preview_export_requires_consent,
            "preview_service_boundary": self.preview_service_boundary,
            "preview_blocking_reason": self.preview_blocking_reason,
            "projection_source": self.projection_source,
            "projection_version": self.projection_version,
        }

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def classify_rfq_readiness_intent(message: str) -> RfqReadinessIntent:
    text = _normalize(message)
    if not text:
        return RfqReadinessIntent(detected=False)

    has_rfq_term = any(
        term in text
        for term in (
            "rfq",
            "anfrage",
            "anfragebasis",
            "angebot",
            "hersteller",
            "pdf",
        )
    )
    asks_missing = "was fehlt" in text or "offene punkte" in text
    asks_ready = any(
        term in text
        for term in (
            "vollstaendig",
            "bereit",
            "reif",
            "readiness",
            "rfq ready",
            "anfrage ready",
        )
    )
    asks_preview = any(
        term in text for term in ("pdf", "vorschau", "preview", "export", "dokument")
    )
    asks_build = any(
        term in text
        for term in (
            "erstelle",
            "erstellen",
            "mach daraus",
            "vorbereiten",
            "anfragebasis erstellen",
            "rfq vorbereiten",
        )
    )
    asks_contact = any(
        term in text
        for term in (
            "senden",
            "schicken",
            "verschicken",
            "weiterleiten",
            "kontaktieren",
            "an hersteller",
            "zum hersteller",
            "hersteller schicken",
        )
    )

    if asks_contact and (has_rfq_term or "das" in text):
        return RfqReadinessIntent(
            detected=True,
            rfq_action_type="external_contact_request",
            reason="deterministic_external_contact_or_send_request",
            asks_external_contact=True,
        )
    if asks_missing and (has_rfq_term or "hersteller" in text):
        return RfqReadinessIntent(
            detected=True,
            rfq_action_type="show_missing_fields",
            reason="deterministic_missing_fields_for_manufacturer_request",
            asks_missing_fields=True,
            asks_readiness=True,
        )
    if asks_ready and has_rfq_term:
        return RfqReadinessIntent(
            detected=True,
            rfq_action_type="show_readiness",
            reason="deterministic_rfq_readiness_question",
            asks_readiness=True,
        )
    if asks_preview and has_rfq_term:
        return RfqReadinessIntent(
            detected=True,
            rfq_action_type="build_preview_or_pdf",
            reason="deterministic_rfq_preview_or_pdf_request",
            asks_preview_or_pdf=True,
        )
    if asks_build and has_rfq_term:
        return RfqReadinessIntent(
            detected=True,
            rfq_action_type="build_rfq_basis",
            reason="deterministic_rfq_basis_creation_request",
            asks_build_basis=True,
        )

    return RfqReadinessIntent(detected=False)


def build_rfq_readiness_answer(
    *,
    latest_user_message: str,
    governed_state: Any | None,
    intent: RfqReadinessIntent,
) -> RfqReadinessAnswer:
    projection = build_rfq_readiness_projection(
        governed_state=governed_state,
        intent=intent,
    )
    active_case_exists = projection.projection_source != "no_active_case"
    missing_fields = tuple(projection.known_missing_fields)
    pending = projection.pending_question or {}
    pending_field = str(pending.get("target_field") or "").strip() or None
    pending_question = str(pending.get("question_text") or "").strip() or None
    rfq_ready = projection.rfq_basis_ready
    rfq_admissible = _bool_attr(
        getattr(governed_state, "governance", None), "rfq_admissible"
    )
    dispatch_ready = _bool_attr(
        getattr(governed_state, "dispatch", None), "dispatch_ready"
    )
    action_type = _runtime_action_type(
        intent=intent,
        active_case_exists=active_case_exists,
        has_missing=bool(missing_fields),
    )

    if not active_case_exists:
        answer = render_communication_template(
            "rfq_readiness_answer",
            {"mode": "no_active_case"},
            fallback=(
                "Ich kann eine Anfragebasis oder RFQ-Basis vorbereiten, aber dafuer brauche ich zuerst "
                "einen qualifizierten Dichtungsfall. Ohne Fall, Revision und technische Eckdaten erstelle "
                "ich keine Herstelleranfrage und sende nichts extern.\n\n"
                "Der sichere naechste Schritt ist die Qualifikation: Um welche Dichtung oder Anwendung geht es?"
            ),
        )
    elif intent.asks_external_contact:
        answer = _active_contact_answer(
            missing_fields=missing_fields,
            pending_question=pending_question,
            rfq_ready=rfq_ready,
            dispatch_ready=dispatch_ready,
        )
    elif intent.asks_build_basis or intent.asks_preview_or_pdf:
        answer = _active_build_answer(
            missing_fields=missing_fields,
            pending_question=pending_question,
            rfq_ready=rfq_ready,
            preview_requested=intent.asks_preview_or_pdf,
        )
    else:
        answer = _active_readiness_answer(
            missing_fields=missing_fields,
            pending_question=pending_question,
            rfq_ready=rfq_ready,
        )

    trace = {
        **intent.as_trace(),
        "rfq_readiness_builder": "deterministic_rfq_readiness_v1",
        "active_case_exists": active_case_exists,
        "rfq_ready": rfq_ready,
        "rfq_admissible": rfq_admissible,
        "dispatch_ready": dispatch_ready,
        "rfq_known_missing_fields": list(missing_fields),
        "rfq_known_missing_fields_count": len(missing_fields),
        "pending_question_available": bool(pending_question),
        "pending_question_target_field": pending_field,
        "pending_question_restored": bool(pending_question and missing_fields),
        "consent_required": True,
        "dispatch_allowed": False,
        "external_contact_allowed": False,
        "manufacturer_review_framing": True,
        "final_approval_claim_allowed": False,
        "rfq_preview_invoked": False,
        "case_delta_allowed": False,
        "governed_graph_bypassed": True,
        "latest_user_question_answered": True,
        "latest_user_message_classified_as_rfq_readiness": True,
    }
    trace.update(projection.as_trace())
    return RfqReadinessAnswer(
        answer_markdown=answer.strip(),
        rfq_action_type=intent.rfq_action_type,
        action_type=action_type,
        projection=projection,
        trace=trace,
    )


def build_rfq_readiness_projection(
    *,
    governed_state: Any | None,
    intent: RfqReadinessIntent,
) -> RfqReadinessProjection:
    active_case_exists = _active_case_exists(governed_state)
    if not active_case_exists:
        return RfqReadinessProjection(
            manufacturer_review_ready=False,
            rfq_basis_ready=False,
            preview_possible=False,
            preview_available=False,
            preview_requires_explicit_endpoint=True,
            preview_action_available=False,
            preview_blocking_reason="no_active_case",
            projection_source="no_active_case",
        )

    missing_fields = list(_missing_fields(governed_state))
    open_points = list(_open_points(governed_state))
    professional_projection = _professional_check_projection(governed_state)
    professional_check_groups = list(professional_projection["groups"])
    professional_check_blockers = list(professional_projection["blockers"])
    for blocker in professional_check_blockers:
        if blocker not in open_points:
            open_points.append(blocker)
    governance = getattr(governed_state, "governance", None)
    # §12.6: consume the reducer's collapsed conflict-severity verdict (gov_class)
    # as the single source — never re-derive the safety/value split here.
    gov_class = str(getattr(governance, "gov_class", "") or "")
    blocking_reasons = list(
        _blocking_reasons(
            governed_state, missing_fields, open_points, gov_class=gov_class
        )
    )
    for blocker in professional_check_blockers:
        if blocker not in blocking_reasons:
            blocking_reasons.append(blocker)
    pending = _pending_question(governed_state)
    known_summary = _known_case_summary(governed_state)
    rfq_ready = _bool_attr(getattr(governed_state, "rfq", None), "rfq_ready")
    rfq_admissible = _bool_attr(governance, "rfq_admissible")
    export_profile = getattr(governed_state, "export_profile", None)
    export_rfq_ready = _bool_attr(export_profile, "rfq_ready")
    # Clean ready = Class A / explicitly rfq-ready, with no remaining hard blocker.
    clean_ready = bool(
        (rfq_ready or rfq_admissible or gov_class == "A" or export_rfq_ready)
        and not blocking_reasons
    )
    # Class B = RFQ admissible with acknowledged open points (degraded value
    # conflict). Manufacturer-review-ready stays strict (clean only); the RFQ
    # basis itself is available for both A and B, so the preview button and the
    # tile agree instead of contradicting.
    manufacturer_review_ready = clean_ready
    rfq_basis_ready = bool(clean_ready or gov_class in ("A", "B"))
    if clean_ready:
        readiness_band = "rfq_ready"
    elif gov_class in ("A", "B"):
        readiness_band = "rfq_with_open_points"
    elif gov_class == "C":
        readiness_band = "blocked"
    else:
        readiness_band = "in_progress"
    preview_possible = bool(active_case_exists)
    preview_blocking_reason = (
        "preview_creation_requires_durable_case_endpoint_and_consent_flow"
        if intent.asks_build_basis or intent.asks_preview_or_pdf
        else "preview_not_requested"
    )
    if not preview_possible:
        preview_blocking_reason = "no_active_case"

    return RfqReadinessProjection(
        manufacturer_review_ready=manufacturer_review_ready,
        rfq_basis_ready=rfq_basis_ready,
        readiness_band=readiness_band,
        known_missing_fields=missing_fields,
        open_points=open_points,
        blocking_reasons=blocking_reasons,
        pending_question=pending or None,
        known_case_facts_count=_known_case_fact_count(governed_state),
        known_case_summary=known_summary,
        professional_check_groups=professional_check_groups,
        professional_check_blockers=professional_check_blockers,
        evidence_status=str(professional_projection["evidence_status"]),
        consent_required=True,
        dispatch_allowed=False,
        external_contact_allowed=False,
        final_approval_claim_allowed=False,
        preview_available=False,
        preview_possible=preview_possible,
        preview_id=None,
        preview_requires_explicit_endpoint=True,
        preview_action_available=preview_possible,
        preview_action_name="create_rfq_preview",
        preview_endpoint="/api/v1/rfq/preview",
        preview_creation_requires_explicit_user_intent=True,
        preview_export_requires_consent=True,
        preview_service_boundary="RfqPreviewService.create_preview_for_case",
        preview_blocking_reason=preview_blocking_reason,
        projection_source="governed_session_state",
    )


def _active_readiness_answer(
    *,
    missing_fields: tuple[str, ...],
    pending_question: str | None,
    rfq_ready: bool,
) -> str:
    if rfq_ready and not missing_fields:
        return render_communication_template(
            "rfq_readiness_answer",
            {"mode": "readiness_ready"},
            fallback=(
                "Deine Anfragebasis wirkt aus dem aktuellen governed State grundsaetzlich fuer eine "
                "Herstellerpruefung vorbereitet. Das ist keine technische Endentscheidung und kein "
                "automatischer Herstellerentscheid; vor externem Teilen braucht es weiterhin den geregelten "
                "RFQ-/Consent-Schritt.\n\n"
                "Ich sende nichts automatisch an Hersteller."
            ),
        )
    open_points = _open_points_text(missing_fields)
    return render_communication_template(
        "rfq_readiness_answer",
        {
            "mode": "readiness_open",
            "open_points": open_points,
            "pending_question": pending_question,
        },
        fallback=(
            "Die Anfragebasis ist fuer eine Herstellerpruefung noch nicht vollstaendig genug. "
            "Ich kann den RFQ-Status nur aus dem vorhandenen governed State ableiten und erfinde keine "
            f"fehlenden Werte.\n\nOffene Punkte: {open_points}.\n\n"
            "Das ist eine RFQ-Basis fuer die Klaerung mit einem Hersteller oder Spezialisten, keine technische Endentscheidung."
            + (
                f"\n\nDer naechste sinnvolle Schritt bleibt: {pending_question}"
                if pending_question
                else ""
            )
        ),
    )


def _active_build_answer(
    *,
    missing_fields: tuple[str, ...],
    pending_question: str | None,
    rfq_ready: bool,
    preview_requested: bool,
) -> str:
    artifact = "PDF-/RFQ-Vorschau" if preview_requested else "Anfragebasis"
    if rfq_ready and not missing_fields:
        return render_communication_template(
            "rfq_readiness_answer",
            {"mode": "build_ready", "artifact": artifact},
            fallback=(
                f"Ich kann die {artifact} als prueffaehigen Anfrageentwurf vorbereiten, "
                "aber die dauerhafte Anfragevorschau entsteht erst ueber die explizite Aktion "
                "'Anfragevorschau vorbereiten'. Das Teilen oder Exportieren laeuft danach ueber den "
                "geregelten Preview- und Consent-Fluss. "
                "Ich sende nichts automatisch extern und treffe keine technische Endentscheidung."
            ),
        )
    open_points = _open_points_text(missing_fields)
    return render_communication_template(
        "rfq_readiness_answer",
        {
            "mode": "build_open",
            "artifact": artifact,
            "open_points": open_points,
            "pending_question": pending_question,
        },
        fallback=(
            f"Ich kann daraus eine {artifact} vorbereiten, aber im aktuellen Fall fehlen noch Angaben "
            f"fuer eine belastbare Herstellerpruefung. Offene Punkte: {open_points}.\n\n"
            "Sobald die Pflichtangaben im governed Fall sauber vorliegen, kann daraus eine RFQ-Basis fuer "
            "die Herstellerpruefung entstehen. Die dauerhafte Anfragevorschau wird ueber die explizite "
            "Aktion 'Anfragevorschau vorbereiten' erstellt. Das ist keine technische Endentscheidung "
            "und kein automatischer Versand."
            + (
                f"\n\nDer naechste sinnvolle Schritt bleibt: {pending_question}"
                if pending_question
                else ""
            )
        ),
    )


def _active_contact_answer(
    *,
    missing_fields: tuple[str, ...],
    pending_question: str | None,
    rfq_ready: bool,
    dispatch_ready: bool,
) -> str:
    open_points = _open_points_text(missing_fields)
    status = (
        "Die Anfragebasis wirkt im aktuellen Arbeitsstand vorbereitet"
        if rfq_ready and not missing_fields
        else f"Die Anfragebasis ist noch nicht vollstaendig; offene Punkte: {open_points}"
    )
    dispatch_note = (
        "Ein Versand ist trotzdem nur nach expliziter Zustimmung und ueber den geregelten Dispatch-Fluss erlaubt."
        if dispatch_ready
        else "Ein Versand an Hersteller ist hier nicht erlaubt; dafuer braucht es bestaetigte Daten, explizite Zustimmung und den geregelten Dispatch-Fluss."
    )
    return render_communication_template(
        "rfq_readiness_answer",
        {
            "mode": "contact",
            "status": status,
            "dispatch_note": dispatch_note,
            "pending_question": pending_question,
            "has_missing": bool(missing_fields),
        },
        fallback=(
            f"{status}. {dispatch_note}\n\n"
            "Ich kann die Anfragebasis fuer eine Herstellerpruefung vorbereiten und offene Punkte sichtbar machen, "
            "aber ich kontaktiere keinen Hersteller automatisch und treffe keine technische Endentscheidung."
            + (
                f"\n\nDer naechste sinnvolle Schritt bleibt: {pending_question}"
                if pending_question and missing_fields
                else ""
            )
        ),
    )


def _runtime_action_type(
    *,
    intent: RfqReadinessIntent,
    active_case_exists: bool,
    has_missing: bool,
) -> RuntimeActionType:
    if not active_case_exists:
        return RuntimeActionType.DEFER_RFQ_UNTIL_REQUIRED_FIELDS
    if intent.asks_external_contact:
        return RuntimeActionType.ANSWER_RFQ_STATUS
    if intent.asks_build_basis or intent.asks_preview_or_pdf:
        if has_missing:
            return RuntimeActionType.DEFER_RFQ_UNTIL_REQUIRED_FIELDS
        return RuntimeActionType.BUILD_RFQ_PREVIEW
    return RuntimeActionType.SHOW_RFQ_READINESS


def _missing_fields(state: Any | None) -> tuple[str, ...]:
    if state is None:
        return ()
    known_fields = _known_asserted_fields(state)
    fields: list[str] = []
    pending = _pending_question(state)
    if pending.get("target_field") and pending.get("target_field") not in known_fields:
        fields.append(str(pending["target_field"]))
    asserted = getattr(state, "asserted", None)
    fields.extend(getattr(asserted, "blocking_unknowns", ()) or ())
    fields.extend(getattr(asserted, "conflict_flags", ()) or ())
    governance = getattr(state, "governance", None)
    fields.extend(getattr(governance, "preselection_blockers", ()) or ())
    fields.extend(getattr(governance, "type_sensitive_required", ()) or ())
    fields.extend(getattr(governance, "compliance_blockers", ()) or ())
    fields.extend(getattr(governance, "open_validation_points", ()) or ())
    rfq = getattr(state, "rfq", None)
    fields.extend(getattr(rfq, "blocking_findings", ()) or ())
    fields.extend(getattr(rfq, "required_corrections", ()) or ())
    action_readiness = getattr(state, "action_readiness", None)
    fields.extend(getattr(action_readiness, "missing_for_inquiry", ()) or ())
    unresolved = [
        field
        for field in _unique_nonempty(fields)
        if _field_key(field) not in known_fields
    ]
    return tuple(_field_label(field) for field in unresolved)[:8]


def _open_points(state: Any | None) -> tuple[str, ...]:
    if state is None:
        return ()
    points: list[str] = []
    governance = getattr(state, "governance", None)
    points.extend(getattr(governance, "open_validation_points", ()) or ())
    points.extend(getattr(governance, "missing_but_assumable", ()) or ())
    evidence = getattr(state, "evidence", None)
    points.extend(getattr(evidence, "unresolved_open_points", ()) or ())
    points.extend(getattr(evidence, "evidence_gaps", ()) or ())
    rfq = getattr(state, "rfq", None)
    points.extend(getattr(rfq, "soft_findings", ()) or ())
    points.extend(getattr(rfq, "notes", ()) or ())
    export_profile = getattr(state, "export_profile", None)
    points.extend(getattr(export_profile, "unresolved_points", ()) or ())
    return tuple(_field_label(point) for point in _unique_nonempty(points))[:8]


def _blocking_reasons(
    state: Any | None,
    missing_fields: list[str],
    open_points: list[str],
    *,
    gov_class: str = "",
) -> tuple[str, ...]:
    if state is None:
        return ()
    # §12.6 reconciliation: the governance reducer already collapsed the
    # safety/value-conflict split into gov_class. Class A (admissible) and
    # Class B (admissible with open points) are, by that verdict, NOT hard-
    # blocked — their gaps and degraded value conflicts are open points, not
    # blocking reasons. Only Class C (safety/compliance) keeps hard blockers.
    # Consume gov_class as the single source instead of re-deriving the conflict
    # severity here.
    if gov_class in ("A", "B"):
        return ()
    reasons: list[str] = []
    reasons.extend(missing_fields)
    asserted = getattr(state, "asserted", None)
    reasons.extend(getattr(asserted, "conflict_flags", ()) or ())
    governance = getattr(state, "governance", None)
    reasons.extend(getattr(governance, "preselection_blockers", ()) or ())
    reasons.extend(getattr(governance, "compliance_blockers", ()) or ())
    rfq = getattr(state, "rfq", None)
    reasons.extend(getattr(rfq, "blocking_findings", ()) or ())
    reasons.extend(getattr(rfq, "required_corrections", ()) or ())
    action_readiness = getattr(state, "action_readiness", None)
    reasons.extend(getattr(action_readiness, "missing_for_inquiry", ()) or ())
    if open_points and not (_bool_attr(getattr(state, "rfq", None), "rfq_ready")):
        reasons.extend(open_points)
    return tuple(_field_label(reason) for reason in _unique_nonempty(reasons))[:10]


def _pending_question(state: Any | None) -> dict[str, str]:
    pending = getattr(state, "pending_question", None)
    if pending is None:
        return {}
    target_field = str(getattr(pending, "target_field", "") or "").strip()
    if target_field and _field_key(target_field) in _known_asserted_fields(state):
        return {}
    return {
        "target_field": target_field,
        "question_text": str(getattr(pending, "question_text", "") or "").strip(),
    }


def _active_case_exists(state: Any | None) -> bool:
    if state is None:
        return False
    if getattr(state, "pending_question", None) is not None:
        return True
    if getattr(state, "conversation_messages", None):
        return True
    asserted = getattr(state, "asserted", None)
    return bool(getattr(asserted, "assertions", None))


def _known_case_summary(state: Any | None) -> list[str]:
    asserted = getattr(state, "asserted", None)
    assertions = getattr(asserted, "assertions", {}) or {}
    summary: list[str] = []
    if isinstance(assertions, dict):
        for field, claim in assertions.items():
            field_label = _field_label(field)
            value = getattr(claim, "asserted_value", None)
            if value is None:
                value = getattr(claim, "value", None)
            if value is None:
                summary.append(field_label)
            else:
                summary.append(f"{field_label}: {value}")
    return summary[:6]


def _known_case_fact_count(state: Any | None) -> int:
    asserted = getattr(state, "asserted", None)
    assertions = getattr(asserted, "assertions", {}) or {}
    return len(assertions) if isinstance(assertions, dict) else 0


def _professional_check_projection(state: Any | None) -> dict[str, Any]:
    profile = _governed_profile(state)
    engineering_path = _engineering_path(profile)
    if not profile or engineering_path is None:
        return {"groups": [], "blockers": [], "evidence_status": "not_available"}
    technical_derivations = list(getattr(state, "compute_results", ()) or ())
    existing_derivation_keys = {
        str(item.get("calc_type") or item.get("calculation_id") or "")
        for item in technical_derivations
        if isinstance(item, dict)
    }
    for item in calculation_ledger_derivations(getattr(state, "calculation", None)):
        calc_key = str(item.get("calc_type") or item.get("calculation_id") or "")
        if calc_key in existing_derivation_keys:
            continue
        technical_derivations.append(item)
        existing_derivation_keys.add(calc_key)

    checks = build_registered_check_results(
        profile=profile,
        engineering_path=engineering_path,
        technical_derivations=technical_derivations,
    )
    groups = _group_professional_checks(checks)
    blockers = _professional_check_blockers(checks)
    return {
        "groups": groups,
        "blockers": blockers,
        "evidence_status": _professional_evidence_status(checks, blockers),
    }


def _governed_profile(state: Any | None) -> dict[str, Any]:
    if state is None:
        return {}
    profile: dict[str, Any] = {}
    asserted = getattr(state, "asserted", None)
    assertions = getattr(asserted, "assertions", {}) or {}
    if isinstance(assertions, dict):
        for field, claim in assertions.items():
            value = getattr(claim, "asserted_value", None)
            if value in (None, "", [], {}):
                value = getattr(claim, "value", None)
            if value not in (None, "", [], {}):
                profile[str(field)] = value

    normalized = getattr(state, "normalized", None)
    parameters = getattr(normalized, "parameters", {}) or {}
    if isinstance(parameters, dict):
        for field, parameter in parameters.items():
            if str(field) in profile:
                continue
            value = getattr(parameter, "value", None)
            if value not in (None, "", [], {}):
                profile[str(field)] = value
    return profile


def _engineering_path(profile: dict[str, Any]) -> str | None:
    raw = " ".join(
        str(profile.get(key) or "")
        for key in ("engineering_path", "sealing_type", "seal_type", "application")
    ).casefold()
    if any(
        token in raw
        for token in (
            "rwdr",
            "radialwellendichtring",
            "wellendichtring",
            "radial_shaft_seal",
        )
    ):
        return "rwdr"
    return None


def _group_professional_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for check in checks:
        group_id = _check_group_id(check)
        group = buckets.setdefault(
            group_id,
            {
                "group_id": group_id,
                "label": _check_group_label(group_id),
                "status_counts": {},
                "checks": [],
            },
        )
        status = str(check.get("status") or "unknown")
        group["status_counts"][status] = int(group["status_counts"].get(status, 0)) + 1
        group["checks"].append(_safe_check_payload(check))
    return list(buckets.values())


def _check_group_id(check: dict[str, Any]) -> str:
    calc_id = str(check.get("calc_id") or check.get("check_id") or "")
    formula = str(check.get("formula_version") or "")
    if formula == "rwdr_professional_precheck_v1":
        return "rwdr_professional_checks"
    if calc_id.startswith("material_medium_"):
        return "material_medium_evidence"
    return "rwdr_core_checks"


def _check_group_label(group_id: str) -> str:
    return {
        "rwdr_core_checks": "RWDR core precheck",
        "rwdr_professional_checks": "RWDR professional checks",
        "material_medium_evidence": "Material/medium evidence",
    }.get(group_id, group_id)


def _safe_check_payload(check: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "calc_id",
        "check_id",
        "label",
        "status",
        "claim_type",
        "severity",
        "requirement_tier",
        "missing_fields",
        "ambiguous_fields",
        "evidence_fields",
        "human_readable_reason",
        "allowed_user_wording",
        "blocking_reason",
    )
    payload = {
        key: check.get(key) for key in allowed if check.get(key) not in (None, "", [])
    }
    payload["final_approval_claim_allowed"] = False
    return payload


def _professional_check_blockers(checks: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for check in checks:
        status = str(check.get("status") or "")
        requirement_tier = str(check.get("requirement_tier") or "")
        if not requirement_tier.startswith("required"):
            continue
        missing = check.get("missing_fields") or check.get("missing_inputs") or []
        if missing and status in {"blocked", "pending"}:
            blockers.extend(_field_label(field) for field in missing)
    return list(dict.fromkeys(blockers))[:8]


def _professional_evidence_status(
    checks: list[dict[str, Any]], blockers: list[str]
) -> str:
    if not checks:
        return "not_available"
    if blockers:
        return "insufficient_evidence"
    if any(str(check.get("status") or "") == "failed" for check in checks):
        return "evidence_found_with_risks"
    if any(str(check.get("evidence_fields") or "") for check in checks):
        return "evidence_found"
    return "no_evidence"


def _known_asserted_fields(state: Any | None) -> set[str]:
    asserted = getattr(state, "asserted", None)
    assertions = getattr(asserted, "assertions", {}) or {}
    if not isinstance(assertions, dict):
        return set()
    known: set[str] = set()
    for field, claim in assertions.items():
        value = getattr(claim, "asserted_value", None)
        if value not in (None, "", [], {}):
            known.add(_field_key(field))
    return known


def _open_points_text(missing_fields: tuple[str, ...]) -> str:
    if not missing_fields:
        return "keine konkreten offenen Pflichtfelder im aktuellen Runtime-Kontext sichtbar"
    return ", ".join(missing_fields[:6])


def _field_key(field: Any) -> str:
    value = str(field or "").strip()
    aliases = {
        "Temperatur": "temperature_c",
        "Betriebstemperatur": "temperature_c",
        "temperature": "temperature_c",
        "temperature_c": "temperature_c",
        "Druck": "pressure_bar",
        "pressure": "pressure_bar",
        "pressure_bar": "pressure_bar",
        "pressure_at_seal_bar": "pressure_at_seal_bar",
        "pressure_delta_bar": "pressure_at_seal_bar",
        "ambiguous_pressure_bar": "ambiguous_pressure_bar",
        "Medium": "medium",
        "medium": "medium",
        "Wellendurchmesser": "shaft_diameter_mm",
        "shaft_diameter_mm": "shaft_diameter_mm",
        "Drehzahl": "speed_rpm",
        "speed_rpm": "speed_rpm",
    }
    return aliases.get(value, value)


def _field_label(field: Any) -> str:
    value = str(field or "").strip()
    labels = {
        "medium": "Medium",
        "temperature_c": "Temperatur",
        "temperature": "Temperatur",
        "pressure_bar": "Druck",
        "pressure_at_seal_bar": "Druck",
        "pressure_delta_bar": "Druck",
        "ambiguous_pressure_bar": "Druckbezug",
        "pressure": "Druck",
        "motion_type": "Bewegung",
        "seal_type": "Dichtungstyp",
        "dimensions": "Abmessungen",
        "shaft_diameter_mm": "Wellendurchmesser",
        "housing_bore_diameter_mm": "Gehaeusebohrung",
        "speed_rpm": "Drehzahl",
        "surface_finish": "Oberflaeche",
    }
    return labels.get(value, value or "offener Punkt")


def _unique_nonempty(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _bool_attr(obj: Any | None, attr: str) -> bool:
    return bool(getattr(obj, attr, False)) if obj is not None else False


def _normalize(message: str) -> str:
    text = " ".join(str(message or "").casefold().strip().split())
    replacements = {
        "\u00e4": "ae",
        "\u00f6": "oe",
        "\u00fc": "ue",
        "\u00df": "ss",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text
