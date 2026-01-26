from app.langgraph_v2.nodes import nodes_frontdoor


def test_frontdoor_derives_knowledge_type_from_key():
    raw_intent = {"key": "knowledge_material", "knowledge_type": None}
    assert nodes_frontdoor._derive_knowledge_type_from_intent(raw_intent) == "material"


def test_frontdoor_detects_sources_from_standard_codes():
    assert nodes_frontdoor.detect_sources_request("Bitte nach DIN 376 prüfen") is True
    assert nodes_frontdoor.detect_sources_request("Gilt ISO 3601 für O-Ringe?") is True


def test_frontdoor_requires_rag_when_sources_and_comparison():
    assert nodes_frontdoor._compute_requires_rag("explanation_or_comparison", True) is True


def test_frontdoor_no_rag_for_design_with_sources_flag():
    assert nodes_frontdoor._compute_requires_rag("design_recommendation", True) is True
