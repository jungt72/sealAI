from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agent.communication.models import (
    AllowedClaim,
    CaseConversationState,
    ConversationMode,
    LLMResponseContract,
)
from app.agent.runtime.output_guard import check_fast_path_output


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    fallback_message: str | None = None


class CommunicationGuard:
    """Validates LLM communication contracts before they reach the user."""

    _forbidden_patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("final_approval", re.compile(r"\b(freigegeben|approved|final\s+geeignet|final\s+freigegeben|technisch\s+validiert)\b", re.IGNORECASE)),
        ("guarantee", re.compile(r"\b(garantiert|guaranteed|sicher\s+passend|garantiert\s+dicht|keine\s+weiteren\s+pruefungen|keine\s+weiteren\s+prüfungen)\b", re.IGNORECASE)),
        ("manufacturer_acceptance", re.compile(r"\b(hersteller\s+wird\s+.*akzeptieren|laut\s+hersteller|best(?:er|e)\s+hersteller)\b", re.IGNORECASE)),
        ("unsupported_standard", re.compile(r"\b(norm\s+[A-Z0-9/-]+\s+sagt|nach\s+(?:FDA|ATEX|EHEDG|TA[-\s]?Luft).*(?:konform|zugelassen|zertifiziert))\b", re.IGNORECASE)),
        ("final_recommendation", re.compile(r"\b(ich\s+empfehle\s+final|finale\s+empfehlung|nehmen\s+sie\s+final)\b", re.IGNORECASE)),
    )
    _risk_terms = re.compile(r"\b(\w*risiko|korrosion|trockenlauf|abrasion|atex|dampf)\b", re.IGNORECASE)
    _readiness_terms = re.compile(r"\b(readiness|rfq[-\s]?ready|anfragebasis\s+bereit|herstellerreif|rfq\s+bereit)\b", re.IGNORECASE)

    def validate(
        self,
        contract: LLMResponseContract,
        *,
        allowed_claims: list[AllowedClaim],
        state: CaseConversationState,
    ) -> GuardResult:
        errors: list[str] = []
        text = contract.assistant_message
        allowed_ids = {claim.id for claim in allowed_claims}
        allowed_evidence_ids = {
            evidence_id
            for claim in allowed_claims
            for evidence_id in claim.evidence_ref_ids
        }

        unknown_ids = [claim_id for claim_id in contract.used_claim_ids if claim_id not in allowed_ids]
        if unknown_ids:
            errors.append("fabricated_claim_id:" + ",".join(unknown_ids))

        if contract.contains_final_approval:
            errors.append("contract_contains_final_approval")
        if contract.contains_solution_recommendation:
            errors.append("contract_contains_solution_recommendation")

        for category, pattern in self._forbidden_patterns:
            if pattern.search(text):
                errors.append(f"forbidden_phrase:{category}")

        safe, category = check_fast_path_output(text)
        if not safe:
            errors.append(f"output_guard:{category}")

        used_claims = [claim for claim in allowed_claims if claim.id in set(contract.used_claim_ids)]
        used_types = {claim.type for claim in used_claims}

        if contract.mode != ConversationMode.GENERAL_KNOWLEDGE:
            if allowed_claims and not contract.used_claim_ids and self._contains_case_bound_statement(text, state):
                errors.append("case_bound_statement_without_allowed_claim")
            if self._risk_terms.search(text) and "risk" not in used_types and not self._has_risk_limitation_only(text):
                errors.append("risk_statement_without_risk_claim")
            if self._readiness_terms.search(text) and "readiness" not in used_types:
                errors.append("readiness_statement_without_readiness_claim")

        for evidence_id in re.findall(r"\bevidence[_-]?[A-Za-z0-9_.:-]+\b", text):
            if evidence_id not in allowed_evidence_ids:
                errors.append(f"fabricated_evidence_ref:{evidence_id}")

        if errors:
            return GuardResult(ok=False, errors=errors, fallback_message=self.fallback(state))
        return GuardResult(ok=True)

    def fallback(self, state: CaseConversationState) -> str:
        missing = [field.label for field in state.missing_fields[:4]]
        if missing:
            return (
                "Ich kann die Antwort gerade nicht sauber genug absichern. "
                "Aus dem aktuellen Arbeitsstand fehlen noch: "
                + ", ".join(missing)
                + ". Bitte ergänze diese Angaben, dann kann SeaLAI den nächsten Schritt prüfen."
            )
        if state.allowed_next_actions:
            return str(state.allowed_next_actions[0])
        return (
            "Ich kann die Antwort gerade nicht sauber genug absichern. "
            "Bitte beschreibe kurz Anwendung, Medium und die wichtigste offene Frage."
        )

    @staticmethod
    def _contains_case_bound_statement(text: str, state: CaseConversationState) -> bool:
        lowered = str(text or "").lower()
        field_values = [str(field.value).lower() for field in state.confirmed_fields if field.value not in (None, "")]
        field_labels = [str(field.label or field.key).lower() for field in state.confirmed_fields + state.proposed_fields]
        return any(value and value in lowered for value in field_values) or any(label and label in lowered for label in field_labels)

    @staticmethod
    def _has_risk_limitation_only(text: str) -> bool:
        lowered = str(text or "").lower()
        return "herstellerprüfung" in lowered or "herstellerpruefung" in lowered or "zu prüfen" in lowered
