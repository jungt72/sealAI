from __future__ import annotations

import hashlib
import json
from typing import Any

from app.agent.communication.models import (
    CalculationFact,
    CaseConversationState,
    ConversationField,
    EvidenceRef,
    MissingField,
    ReadinessFact,
    RiskFact,
    StaleField,
)
from app.domain.critical_field_contract import is_critical_case_field


_FIELD_LABELS: dict[str, str] = {
    "medium": "Medium",
    "temperature_c": "Temperatur",
    "temperature_max": "Temperatur",
    "pressure_bar": "Druck",
    "pressure_mpa": "Druck",
    "pressure_spike_bar": "Druckspitze",
    "decompression_rate_bar_per_s": "Dekompressionsrate",
    "pressure_nominal": "Druck",
    "shaft_diameter_mm": "Wellendurchmesser",
    "housing_bore_mm": "Gehaeusebohrung",
    "installation_width_mm": "Einbaubreite",
    "radial_gap_mm": "Dichtspalt",
    "groove_width_mm": "Nutbreite",
    "groove_depth_mm": "Nuttiefe",
    "cross_section_mm": "Schnurstaerke",
    "seal_inner_diameter_mm": "Innendurchmesser",
    "runout_um": "Rundlauf",
    "surface_roughness_ra_um": "Rauheit Ra",
    "surface_roughness_rz_um": "Rauheit Rz",
    "hardness_shore_a": "Haerte",
    "speed_rpm": "Drehzahl",
    "sealing_type": "Dichtungstyp",
    "seal_type": "Dichtungstyp",
    "motion_type": "Bewegungsart",
    "leakage_target": "Leckageziel",
    "target_lifetime_cycles": "Lebensdauer Zyklen",
    "target_lifetime_hours": "Lebensdauer Stunden",
    "installation": "Einbausituation",
    "geometry_context": "Geometrie",
    "counterface_surface": "Oberflaeche",
    "compliance": "Compliance-Anforderung",
    "shaft_runout": "Rundlauf",
    "eccentricity": "Exzentrizitaet",
    "tolerance_gap": "Toleranz / Spalt",
    "material_identity": "Werkstoffidentitaet",
    "material_or_compound": "Werkstoff / Compound",
    "lubrication": "Schmierung",
    "contamination": "Verschmutzung",
    "verification_criteria": "Pruefkriterium",
    "mounting_path": "Montageweg",
}

_CRITICAL_FIELD_ALIASES: dict[str, str] = {
    "medium": "medium_name",
    "pressure": "pressure_bar",
    "temperature": "temperature_c",
    "speed": "speed_rpm",
    "rpm": "speed_rpm",
    "shaft_diameter": "shaft_diameter_mm",
    "housing_bore": "housing_bore_mm",
    "installation_width": "installation_width_mm",
    "runout": "shaft_runout",
    "dynamic_runout": "shaft_runout",
    "shaft_runout_um": "shaft_runout",
    "surface": "surface_finish",
    "roughness": "surface_roughness",
    "material": "material_identity",
    "compound": "material_or_compound",
    "function": "sealing_function",
    "lifetime": "lifetime_target",
    "verification": "verification_criteria",
    "installation": "installation_context",
}


def human_label(field_key: str) -> str:
    key = str(field_key or "").strip()
    return _FIELD_LABELS.get(key, key.replace("_", " ").strip().title() or "Angabe")


def _canonical_missing_key(field_key: str) -> str:
    key = (
        str(field_key or "")
        .replace("open_point:", "")
        .replace("conflict:", "")
        .replace(".", "_")
        .replace("-", "_")
        .strip()
        .lower()
    )
    return _CRITICAL_FIELD_ALIASES.get(key, key)


def _missing_field_criticality(field_key: str) -> str:
    return "critical" if is_critical_case_field(_canonical_missing_key(field_key)) else "important"


def state_snapshot_hash(state: CaseConversationState) -> str:
    payload = state.model_dump(mode="json", exclude={"user_id", "tenant_id"})
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CaseContextAssembler:
    """Builds a read-only LLM context from governed backend state."""

    def assemble(
        self,
        state: Any | None,
        *,
        latest_user_message: str,
        case_id: str = "default",
        current_user_id: str | None = None,
        case_owner_id: str | None = None,
        tenant_id: str | None = None,
        conversation_summary: str | None = None,
    ) -> CaseConversationState:
        if case_owner_id and current_user_id and case_owner_id != current_user_id:
            raise PermissionError("case does not belong to current user")

        if isinstance(state, CaseConversationState):
            return state.model_copy(
                update={
                    "case_id": str(case_id or state.case_id or "default"),
                    "user_id": case_owner_id or current_user_id or state.user_id,
                    "tenant_id": tenant_id or state.tenant_id,
                    "latest_user_message": latest_user_message,
                    "conversation_summary": conversation_summary or state.conversation_summary,
                }
            )

        if state is None:
            active_question = "Beschreibe kurz Anwendung, Medium oder die wichtigste Frage zur Dichtstelle."
            return CaseConversationState(
                case_id=case_id,
                user_id=case_owner_id or current_user_id,
                tenant_id=tenant_id,
                latest_user_message=latest_user_message,
                conversation_summary=conversation_summary,
                missing_fields=[
                    MissingField(
                        key="application",
                        label="Anwendung",
                        criticality="critical",
                        reason="Ohne Anwendung kann SeaLAI den Dichtungsfall nicht einordnen.",
                    )
                ],
                allowed_next_actions=["Dichtungsfall kurz beschreiben"],
                active_question=active_question,
                active_question_field_keys=["application"],
            )

        missing_fields = self._missing_fields(state)
        next_actions = self._allowed_next_actions(state)
        return CaseConversationState(
            case_id=str(getattr(state, "session_id", None) or case_id or "default"),
            user_id=case_owner_id or current_user_id,
            tenant_id=tenant_id or str(getattr(state, "tenant_id", "") or "") or None,
            phase=self._phase_from_state(state),
            confirmed_fields=self._confirmed_fields(state),
            proposed_fields=self._proposed_fields(state),
            missing_fields=missing_fields,
            stale_fields=self._stale_fields(state),
            calculations=self._calculations(state),
            risks=self._risks(state),
            readiness=self._readiness(state),
            evidence_refs=self._evidence_refs(state),
            allowed_next_actions=next_actions,
            conversation_summary=conversation_summary,
            latest_user_message=latest_user_message,
            active_question=next_actions[0] if next_actions else None,
            active_question_field_keys=[field.key for field in missing_fields[:3]],
        )

    def assemble_from_turn_context(
        self,
        *,
        turn_context: Any | None,
        latest_user_message: str,
        case_id: str = "default",
        deterministic_reply: str | None = None,
    ) -> CaseConversationState:
        confirmed: list[ConversationField] = []
        missing: list[MissingField] = []
        actions: list[str] = []
        primary = ""

        if turn_context is not None:
            for idx, item in enumerate(getattr(turn_context, "confirmed_facts_summary", []) or []):
                text = str(item or "").strip()
                if not text:
                    continue
                label, _, value = text.partition(":")
                key = label.strip().lower().replace(" ", "_") or f"fact_{idx}"
                confirmed.append(
                    ConversationField(
                        key=key,
                        label=label.strip() or human_label(key),
                        value=value.strip() if value else text,
                        source="backend",
                        status="confirmed",
                        confidence="confirmed",
                    )
                )
            for item in getattr(turn_context, "open_points_summary", []) or []:
                key = str(item or "").strip().lower().replace(" ", "_")
                if key:
                    missing.append(
                        MissingField(
                            key=key,
                            label=str(item),
                            criticality=_missing_field_criticality(key),
                            reason="Dieser Punkt blockiert den naechsten belastbaren Schritt.",
                        )
                    )
            primary = str(getattr(turn_context, "primary_question", "") or "").strip()
            if primary:
                actions.append(primary)

        return CaseConversationState(
            case_id=case_id,
            phase=str(getattr(turn_context, "conversation_phase", "") or "unknown"),
            confirmed_fields=confirmed,
            missing_fields=missing,
            allowed_next_actions=list(dict.fromkeys(action for action in actions if action)),
            latest_user_message=latest_user_message,
            active_question=primary or None,
            active_question_field_keys=[field.key for field in missing[:3]],
        )

    def _phase_from_state(self, state: Any) -> str:
        lifecycle = getattr(state, "case_lifecycle", None)
        phase = getattr(lifecycle, "phase", None) if lifecycle is not None else None
        return str(phase or getattr(state, "phase", "") or "unknown")

    def _confirmed_fields(self, state: Any) -> list[ConversationField]:
        assertions = getattr(getattr(state, "asserted", None), "assertions", {}) or {}
        result: list[ConversationField] = []
        for key, claim in dict(assertions).items():
            value = getattr(claim, "asserted_value", None)
            if value in (None, ""):
                continue
            confidence = str(getattr(claim, "confidence", "") or "")
            status = str(getattr(claim, "status", "") or "")
            if confidence == "requires_confirmation" or status in {"candidate", "inferred"}:
                continue
            result.append(
                ConversationField(
                    key=str(key),
                    label=human_label(str(key)),
                    value=value,
                    unit=getattr(getattr(claim, "engineering_value", None), "unit", None),
                    source=str(getattr(claim, "provenance", "") or "backend"),
                    status=status or "confirmed",
                    confidence=confidence or "confirmed",
                )
            )
        return result

    def _proposed_fields(self, state: Any) -> list[ConversationField]:
        result: list[ConversationField] = []
        for extraction in getattr(getattr(state, "observed", None), "raw_extractions", []) or []:
            field_name = str(getattr(extraction, "field_name", "") or "").strip()
            value = getattr(extraction, "raw_value", None)
            if not field_name or value in (None, ""):
                continue
            result.append(
                ConversationField(
                    key=field_name,
                    label=human_label(field_name),
                    value=value,
                    unit=getattr(extraction, "raw_unit", None),
                    source="user_text" if getattr(extraction, "source", "") == "user" else "llm_extraction",
                    status="pending_validation",
                    confidence="proposed",
                )
            )
        return result[-8:]

    def _missing_fields(self, state: Any) -> list[MissingField]:
        raw_items: list[str] = []
        asserted = getattr(state, "asserted", None)
        governance = getattr(state, "governance", None)
        raw_items.extend(str(item) for item in list(getattr(asserted, "blocking_unknowns", []) or []) if item)
        for attr in ("preselection_blockers", "compliance_blockers", "type_sensitive_required", "open_validation_points"):
            raw_items.extend(str(item) for item in list(getattr(governance, attr, []) or []) if item)
        result: list[MissingField] = []
        seen: set[str] = set()
        for item in raw_items:
            key = item.replace("open_point:", "").replace("conflict:", "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(
                MissingField(
                    key=key,
                    label=human_label(key),
                    criticality=_missing_field_criticality(key),
                    reason="Diese Angabe fehlt fuer die naechste technische Einordnung.",
                )
            )
        return result

    def _stale_fields(self, state: Any) -> list[StaleField]:
        result: list[StaleField] = []
        for key, status in dict(getattr(getattr(state, "normalized", None), "parameter_status", {}) or {}).items():
            if str(status) in {"stale", "contradicted"}:
                reason = "Wert muss nach Aenderung oder Widerspruch neu bewertet werden."
                result.append(StaleField(key=str(key), reason=reason))
        for key in list(getattr(getattr(state, "derived", None), "stale_derived_value_ids", []) or []):
            result.append(StaleField(key=str(key), reason="Abgeleiteter Wert ist nach Eingabeaenderung stale."))
        return result

    def _calculations(self, state: Any) -> list[CalculationFact]:
        result: list[CalculationFact] = []
        for item in list(getattr(state, "compute_results", []) or []):
            if not isinstance(item, dict):
                continue
            calc_id = str(item.get("id") or item.get("calc_type") or "calculation")
            status = "available" if item.get("status") in {"ok", "available", "computed"} else "blocked_by_missing_inputs"
            result.append(
                CalculationFact(
                    id=calc_id,
                    label=str(item.get("label") or calc_id),
                    value=item.get("value") or item.get("v_surface_m_s") or item.get("pv_value_mpa_m_s"),
                    unit=item.get("unit"),
                    inputs=[str(v) for v in list(item.get("inputs") or [])],
                    status=status,
                )
            )
        derived_values = dict(getattr(getattr(state, "derived", None), "derived_values", {}) or {})
        for key, value in derived_values.items():
            result.append(
                CalculationFact(
                    id=str(getattr(value, "calculation_id", "") or key),
                    label=human_label(str(key)),
                    value=getattr(value, "value", None),
                    inputs=list(getattr(value, "derived_from_fields", []) or []),
                    status="available" if getattr(value, "status", "") == "valid" else "blocked_by_missing_inputs",
                )
            )
        return result

    def _risks(self, state: Any) -> list[RiskFact]:
        result: list[RiskFact] = []
        governance = getattr(state, "governance", None)
        for item in list(getattr(governance, "compliance_blockers", []) or []):
            result.append(
                RiskFact(
                    id=f"risk.compliance.{item}",
                    label=f"Compliance-Pruefpunkt: {human_label(str(item))}",
                    severity="high",
                    reason="Regulierter Kontext darf nicht durch SeaLAI freigegeben werden.",
                    source="rule",
                )
            )
        for item in list(getattr(governance, "validity_limits", []) or []):
            result.append(
                RiskFact(
                    id=f"risk.validity.{len(result)}",
                    label="Gueltigkeitsgrenze",
                    severity="medium",
                    reason=str(item),
                    source="rule",
                )
            )
        return result

    def _readiness(self, state: Any) -> ReadinessFact:
        governance = getattr(state, "governance", None)
        rfq = getattr(state, "rfq", None)
        if bool(getattr(rfq, "rfq_ready", False)) or bool(getattr(governance, "rfq_admissible", False)):
            return ReadinessFact(status="rfq_ready")
        blockers = [str(item) for item in list(getattr(getattr(state, "asserted", None), "blocking_unknowns", []) or [])]
        blockers.extend(str(item) for item in list(getattr(governance, "preselection_blockers", []) or []))
        gov_class = str(getattr(governance, "gov_class", "") or "")
        if gov_class in {"A", "B"}:
            return ReadinessFact(status="partially_ready", blocking_reasons=list(dict.fromkeys(blockers)))
        if blockers:
            return ReadinessFact(status="not_ready", blocking_reasons=list(dict.fromkeys(blockers)))
        return ReadinessFact(status="unknown")

    def _evidence_refs(self, state: Any) -> list[EvidenceRef]:
        result: list[EvidenceRef] = []
        for idx, item in enumerate(list(getattr(state, "rag_evidence", []) or [])):
            if not isinstance(item, dict):
                continue
            ref_id = str(item.get("evidence_ref_id") or item.get("document_id") or f"evidence-{idx}")
            result.append(
                EvidenceRef(
                    id=ref_id,
                    title=str(item.get("title") or item.get("source") or ref_id),
                    source_type="internal_doc",
                    uri_or_ref=str(item.get("uri") or item.get("ref") or "") or None,
                )
            )
        return result

    def _allowed_next_actions(self, state: Any) -> list[str]:
        actions: list[str] = []
        output_reply = str(getattr(state, "output_reply", "") or "").strip()
        if output_reply:
            actions.append(output_reply)
        governance = getattr(state, "governance", None)
        if bool(getattr(governance, "rfq_admissible", False)):
            actions.append("RFQ-Preview pruefen")
        if not actions:
            actions.append("Naechste fehlende technische Angabe klaeren")
        return actions
