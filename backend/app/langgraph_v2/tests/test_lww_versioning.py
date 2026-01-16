
import pytest
import time
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_lww

def test_lww_versioning_fresh_update():
    """Verify that a fresh update increments the version."""
    existing = {"pressure_bar": 10.0}
    patch = {"pressure_bar": 20.0}
    versions = {"pressure_bar": 1}
    updated_at = {"pressure_bar": 1000.0}
    
    (
        merged,
        _,
        merged_versions,
        merged_updated_at,
        applied,
        rejected
    ) = apply_parameter_patch_lww(
        existing,
        patch,
        provenance={"pressure_bar": "llm"},
        source="llm",
        parameter_versions=versions,
        parameter_updated_at=updated_at,
        base_versions=versions # Simulate LLM seeing version 1
    )
    
    assert "pressure_bar" in applied
    assert not rejected
    assert merged["pressure_bar"] == 20.0
    assert merged_versions["pressure_bar"] == 2
    assert merged_updated_at["pressure_bar"] > 1000.0

def test_lww_versioning_stale_update():
    """Verify that an update based on an old version is rejected."""
    existing = {"pressure_bar": 20.0}
    versions = {"pressure_bar": 5} # Current version is 5
    
    patch = {"pressure_bar": 30.0}
    base_versions = {"pressure_bar": 2} # Client thinks version is 2
    
    (
        merged,
        _,
        merged_versions,
        _,
        applied,
        rejected
    ) = apply_parameter_patch_lww(
        existing,
        patch,
        provenance={"pressure_bar": "user"},
        source="user",
        parameter_versions=versions,
        parameter_updated_at={},
        base_versions=base_versions
    )
    
    assert "pressure_bar" not in applied
    assert merged["pressure_bar"] == 20.0 # Unchanged
    assert merged_versions["pressure_bar"] == 5 # Unchanged
    
    # Check rejection details
    rejection = next((r for r in rejected if r["field"] == "pressure_bar"), None)
    assert rejection is not None
    assert rejection["reason"] == "stale"

def test_lww_versioning_new_field():
    """Verify that a new field starts at version 1."""
    existing = {}
    versions = {}
    
    patch = {"pressure_bar": 10.0}
    
    (
        merged,
        _,
        merged_versions,
        _,
        applied,
        _
    ) = apply_parameter_patch_lww(
        existing,
        patch,
        provenance={},
        source="user",
        parameter_versions=versions,
        parameter_updated_at={},
        base_versions={}
    )
    
    assert merged["pressure_bar"] == 10.0
    assert merged_versions["pressure_bar"] == 1

def test_lww_mixed_updates():
    """Verify partial application where some fields are stale and others are fresh."""
    existing = {"A": 10, "B": 20}
    versions = {"A": 5, "B": 5}
    
    patch = {"A": 11, "B": 21}
    base_versions = {"A": 5, "B": 2} # A is fresh, B is stale (2 < 5)
    
    (
        merged,
        _,
        merged_versions,
        _,
        applied,
        rejected
    ) = apply_parameter_patch_lww(
        existing,
        patch,
        provenance={"A": "user", "B": "user"},
        source="user",
        parameter_versions=versions,
        parameter_updated_at={},
        base_versions=base_versions
    )
    
    # A should be applied
    assert "A" in applied
    assert merged["A"] == 11
    assert merged_versions["A"] == 6
    
    # B should be rejected
    assert "B" not in applied
    assert merged["B"] == 20
    assert merged_versions["B"] == 5
    
    stale_fields = [r["field"] for r in rejected if r["reason"] == "stale"]
    assert "B" in stale_fields
