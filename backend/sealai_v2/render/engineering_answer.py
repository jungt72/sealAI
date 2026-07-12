"""Deterministic Markdown renderer for source-bound engineering knowledge answers."""

from __future__ import annotations

from sealai_v2.core.engineering_answer import EngineeringKnowledgeAnswer
from sealai_v2.knowledge.material_parameters import comparison_matrix


def _escape(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ").strip()


def _parameter_table(material_params: list[dict] | None) -> str | None:
    matrix = comparison_matrix(material_params or [])
    if not matrix:
        return None
    subjects, rows = matrix
    lines = [
        "**Quellengebundene Kennwerte**",
        "",
        "| Parameter | " + " | ".join(_escape(subject) for subject in subjects) + " |",
        "|---|" + "---|" * len(subjects),
    ]
    for row in rows:
        lines.append(
            "| "
            + _escape(row["label"])
            + " | "
            + " | ".join(
                _escape(row["values"].get(subject, "—")) for subject in subjects
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Typ-, Mindest- und Referenzwerte sind keine universellen Einsatzgrenzen. "
            "Prüfbasis und konkreter Compound bleiben Teil der Aussage.",
        ]
    )
    return "\n".join(lines)


def _comparison_table(answer: EngineeringKnowledgeAnswer, plan: dict) -> str:
    subjects = tuple(str(value) for value in plan.get("subjects", ()) if str(value))
    sections = plan.get("sections", ())
    lines = [
        "**Vergleich auf identischen Engineering-Achsen**",
        "",
        "| Vergleichsachse | "
        + " | ".join(_escape(subject) for subject in subjects)
        + " |",
        "|---|" + "---|" * len(subjects),
    ]
    for section in sections:
        facets = set(section.get("facets", ()))
        cells = []
        for subject in subjects:
            statements = [
                claim.statement
                for claim in answer.claims
                if claim.subject.casefold() == subject.casefold()
                and claim.facet in facets
            ]
            cells.append(
                "<br>".join(_escape(item) for item in statements[:3]) or "Nicht belegt"
            )
        lines.append(
            "| "
            + _escape(str(section.get("heading", "Einordnung")))
            + " | "
            + " | ".join(cells)
            + " |"
        )
    return "\n".join(lines)


def _overview_sections(answer: EngineeringKnowledgeAnswer, plan: dict) -> list[str]:
    rendered: list[str] = []
    used: set[int] = set()
    for section in plan.get("sections", ()):
        facets = set(section.get("facets", ()))
        matches = [
            (index, claim)
            for index, claim in enumerate(answer.claims)
            if index not in used and claim.facet in facets
        ]
        if not matches:
            continue
        used.update(index for index, _claim in matches)
        lines = [f"**{section.get('heading', 'Technische Einordnung')}**"]
        lines.extend(f"- {claim.statement}" for _index, claim in matches)
        rendered.append("\n".join(lines))
    remaining = [
        claim for index, claim in enumerate(answer.claims) if index not in used
    ]
    if remaining:
        rendered.append(
            "**Weitere quellengebundene Einordnung**\n"
            + "\n".join(f"- {claim.statement}" for claim in remaining)
        )
    return rendered


def render_engineering_answer(
    answer: EngineeringKnowledgeAnswer,
    *,
    knowledge_answer_plan: dict,
    material_params: list[dict] | None = None,
) -> str:
    sections = [answer.conclusion.strip()]
    parameter_table = _parameter_table(material_params)
    if parameter_table:
        sections.append(parameter_table)
    if knowledge_answer_plan.get("comparison") and knowledge_answer_plan.get(
        "subjects"
    ):
        sections.append(_comparison_table(answer, knowledge_answer_plan))
    else:
        sections.extend(_overview_sections(answer, knowledge_answer_plan))

    if answer.assumptions:
        sections.append(
            "**Annahmen**\n" + "\n".join(f"- {item}" for item in answer.assumptions)
        )
    if answer.missing_information:
        sections.append(
            "**Für Auswahl oder Freigabe noch erforderlich**\n"
            + "\n".join(f"- {item}" for item in answer.missing_information)
        )
    return "\n\n".join(section for section in sections if section)
