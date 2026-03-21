from app._legacy_v2.utils.candidate_semantics import annotate_material_choice, build_candidate_clusters


def test_annotate_material_choice_marks_retrieval_hits_as_document_level() -> None:
    annotated = annotate_material_choice(
        {
            "material": "Technical datasheet",
            "confidence": "retrieved",
        }
    )

    assert annotated["specificity"] == "family_only"
    assert annotated["governed"] is False


def test_annotate_material_choice_keeps_family_codes_at_family_level() -> None:
    annotated = annotate_material_choice(
        {
            "material": "PTFE",
            "confidence": "heuristic",
        }
    )

    assert annotated["specificity"] == "family_only"
    assert annotated["governed"] is False


def test_annotate_material_choice_does_not_upgrade_probable_identity_to_compound_specific() -> None:
    annotated = annotate_material_choice(
        {
            "material": "Kyrolon",
            "confidence": "heuristic",
        },
        identity_map={"material": {"identity_class": "identity_probable"}},
    )

    assert annotated["identity_class"] == "identity_probable"
    assert annotated["specificity"] == "family_only"
    assert annotated["governed"] is False


def test_build_candidate_clusters_routes_gate_excluded_to_inadmissible() -> None:
    candidates = [
        {
            "kind": "material",
            "value": "NBR",
            "specificity": "family_only",
            "governed": False,
            "excluded_by_gate": "chemical_resistance:C:NBR×Schwefelsäure",
        },
        {
            "kind": "material",
            "value": "FKM",
            "specificity": "family_only",
            "governed": False,
            "excluded_by_gate": None,
        },
    ]

    clusters = build_candidate_clusters(candidates)

    assert len(clusters["inadmissible_or_excluded"]) == 1
    assert clusters["inadmissible_or_excluded"][0]["value"] == "NBR"
    assert len(clusters["viable_only_with_manufacturer_validation"]) == 1
    assert clusters["viable_only_with_manufacturer_validation"][0]["value"] == "FKM"
    assert clusters["plausibly_viable"] == []


def test_build_candidate_clusters_governed_compound_specific_is_plausibly_viable() -> None:
    candidates = [
        {
            "kind": "material",
            "value": "FKM-A75",
            "specificity": "compound_required",
            "governed": True,
            "excluded_by_gate": None,
        },
    ]

    clusters = build_candidate_clusters(candidates)

    assert len(clusters["plausibly_viable"]) == 1
    assert clusters["plausibly_viable"][0]["value"] == "FKM-A75"
    assert clusters["viable_only_with_manufacturer_validation"] == []
    assert clusters["inadmissible_or_excluded"] == []


def test_build_candidate_clusters_empty_input_returns_three_empty_buckets() -> None:
    clusters = build_candidate_clusters([])

    assert clusters["plausibly_viable"] == []
    assert clusters["viable_only_with_manufacturer_validation"] == []
    assert clusters["inadmissible_or_excluded"] == []


def test_build_candidate_clusters_gate_exclusion_overrides_governed_flag() -> None:
    """excluded_by_gate must route to inadmissible even if governed=True."""
    candidates = [
        {
            "kind": "material",
            "value": "NBR",
            "specificity": "compound_required",
            "governed": True,
            "excluded_by_gate": "chemical_resistance:C:NBR×Aceton",
        },
    ]

    clusters = build_candidate_clusters(candidates)

    assert len(clusters["inadmissible_or_excluded"]) == 1
    assert clusters["plausibly_viable"] == []
