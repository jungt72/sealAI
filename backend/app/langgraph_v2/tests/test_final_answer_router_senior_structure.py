from app.langgraph_v2.utils.jinja import render_template


def test_final_answer_router_has_senior_headings_and_no_sources_without_refs() -> None:
    text = render_template(
        "final_answer_router.j2",
        {
            "intent_goal": "design_recommendation",
            "frontdoor_reply": "Kurz aufgenommen.",
            "parameters": {},
            "calc_results": {},
            "material_choice": {},
            "profile_choice": {},
            "validation": {},
            "products": {},
            "comparison_notes": {},
            "troubleshooting": {},
            "working_memory": {},
            "requires_rag": False,
        },
    )
    assert "## Annahmen & Randbedingungen" in text
    assert "## Technische Mechanismen" in text
    assert "## Risiken & Failure-Modes" in text
    assert "## Prüf- und Abnahmeempfehlung" in text
    assert "## Nächste Schritte" in text
    assert "## Quellen / Belege" not in text


def test_final_answer_router_shows_sources_only_when_refs_present() -> None:
    text = render_template(
        "final_answer_router.j2",
        {
            "intent_goal": "explanation_or_comparison",
            "comparison_notes": {"rag_reference": ["Quelle: DIN XYZ"]},
            "requires_rag": True,
        },
    )
    assert "## Quellen / Belege" in text
