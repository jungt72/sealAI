from __future__ import annotations

import pytest
from app._legacy_v2.utils.candidate_semantics import (
    annotate_material_choice,
    build_candidate_clusters,
    SpecificityLevel,
    IdentityClass,
)

def test_candidate_clustering_rank_based():
    # Case 1: Required Compound, got Governed Compound
    candidates = [
        {
            "kind": "material",
            "material": "NBR 70",
            "confidence": "user",
            "identity_class": "identity_confirmed",
            "specificity": "compound_required",
            "governed": True
        }
    ]
    clusters = build_candidate_clusters(candidates, required_specificity="compound_required")
    assert len(clusters["plausibly_viable"]) == 1
    assert clusters["plausibly_viable"][0]["material"] == "NBR 70"

    # Case 2: Required Compound, got Governed Family
    candidates = [
        {
            "kind": "material",
            "material": "NBR",
            "confidence": "user",
            "identity_class": "identity_confirmed",
            "specificity": "family_only",
            "governed": True
        }
    ]
    clusters = build_candidate_clusters(candidates, required_specificity="compound_required")
    assert len(clusters["plausibly_viable"]) == 0
    assert len(clusters["viable_only_with_manufacturer_validation"]) == 1
    assert clusters["viable_only_with_manufacturer_validation"][0]["material"] == "NBR"

    # Case 3: Required Family, got Governed Family (Family Eligibility)
    candidates = [
        {
            "kind": "material",
            "material": "NBR",
            "confidence": "user",
            "identity_class": "identity_confirmed",
            "specificity": "family_only",
            "governed": True
        }
    ]
    clusters = build_candidate_clusters(candidates, required_specificity="family_only")
    assert len(clusters["plausibly_viable"]) == 1
    assert clusters["plausibly_viable"][0]["material"] == "NBR"

    # Case 4: Not governed (e.g. heuristic) -> viable_only
    candidates = [
        {
            "kind": "material",
            "material": "NBR 70",
            "confidence": "heuristic",
            "identity_class": "identity_unresolved",
            "specificity": "compound_required",
            "governed": False
        }
    ]
    clusters = build_candidate_clusters(candidates, required_specificity="compound_required")
    assert len(clusters["plausibly_viable"]) == 0
    assert len(clusters["viable_only_with_manufacturer_validation"]) == 1

def test_annotate_material_choice_governance():
    # User confirmed family should be governed
    choice = {
        "material": "FKM",
        "confidence": "user",
        "identity_class": "confirmed"
    }
    annotated = annotate_material_choice(choice)
    assert annotated["governed"] is True
    assert annotated["specificity"] == "family_only"

    # Heuristic should not be governed
    choice = {
        "material": "FKM 75",
        "confidence": "heuristic",
        "identity_class": "unresolved"
    }
    annotated = annotate_material_choice(choice)
    assert annotated["governed"] is False
