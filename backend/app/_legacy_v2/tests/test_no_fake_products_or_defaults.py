from app._legacy_v2.utils.jinja import render_template


def test_router_does_not_emit_fake_products_or_default_facts_when_missing_params() -> None:
    text = render_template(
        "final_answer_router.j2",
        {
            "intent_goal": "design_recommendation",
            "parameters": {},
            "calc_results": {},
            "material_choice": {},
            "profile_choice": {},
            "products": {"requested": True, "catalog_connected": False, "matches": []},
            "comparison_notes": {},
            "working_memory": {},
            "requires_rag": False,
        },
    )

    assert "SealCo" not in text
    assert "SC-" not in text
    assert "Basis-Empfehlung: NBR" not in text
    assert "ASTM" not in text
    assert "EN 681-1" not in text

    # No implicit default operating points
    assert "25.0" not in text
    assert "1000" not in text
    assert "1 bar" not in text

