import pytest
from app._legacy_v2.state.sealai_state import (
    ConflictRecord,
    ParameterIdentityRecord,
    CandidateItem,
)
from app._legacy_v2.state.governance_types import (
    ConflictSeverity,
    ConflictType,
    IdentityClass,
    SpecificityLevel,
)

def test_conflict_record_normalization():
    # Test severity normalization
    c1 = ConflictRecord(severity="WARNING")
    assert c1.severity == "HARD"
    
    c2 = ConflictRecord(severity="soft")
    assert c2.severity == "SOFT"
    
    c3 = ConflictRecord(severity="RESOLUTION_REQUIRES_MANUFACTURER_SCOPE")
    assert c3.severity == "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE"

    # Test type normalization
    c4 = ConflictRecord(conflict_type="COMPOUND_SPECIFICITY_CONFLICT")
    assert c4.conflict_type == "COMPOUND_SPECIFICITY_CONFLICT"

def test_identity_class_normalization():
    p1 = ParameterIdentityRecord(identity_class="confirmed")
    assert p1.identity_class == "identity_confirmed"
    
    p2 = ParameterIdentityRecord(identity_class="identity_confirmed")
    assert p2.identity_class == "identity_confirmed"
    
    p3 = ParameterIdentityRecord(identity_class="probable")
    assert p3.identity_class == "identity_probable"
    
    p4 = ParameterIdentityRecord(identity_class="family_only")
    assert p4.identity_class == "identity_family_only"
    
    p5 = ParameterIdentityRecord(identity_class="unresolved")
    assert p5.identity_class == "identity_unresolved"

def test_candidate_item_normalization():
    c1 = CandidateItem(kind="material", value="NBR", specificity="compound_specific")
    assert c1.specificity == "compound_required"
    
    c2 = CandidateItem(kind="material", value="NBR", specificity="family_level")
    assert c2.specificity == "family_only"
    
    c3 = CandidateItem(kind="material", value="NBR", specificity="material_class")
    assert c3.specificity == "product_family_required"
    
    c4 = CandidateItem(kind="material", value="NBR", specificity="unresolved")
    assert c4.specificity == "family_only"
