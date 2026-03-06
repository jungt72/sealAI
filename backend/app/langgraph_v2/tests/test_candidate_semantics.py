from app.langgraph_v2.utils.candidate_semantics import annotate_material_choice


def test_annotate_material_choice_marks_retrieval_hits_as_document_level() -> None:
    annotated = annotate_material_choice(
        {
            "material": "Technical datasheet",
            "confidence": "retrieved",
        }
    )

    assert annotated["specificity"] == "document_hit"
    assert annotated["governed"] is False


def test_annotate_material_choice_keeps_family_codes_at_family_level() -> None:
    annotated = annotate_material_choice(
        {
            "material": "PTFE",
            "confidence": "heuristic",
        }
    )

    assert annotated["specificity"] == "family_level"
    assert annotated["governed"] is False


def test_annotate_material_choice_does_not_upgrade_probable_identity_to_compound_specific() -> None:
    annotated = annotate_material_choice(
        {
            "material": "Kyrolon",
            "confidence": "heuristic",
        },
        identity_map={"material": {"identity_class": "probable"}},
    )

    assert annotated["identity_class"] == "probable"
    assert annotated["specificity"] == "unresolved"
    assert annotated["governed"] is False
