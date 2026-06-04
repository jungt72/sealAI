"""Shared taxonomy and helpers for bounded technical risk claims."""

from __future__ import annotations

import re
from typing import Any


RISK_CLAIM_TYPES = {
    "measured_risk",
    "missing_input_risk",
    "ambiguity_risk",
    "context_advisory",
    "blocked_claim",
}


def unique_text(items: list[Any] | tuple[Any, ...] | set[Any]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in items if str(item or "").strip()))


def severity_from_score(score: int) -> str:
    if score == 9 or score >= 4:
        return "blocking"
    if score >= 3:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def risk_claim_payload(
    *,
    claim_id: str,
    claim_type: str,
    subject_field: str,
    severity: str,
    evidence_fields: list[Any] | None = None,
    missing_fields: list[Any] | None = None,
    blocked_reason: str | None = None,
    allowed_user_wording: str = "",
    forbidden_user_wording: list[Any] | None = None,
    source: str,
) -> dict[str, Any]:
    normalized_type = claim_type if claim_type in RISK_CLAIM_TYPES else "context_advisory"
    return {
        "claim_id": claim_id,
        "claim_type": normalized_type,
        "subject_field": subject_field,
        "severity": severity,
        "evidence_fields": unique_text(evidence_fields or []),
        "missing_fields": unique_text(missing_fields or []),
        "blocked_reason": blocked_reason,
        "allowed_user_wording": allowed_user_wording,
        "forbidden_user_wording": unique_text(forbidden_user_wording or []),
        "source": source,
    }


def claims_from_context(context: Any) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for attr in ("risk_findings", "risk_claims"):
        for item in list(getattr(context, attr, []) or []):
            payload = _as_dict(item)
            if payload:
                claims.append(payload)
    dashboard = getattr(context, "dashboard_projection", None)
    if isinstance(dashboard, dict):
        for item in list(dashboard.get("risk_matrix") or []):
            payload = _as_dict(item)
            if payload:
                claims.append(payload)
    return claims


def has_measured_risk_evidence(
    context: Any,
    *,
    subject_fields: set[str],
    evidence_fields: set[str],
) -> bool:
    for claim in claims_from_context(context):
        if str(claim.get("claim_type") or "") != "measured_risk":
            continue
        subject = str(claim.get("subject_field") or "")
        evidence = {str(item) for item in list(claim.get("evidence_fields") or [])}
        if subject in subject_fields and evidence.intersection(evidence_fields):
            return True
    return False


def unsupported_measured_claim_failures(context: Any, text: str) -> list[dict[str, Any]]:
    answer = str(text or "")
    failures: list[dict[str, Any]] = []
    rules = (
        {
            "kind": "unsupported_measured_runout_claim",
            "pattern": re.compile(
                r"\b(?:hoher|hohe|hoch|erhoeht(?:er|e|es|en)?|erhöht(?:er|e|es|en)?)\s+"
                r"(?:wellenschlag|rundlauf|exzentrizitaet|exzentrizität)\b|"
                r"\b(?:wellenschlag|rundlauf|exzentrizitaet|exzentrizität)\s+"
                r"(?:ist|liegt|wirkt)\s+(?:hoch|erhoeht|erhöht|kritisch)\b",
                re.IGNORECASE | re.UNICODE,
            ),
            "subject_fields": {"runout_mm", "shaft_runout", "eccentricity_mm"},
            "evidence_fields": {"runout_mm", "shaft_runout", "eccentricity_mm"},
            "safe_wording": "Rundlauf/Wellenschlag ist noch offen und sollte fuer RWDR geprueft werden.",
        },
        {
            "kind": "unsupported_measured_seal_pressure_claim",
            "pattern": re.compile(
                r"\b(?:dichtungsdruck|dichtstellendruck|druck\s+direkt\s+an\s+der\s+dichtung|"
                r"druck\s+an\s+der\s+dichtstelle).{0,80}\b(?:kritisch|zu\s+hoch|ueber|über|"
                r"ueberschreit|überschreit)\b",
                re.IGNORECASE | re.UNICODE,
            ),
            "subject_fields": {"pressure_at_seal_bar", "pressure_delta_bar", "pressure_nominal"},
            "evidence_fields": {"pressure_at_seal_bar", "pressure_delta_bar"},
            "safe_wording": "Systemdruck oder unklarer Druck ersetzt keinen Dichtstellendruck.",
        },
        {
            "kind": "unsupported_measured_medium_material_claim",
            "pattern": re.compile(
                r"\b(?:medium|werkstoffvertraeglichkeit|werkstoffverträglichkeit|material).{0,80}"
                r"\b(?:chemisch\s+kritisch|unvertraeglich|unverträglich|nicht\s+vertraeglich|"
                r"nicht\s+verträglich)\b",
                re.IGNORECASE | re.UNICODE,
            ),
            "subject_fields": {"medium", "medium_name", "material", "sealing_material_family"},
            "evidence_fields": {"medium", "medium_name", "material", "sealing_material_family"},
            "safe_wording": "Das Medium muss eindeutig benannt sein, bevor Werkstoffvertraeglichkeit als Fakt bewertet wird.",
        },
    )
    for rule in rules:
        if not rule["pattern"].search(answer):
            continue
        if has_measured_risk_evidence(
            context,
            subject_fields=set(rule["subject_fields"]),
            evidence_fields=set(rule["evidence_fields"]),
        ):
            continue
        failures.append(
            {
                "kind": rule["kind"],
                "reason": "measured risk wording requires matching measured deterministic evidence",
                "safe_wording": rule["safe_wording"],
            }
        )
    return failures


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return {}
