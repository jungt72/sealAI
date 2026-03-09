import pytest
from app.langgraph_v2.projections.case_workspace import _build_specificity
from app.api.v1.schemas.case_workspace import CompletenessStatus, CandidateClusterSummary, ElevationHint

def test_specificity_elevation_missing_params():
    system = {
        "sealing_requirement_spec": {
            "material_specificity_required": "family_only"
        }
    }
    reasoning = {
        "completeness_depth": "precheck"
    }
    completeness = CompletenessStatus(
        missing_critical_parameters=["medium", "pressure_bar"]
    )
    clusters = CandidateClusterSummary(
        plausibly_viable=[],
        manufacturer_validation_required=[],
        total_candidates=0
    )
    
    spec_info = _build_specificity(system, reasoning, completeness, clusters)
    
    assert spec_info.elevation_possible is True
    # Patch C4: Check for structured hints
    assert isinstance(spec_info.elevation_hints[0], ElevationHint)
    assert any(h.field_key == "medium" for h in spec_info.elevation_hints)
    assert any(h.field_key == "pressure_bar" for h in spec_info.elevation_hints)
    assert spec_info.elevation_target == "compound_required"

def test_specificity_elevation_family_candidates():
    system = {
        "sealing_requirement_spec": {
            "material_specificity_required": "compound_required"
        }
    }
    reasoning = {
        "completeness_depth": "prequalification"
    }
    completeness = CompletenessStatus(
        missing_critical_parameters=[]
    )
    # Only family-level candidates in mfr_validation
    clusters = CandidateClusterSummary(
        plausibly_viable=[],
        manufacturer_validation_required=[
            {"value": "FKM", "specificity": "family_only"}
        ],
        total_candidates=1
    )
    
    spec_info = _build_specificity(system, reasoning, completeness, clusters)
    
    assert spec_info.elevation_possible is True
    # Patch C4: Check for structured hints
    assert spec_info.elevation_hints[0].field_key == "seal_material"
    assert spec_info.elevation_hints[0].priority == 10
    assert any("compound" in h.label.lower() for h in spec_info.elevation_hints)
    assert spec_info.elevation_target == "compound_required"

def test_no_elevation_when_already_specific():
    system = {
        "sealing_requirement_spec": {
            "material_specificity_required": "compound_required"
        }
    }
    reasoning = {
        "completeness_depth": "critical_review"
    }
    completeness = CompletenessStatus(
        missing_critical_parameters=[]
    )
    # We have a viable compound candidate
    clusters = CandidateClusterSummary(
        plausibly_viable=[
            {"value": "FKM 75 Shore A", "specificity": "compound_required"}
        ],
        manufacturer_validation_required=[],
        total_candidates=1
    )
    
    spec_info = _build_specificity(system, reasoning, completeness, clusters)
    
    assert spec_info.elevation_possible is False
    assert len(spec_info.elevation_hints) == 0
    assert spec_info.elevation_target is None
