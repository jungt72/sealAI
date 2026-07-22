"""Deterministic German renderer for the internal TechnicalAnswer contract."""

from __future__ import annotations

from sealai_v2.core.technical_answer import TechnicalAnswer

_STATUS = {
    "provisional": "Vorläufige Orientierung",
    "conditional": "Bedingte technische Orientierung",
    "not_recommended": "Nicht empfohlen",
}


def render_technical_answer(
    answer: TechnicalAnswer, *, communication_plan: dict | None = None
) -> str:
    sections = [answer.conclusion.strip()]
    plan = communication_plan or {}

    if answer.claims:
        claims = ["**Technische Einordnung**"]
        for claim in answer.claims:
            source = (
                " (quellengebunden)"
                if claim.evidence_ids
                else " (ohne belastbaren Beleg; vorläufig)"
            )
            claims.append(f"- {claim.text.strip()}{source}")
        sections.append("\n".join(claims))

    if answer.assumptions:
        sections.append(
            "**Annahmen**\n" + "\n".join(f"- {item}" for item in answer.assumptions)
        )
    planned_question = str(plan.get("next_question") or "").strip()
    missing_information = answer.missing_information
    if plan.get("goal") == "advance_engineering_case":
        missing_information = missing_information[:1]
    if missing_information and not planned_question:
        sections.append(
            "**Nächster Klärungsschritt**\n"
            + "\n".join(f"- {item}" for item in missing_information)
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
    if planned_question:
        reason = str(plan.get("question_reason") or "").strip()
        sections.append(
            "**Nächster Schritt**\n"
            + planned_question
            + (f" {reason}" if reason else "")
        )
    return "\n\n".join(section for section in sections if section)
