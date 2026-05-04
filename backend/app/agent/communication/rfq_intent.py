from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agent.communication.v7_contracts import RuntimeActionType


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
    known_missing_fields: list[str] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    pending_question: dict[str, str | None] | None = None
    known_case_facts_count: int = 0
    known_case_summary: list[str] = Field(default_factory=list)
    consent_required: bool = True
    dispatch_allowed: bool = False
    external_contact_allowed: bool = False
    final_approval_claim_allowed: bool = False
    preview_available: bool = False
    preview_possible: bool = False
    preview_id: str | None = None
    preview_requires_explicit_endpoint: bool = True
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
            "known_missing_fields_count": len(self.known_missing_fields),
            "open_points_count": len(self.open_points),
            "blocking_reasons_count": len(self.blocking_reasons),
            "known_case_facts_count": self.known_case_facts_count,
            "preview_available": self.preview_available,
            "preview_possible": self.preview_possible,
            "preview_id": self.preview_id,
            "preview_requires_explicit_endpoint": self.preview_requires_explicit_endpoint,
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
        term in text
        for term in ("pdf", "vorschau", "preview", "export", "dokument")
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
    rfq_admissible = _bool_attr(getattr(governed_state, "governance", None), "rfq_admissible")
    dispatch_ready = _bool_attr(getattr(governed_state, "dispatch", None), "dispatch_ready")
    action_type = _runtime_action_type(intent=intent, active_case_exists=active_case_exists, has_missing=bool(missing_fields))

    if not active_case_exists:
        answer = (
            "Ich kann eine Anfragebasis oder RFQ-Basis vorbereiten, aber dafuer brauche ich zuerst "
            "einen qualifizierten Dichtungsfall. Ohne Fall, Revision und technische Eckdaten erstelle "
            "ich keine Herstelleranfrage und sende nichts extern.\n\n"
            "Der sichere naechste Schritt ist die Qualifikation: Um welche Dichtung oder Anwendung geht es?"
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
            preview_blocking_reason="no_active_case",
            projection_source="no_active_case",
        )

    missing_fields = list(_missing_fields(governed_state))
    open_points = list(_open_points(governed_state))
    blocking_reasons = list(_blocking_reasons(governed_state, missing_fields, open_points))
    pending = _pending_question(governed_state)
    known_summary = _known_case_summary(governed_state)
    rfq_ready = _bool_attr(getattr(governed_state, "rfq", None), "rfq_ready")
    rfq_admissible = _bool_attr(getattr(governed_state, "governance", None), "rfq_admissible")
    export_profile = getattr(governed_state, "export_profile", None)
    export_rfq_ready = _bool_attr(export_profile, "rfq_ready")
    manufacturer_review_ready = bool((rfq_ready or rfq_admissible or export_rfq_ready) and not blocking_reasons)
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
        rfq_basis_ready=bool((rfq_ready or rfq_admissible or export_rfq_ready) and not blocking_reasons),
        known_missing_fields=missing_fields,
        open_points=open_points,
        blocking_reasons=blocking_reasons,
        pending_question=pending or None,
        known_case_facts_count=_known_case_fact_count(governed_state),
        known_case_summary=known_summary,
        consent_required=True,
        dispatch_allowed=False,
        external_contact_allowed=False,
        final_approval_claim_allowed=False,
        preview_available=False,
        preview_possible=preview_possible,
        preview_id=None,
        preview_requires_explicit_endpoint=True,
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
        return (
            "Deine Anfragebasis wirkt aus dem aktuellen governed State grundsaetzlich fuer eine "
            "Herstellerpruefung vorbereitet. Das ist keine technische Endentscheidung und kein "
            "automatischer Herstellerentscheid; vor externem Teilen braucht es weiterhin den geregelten "
            "RFQ-/Consent-Schritt.\n\n"
            "Ich sende nichts automatisch an Hersteller."
        )
    open_points = _open_points_text(missing_fields)
    resume = f"\n\nDer naechste sinnvolle Schritt bleibt: {pending_question}" if pending_question else ""
    return (
        "Die Anfragebasis ist fuer eine Herstellerpruefung noch nicht vollstaendig genug. "
        "Ich kann den RFQ-Status nur aus dem vorhandenen governed State ableiten und erfinde keine "
        f"fehlenden Werte.\n\nOffene Punkte: {open_points}.\n\n"
        "Das ist eine RFQ-Basis fuer die Klaerung mit einem Hersteller oder Spezialisten, keine technische Endentscheidung."
        f"{resume}"
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
        return (
            f"Ich kann die {artifact} als manufacturer-review-ready RFQ-Basis vorbereiten, "
            "aber das Teilen oder Exportieren laeuft ueber den geregelten Preview- und Consent-Fluss. "
            "Ich sende nichts automatisch extern und treffe keine technische Endentscheidung."
        )
    open_points = _open_points_text(missing_fields)
    resume = f"\n\nDer naechste sinnvolle Schritt bleibt: {pending_question}" if pending_question else ""
    return (
        f"Ich kann daraus eine {artifact} vorbereiten, aber im aktuellen Fall fehlen noch Angaben "
        f"fuer eine belastbare Herstellerpruefung. Offene Punkte: {open_points}.\n\n"
        "Sobald die Pflichtangaben im governed Fall sauber vorliegen, kann daraus eine RFQ-Basis fuer "
        "die Herstellerpruefung entstehen. Das ist keine technische Endentscheidung und kein automatischer Versand."
        f"{resume}"
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
        "Die Anfragebasis wirkt im aktuellen State vorbereitet"
        if rfq_ready and not missing_fields
        else f"Die Anfragebasis ist noch nicht vollstaendig; offene Punkte: {open_points}"
    )
    resume = f"\n\nDer naechste sinnvolle Schritt bleibt: {pending_question}" if pending_question and missing_fields else ""
    dispatch_note = (
        "Ein Versand ist trotzdem nur nach expliziter Zustimmung und ueber den geregelten Dispatch-Fluss erlaubt."
        if dispatch_ready
        else "Ein Versand an Hersteller ist hier nicht erlaubt; dafuer braucht es bestaetigte Daten, explizite Zustimmung und den geregelten Dispatch-Fluss."
    )
    return (
        f"{status}. {dispatch_note}\n\n"
        "Ich kann die Anfragebasis fuer eine Herstellerpruefung vorbereiten und offene Punkte sichtbar machen, "
        "aber ich kontaktiere keinen Hersteller automatisch und treffe keine technische Endentscheidung."
        f"{resume}"
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
    fields: list[str] = []
    pending = _pending_question(state)
    if pending.get("target_field"):
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
    return tuple(_field_label(field) for field in _unique_nonempty(fields))[:8]


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
) -> tuple[str, ...]:
    if state is None:
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
    return {
        "target_field": str(getattr(pending, "target_field", "") or "").strip(),
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


def _open_points_text(missing_fields: tuple[str, ...]) -> str:
    if not missing_fields:
        return "keine konkreten offenen Pflichtfelder im aktuellen Runtime-Kontext sichtbar"
    return ", ".join(missing_fields[:6])


def _field_label(field: Any) -> str:
    value = str(field or "").strip()
    labels = {
        "medium": "Medium",
        "temperature_c": "Temperatur",
        "temperature": "Temperatur",
        "pressure_bar": "Druck",
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
