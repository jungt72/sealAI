from app.services.medium_intelligence_service import MediumIntelligenceService, ProvenanceTier


def test_registry_medium_is_tier_one_grounded() -> None:
    result = MediumIntelligenceService().get_medium_intelligence("HLP46")
    assert result.matched_registry_entry is not None
    assert result.provenance_tier is ProvenanceTier.REGISTRY


def test_unknown_medium_is_marked_as_llm_synthesis_even_without_llm() -> None:
    result = MediumIntelligenceService().get_medium_intelligence("mystery medium")
    assert result.matched_registry_entry is None
    assert result.provenance_tier is ProvenanceTier.LLM_SYNTHESIS
    assert "medium_not_registry_grounded" in result.risk_notes
