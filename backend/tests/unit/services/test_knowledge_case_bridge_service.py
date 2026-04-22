from app.services.knowledge_case_bridge_service import KnowledgeCaseBridgeService, TransitionSignalKind


def test_transition_signal_detects_concrete_user_case() -> None:
    signal = KnowledgeCaseBridgeService().detect_transition_signal("Meine Pumpe hat 50 mm Welle und 6 bar")
    assert signal.kind is TransitionSignalKind.CONCRETE_CASE
    assert signal.confidence > 0.5
