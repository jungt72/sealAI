"""Unit tests for SealAIState.compute_knowledge_coverage() — deterministic, no LLM."""
from app._legacy_v2.state.sealai_state import SealAIState


def test_coverage_greeting():
    s = SealAIState()
    assert s.compute_knowledge_coverage("greeting") == "full"


def test_coverage_limited():
    s = SealAIState()
    assert s.compute_knowledge_coverage("material_research") == "limited"


def test_coverage_full():
    s = SealAIState(
        medium="Hydrauliköl HLP46",
        pressure_bar=180.0,
        temperature_c=60.0,
        dynamic_type="reciprocating",
    )
    assert s.compute_knowledge_coverage("material_research") == "full"


def test_coverage_partial_complex():
    s = SealAIState(
        medium="H2",
        pressure_bar=350.0,
        temperature_c=20.0,
        dynamic_type="static",
        # dp_dt_bar_per_s, aed_required, medium_additives alle None → partial
    )
    assert s.compute_knowledge_coverage("safety_critical") == "partial"
