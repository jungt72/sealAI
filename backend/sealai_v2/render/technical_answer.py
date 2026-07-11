"""Deterministic German renderer for the internal TechnicalAnswer contract."""

from __future__ import annotations

from sealai_v2.core.technical_answer import TechnicalAnswer

_STATUS = {
    "provisional": "Vorläufige Orientierung",
    "conditional": "Bedingte technische Orientierung",
    "not_recommended": "Nicht empfohlen",
}


def render_technical_answer(answer: TechnicalAnswer) -> str:
    sections = [answer.conclusion.strip()]

    if answer.claims:
        claims = ["**Technische Einordnung**"]
        for claim in answer.claims:
            source = (
                " (geprüft belegt)"
                if claim.evidence_ids
                else " (ohne belastbaren Beleg; vorläufig)"
            )
            claims.append(f"- {claim.text.strip()}{source}")
        sections.append("\n".join(claims))

    if answer.assumptions:
        sections.append(
            "**Annahmen**\n" + "\n".join(f"- {item}" for item in answer.assumptions)
        )
    if answer.missing_information:
        sections.append(
            "**Noch erforderlich**\n"
            + "\n".join(f"- {item}" for item in answer.missing_information)
        )

    recommendation = answer.recommendation
    if recommendation.status != "none" and recommendation.summary.strip():
        lines = [
            f"**{_STATUS[recommendation.status]}**",
            recommendation.summary.strip(),
        ]
        lines.extend(f"- {condition}" for condition in recommendation.conditions)
        sections.append("\n".join(lines))

    if answer.needs_human_review:
        sections.append(
            "**Fachprüfung erforderlich**\n"
            "Die technische Entscheidung muss durch den Hersteller oder die zuständige "
            "Fachstelle geprüft werden."
        )
    return "\n\n".join(section for section in sections if section)
