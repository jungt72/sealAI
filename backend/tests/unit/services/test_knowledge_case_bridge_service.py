from app.services.knowledge_case_bridge_service import (
    KnowledgeCaseBridgeService,
    KnowledgeSessionContext,
    TransitionSignalKind,
)


def test_transition_signal_detects_concrete_user_case() -> None:
    signal = KnowledgeCaseBridgeService().detect_transition_signal(
        "Meine Pumpe hat 50 mm Welle und 6 bar",
    )
    assert signal.kind is TransitionSignalKind.CONCRETE_CASE
    assert signal.confidence > 0.5


def test_update_context_collects_turns_and_parameter_seeds() -> None:
    service = KnowledgeCaseBridgeService()

    context = service.update_context(
        "Was ist PTFE bei 180 C und 12 bar Dampf?",
        session_id="knowledge-1",
    )

    assert context.session_id == "knowledge-1"
    assert context.user_turn_index == 1
    assert context.conversation_turns[0].role == "user"
    assert context.mentioned_parameters["temperature_c"].raw_value == 180.0
    assert context.mentioned_parameters["pressure_bar"].raw_value == 12.0
    assert context.mentioned_parameters["medium"].raw_value == "Dampf"


def test_build_bridge_invitation_only_once_per_context() -> None:
    service = KnowledgeCaseBridgeService()
    context = service.update_context(
        "Was ist PTFE fuer meine Pumpe bei 12 bar?",
        session_id="knowledge-2",
    )

    invitation = service.build_bridge_invitation(
        "Was ist PTFE fuer meine Pumpe bei 12 bar?",
        context=context,
    )
    offered_context = service.mark_transition_offered(context)

    assert invitation is not None
    assert "technischen Fall" in invitation
    assert "überführen" in invitation
    assert "weiterklären" in invitation
    assert "ueberfuehren" not in invitation
    assert "weiterklaeren" not in invitation
    assert (
        service.build_bridge_invitation(
            "Was ist PTFE fuer meine Pumpe bei 12 bar?",
            context=offered_context,
        )
        is None
    )


def test_build_bridge_invitation_skips_plain_definition_even_with_existing_context() -> None:
    service = KnowledgeCaseBridgeService()
    context = service.update_context(
        "Was ist PTFE bei 180 C und 12 bar Dampf?",
        session_id="knowledge-definition",
    )

    assert (
        service.build_bridge_invitation(
            "Was ist NBR? Bitte antworte kurz und professionell.",
            context=context,
        )
        is None
    )


def test_build_governed_seed_preserves_history_and_parameters() -> None:
    service = KnowledgeCaseBridgeService()
    context = service.update_context(
        "Was ist PTFE bei 180 C und 12 bar Dampf?",
        session_id="knowledge-3",
    )
    context = service.update_context(
        "Aus der Wissensbasis: PTFE ist temperaturfest.",
        context=context,
        role="assistant",
    )

    seed = service.build_governed_seed(context)

    assert len(seed.conversation_messages) == 2
    assert seed.conversation_messages[0].role == "user"
    assert seed.conversation_messages[1].role == "assistant"
    assert {item.field_name for item in seed.observed_extractions} >= {
        "temperature_c",
        "pressure_bar",
        "medium",
    }
    assert seed.user_turn_index == 1
    assert seed.observed_topic is not None


def test_transition_signal_uses_existing_context_when_user_turn_becomes_concrete() -> None:
    service = KnowledgeCaseBridgeService()
    context = KnowledgeSessionContext(session_id="knowledge-4")
    context = service.update_context(
        "Was ist PTFE?",
        context=context,
        role="user",
    )
    signal = service.detect_transition_signal(
        "Ich brauche dafuer eine Loesung fuer meine Pumpe.",
        context=context,
    )

    assert signal.kind is TransitionSignalKind.CONCRETE_CASE
    assert "session_has_parameters" in signal.reasons
