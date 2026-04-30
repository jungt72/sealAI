from __future__ import annotations

from app.agent.communication.models import AllowedClaim, CaseConversationState


class AllowedClaimBuilder:
    """Converts backend state into explicit claim IDs the LLM may use."""

    def build(self, state: CaseConversationState) -> list[AllowedClaim]:
        claims: list[AllowedClaim] = []

        for field in state.confirmed_fields:
            statement = f"{field.label or field.key}: {field.value}"
            if field.unit:
                statement = f"{statement} {field.unit}"
            claims.append(
                AllowedClaim(
                    id=f"field.confirmed.{field.key}",
                    type="confirmed_field",
                    statement=statement,
                    source="user_confirmed" if field.source in {"user_stated", "confirmed"} else "backend_rule",
                    confidence="confirmed",
                    field_keys=[field.key],
                )
            )

        for field in state.proposed_fields:
            statement = f"{field.label or field.key} wurde als Kandidat erkannt: {field.value}"
            if field.unit:
                statement = f"{statement} {field.unit}"
            claims.append(
                AllowedClaim(
                    id=f"field.proposed.{field.key}",
                    type="proposed_field",
                    statement=statement,
                    source="backend_rule",
                    confidence="proposed",
                    field_keys=[field.key],
                )
            )

        for field in state.missing_fields:
            claims.append(
                AllowedClaim(
                    id=f"field.missing.{field.key}",
                    type="missing_field",
                    statement=f"{field.label} fehlt noch. {field.reason}".strip(),
                    source="backend_rule",
                    confidence="uncertain",
                    severity="high" if field.criticality == "critical" else "medium",
                    field_keys=[field.key],
                )
            )

        for field in state.stale_fields:
            claims.append(
                AllowedClaim(
                    id=f"field.stale.{field.key}",
                    type="stale_field",
                    statement=f"{field.key} ist stale: {field.reason}",
                    source="backend_rule",
                    confidence="uncertain",
                    severity="medium",
                    field_keys=[field.key],
                )
            )

        for calc in state.calculations:
            status = "liegt vor" if calc.status == "available" else "ist wegen fehlender Eingaben blockiert"
            claims.append(
                AllowedClaim(
                    id=f"calculation.{calc.id}",
                    type="calculation",
                    statement=f"{calc.label} {status}.",
                    source="calculation",
                    confidence="calculated" if calc.status == "available" else "uncertain",
                    severity="none" if calc.status == "available" else "medium",
                    field_keys=list(calc.inputs),
                )
            )

        for risk in state.risks:
            claims.append(
                AllowedClaim(
                    id=f"risk.{risk.id}",
                    type="risk",
                    statement=f"{risk.label}: {risk.reason}",
                    source="backend_rule" if risk.source == "rule" else risk.source,
                    confidence="confirmed",
                    severity=risk.severity,
                )
            )

        readiness_statement = f"Readiness-Status: {state.readiness.status}."
        if state.readiness.blocking_reasons:
            readiness_statement += " Blockiert durch: " + ", ".join(state.readiness.blocking_reasons[:5])
        claims.append(
            AllowedClaim(
                id="readiness.current",
                type="readiness",
                statement=readiness_statement,
                source="backend_rule",
                confidence="confirmed" if state.readiness.status != "unknown" else "uncertain",
                severity="medium" if state.readiness.blocking_reasons else "none",
                field_keys=list(state.readiness.blocking_reasons),
            )
        )

        for evidence in state.evidence_refs:
            claims.append(
                AllowedClaim(
                    id=f"evidence.{evidence.id}",
                    type="evidence",
                    statement=f"Evidence vorhanden: {evidence.title}",
                    source="evidence",
                    confidence="confirmed",
                    evidence_ref_ids=[evidence.id],
                )
            )

        for idx, action in enumerate(state.allowed_next_actions[:5]):
            claims.append(
                AllowedClaim(
                    id=f"action.next.{idx + 1}",
                    type="allowed_action",
                    statement=str(action),
                    source="backend_rule",
                    confidence="confirmed",
                )
            )

        claims.append(
            AllowedClaim(
                id="limitation.no_final_release",
                type="limitation",
                statement=(
                    "SeaLAI darf keine finale Auslegungsfreigabe erteilen; "
                    "Herstellerpruefung oder qualifizierte technische Pruefung bleibt erforderlich."
                ),
                source="system_limitation",
                confidence="confirmed",
                severity="high",
            )
        )
        return claims
