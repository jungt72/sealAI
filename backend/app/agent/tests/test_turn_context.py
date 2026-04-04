from __future__ import annotations

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.output_contract_node import build_governed_conversation_strategy_contract
from app.agent.runtime.reply_composition import (
    build_turn_context_instruction,
    compose_clarification_reply,
)
from app.agent.runtime.turn_context import (
    build_governed_turn_context,
    build_turn_context_contract,
)
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    ConversationStrategyContract,
    ContextHintState,
    DispatchContractState,
    GovernanceState,
    MediumCaptureState,
    MediumClassificationState,
    NormalizedParameter,
    NormalizedState,
)


def _claim(field_name: str, asserted_value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field_name, asserted_value=asserted_value, confidence=confidence)


def test_build_turn_context_contract_copies_strategy_and_summaries() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Welches Medium soll abgedichtet werden?",
        primary_question_reason="Das Medium entscheidet ueber Werkstoffwahl.",
        response_mode="single_question",
    )

    context = build_turn_context_contract(
        strategy=strategy,
        confirmed_facts_summary=["Medium: Wasser"],
        open_points_summary=["Betriebsdruck"],
    )

    assert context is not None
    assert context.conversation_phase == "narrowing"
    assert context.turn_goal == "clarify_primary_open_point"
    assert context.user_signal_mirror == ""
    assert context.primary_question == "Welches Medium soll abgedichtet werden?"
    assert context.primary_question_reason == "Das Medium entscheidet ueber Werkstoffwahl."
    assert context.confirmed_facts_summary == ["Medium: Wasser"]
    assert context.open_points_summary == ["Betriebsdruck"]


def test_build_turn_context_contract_returns_none_when_empty() -> None:
    assert build_turn_context_contract(strategy=None) is None


def test_build_governed_turn_context_stays_small_and_compatible() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Welches Medium soll abgedichtet werden?",
        primary_question_reason="Das Medium entscheidet ueber Werkstoffwahl.",
        response_mode="single_question",
    )
    state = GraphState(
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Hydraulikoel"),
                "pressure_bar": _claim("pressure_bar", 180),
                "temperature_c": _claim("temperature_c", 90),
            },
            blocking_unknowns=["shaft_diameter", "dynamic_type", "pressure_bar", "temperature_c"],
            conflict_flags=["medium"],
        )
    )

    context = build_governed_turn_context(state=state, strategy=strategy)

    assert context.conversation_phase == "narrowing"
    assert context.turn_goal == "clarify_primary_open_point"
    assert len(context.confirmed_facts_summary) <= 3
    assert len(context.open_points_summary) <= 3
    assert "Medium: Hydraulikoel" in context.confirmed_facts_summary
    assert any("Konflikt" in item or "Betriebsdruck" in item for item in context.open_points_summary)


def test_build_governed_turn_context_uses_governance_open_points_for_recommendation() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="recommendation",
        turn_goal="explain_governed_result",
        response_mode="result_summary",
    )
    state = GraphState(
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Hydraulikoel"),
                "pressure_bar": _claim("pressure_bar", 180),
                "temperature_c": _claim("temperature_c", 90),
            },
        ),
        governance=GovernanceState(open_validation_points=["Werkstoffgrenze pruefen", "Temperaturfenster pruefen"]),
    )

    context = build_governed_turn_context(
        state=state,
        strategy=strategy,
        response_class="governed_recommendation",
    )

    assert context.open_points_summary == ["Werkstoffgrenze pruefen", "Temperaturfenster pruefen"]


def test_build_governed_turn_context_renders_family_only_medium_open_point_status_aware() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Welche genaue Reinigungsloesung liegt an und in welcher Konzentration?",
        primary_question_reason="Ich erkenne bereits einen Medienkontext, brauche aber den genauen Stoff.",
        response_mode="single_question",
    )
    state = GraphState(
        asserted=AssertedState(blocking_unknowns=["medium", "temperature_c"]),
        medium_capture=MediumCaptureState(
            raw_mentions=["alkalische reinigungsloesung"],
            primary_raw_text="alkalische reinigungsloesung",
        ),
        medium_classification=MediumClassificationState(
            family="chemisch_aggressiv",
            confidence="medium",
            status="family_only",
            normalization_source="deterministic_family_hint:alkalisch_reinigend",
        ),
    )

    context = build_governed_turn_context(state=state, strategy=strategy)

    assert any("Reinigungsloesung" in item for item in context.open_points_summary)
    assert all(item != "Medium" for item in context.open_points_summary)


def test_build_governed_turn_context_renders_unclassified_medium_open_point_status_aware() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Wie ist XY-Compound 4711 fachlich genau einzuordnen?",
        primary_question_reason="Ich habe eine Medium-Nennung erfasst, kann sie aber noch nicht technisch einordnen.",
        response_mode="single_question",
    )
    state = GraphState(
        asserted=AssertedState(blocking_unknowns=["medium"]),
        medium_capture=MediumCaptureState(
            raw_mentions=["XY-Compound 4711"],
            primary_raw_text="XY-Compound 4711",
        ),
        medium_classification=MediumClassificationState(
            family="unknown",
            confidence="low",
            status="mentioned_unclassified",
            normalization_source="deterministic_capture_only",
        ),
    )

    context = build_governed_turn_context(state=state, strategy=strategy)

    assert any("XY-Compound 4711" in item for item in context.open_points_summary)
    assert all(item != "Medium" for item in context.open_points_summary)


def test_build_governed_turn_context_does_not_surface_generic_medium_open_point_for_recognized_medium() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Welche Betriebstemperatur liegt in °C an?",
        primary_question_reason="Die Temperatur grenzt Werkstoff und Einsatzfenster ein.",
        response_mode="single_question",
    )
    state = GraphState(
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Salzwasser"),
                "pressure_bar": _claim("pressure_bar", 12.0),
            },
            blocking_unknowns=["temperature_c"],
        ),
        medium_capture=MediumCaptureState(
            raw_mentions=["salzwasser"],
            primary_raw_text="salzwasser",
        ),
        medium_classification=MediumClassificationState(
            canonical_label="Salzwasser",
            family="waessrig_salzhaltig",
            confidence="high",
            status="recognized",
            normalization_source="deterministic_alias_map",
            mapping_confidence="confirmed",
        ),
    )

    context = build_governed_turn_context(state=state, strategy=strategy)

    assert all("Medium" not in item for item in context.open_points_summary)
    assert "Betriebstemperatur" in context.open_points_summary


def test_build_governed_turn_context_prioritizes_application_anchor_before_pressure() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Welche Art von Abdichtung oder Einbausituation liegt vor, zum Beispiel statisch oder an einer bewegten Stelle?",
        primary_question_reason="Mit dem Medium allein ist die Anwendung noch nicht ausreichend eingegrenzt; zuerst brauche ich den Anwendungs- und Bewegungsanker.",
        response_mode="single_question",
    )
    state = GraphState(
        pending_message="ich muss salzwasser draussen halten",
        asserted=AssertedState(
            assertions={"medium": _claim("medium", "Salzwasser")},
            blocking_unknowns=["pressure_bar", "temperature_c"],
        ),
        governance=GovernanceState(
            gov_class="B",
            rfq_admissible=False,
            open_validation_points=["pressure_bar", "temperature_c"],
        ),
        medium_capture=MediumCaptureState(
            raw_mentions=["salzwasser"],
            primary_raw_text="salzwasser",
        ),
        medium_classification=MediumClassificationState(
            canonical_label="Salzwasser",
            family="waessrig_salzhaltig",
            confidence="high",
            status="recognized",
            normalization_source="deterministic_alias_map",
            mapping_confidence="confirmed",
        ),
    )

    context = build_governed_turn_context(state=state, strategy=strategy)

    assert context.open_points_summary[0] == "Anwendungs- und Bewegungsart präzisieren"
    assert "Betriebsdruck" in context.open_points_summary


def test_build_governed_turn_context_prioritizes_rotary_core_parameter_before_pressure() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Welche Drehzahl liegt an der rotierenden Welle in rpm an?",
        primary_question_reason="Bei einer rotierenden Welle ist die Drehzahl einer der wichtigsten Kernparameter fuer die technische Einengung.",
        response_mode="single_question",
    )
    state = GraphState(
        pending_message="es ist eine rotierende welle",
        asserted=AssertedState(
            assertions={"medium": _claim("medium", "Salzwasser")},
            blocking_unknowns=["pressure_bar", "temperature_c"],
        ),
        governance=GovernanceState(
            gov_class="B",
            rfq_admissible=False,
            open_validation_points=["pressure_bar", "temperature_c"],
        ),
        medium_capture=MediumCaptureState(
            raw_mentions=["salzwasser"],
            primary_raw_text="salzwasser",
        ),
        medium_classification=MediumClassificationState(
            canonical_label="Salzwasser",
            family="waessrig_salzhaltig",
            confidence="high",
            status="recognized",
            normalization_source="deterministic_alias_map",
            mapping_confidence="confirmed",
        ),
    )

    context = build_governed_turn_context(state=state, strategy=strategy)

    assert context.open_points_summary[0] == "Drehzahl der rotierenden Welle"
    assert "Betriebsdruck" in context.open_points_summary


def test_build_governed_turn_context_includes_known_rotary_facts_for_rendering() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Wie ist die Einbausituation bei Ihnen ausgeführt?",
        primary_question_reason="Die Einbausituation bestimmt, wie ich den bereits erkannten Anwendungsfall technisch einordne.",
        response_mode="single_question",
    )
    state = GraphState(
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Salzwasser"),
                "shaft_diameter_mm": _claim("shaft_diameter_mm", 40.0),
                "speed_rpm": _claim("speed_rpm", 2000.0),
            },
            blocking_unknowns=["pressure_bar", "temperature_c"],
        ),
        medium_capture=MediumCaptureState(
            raw_mentions=["salzwasser"],
            primary_raw_text="salzwasser",
        ),
        medium_classification=MediumClassificationState(
            canonical_label="Salzwasser",
            family="waessrig_salzhaltig",
            confidence="high",
            status="recognized",
            normalization_source="deterministic_alias_map",
            mapping_confidence="confirmed",
        ),
        motion_hint=ContextHintState(
            label="rotary",
            confidence="high",
            source_turn_ref="turn:1",
            source_turn_index=1,
            source_type="deterministic_text_inference",
        ),
        application_hint=ContextHintState(
            label="shaft_sealing",
            confidence="medium",
            source_turn_ref="turn:1",
            source_turn_index=1,
            source_type="deterministic_text_inference",
        ),
    )

    context = build_governed_turn_context(state=state, strategy=strategy)

    assert any("Medium: Salzwasser" == item for item in context.confirmed_facts_summary)
    assert any("Wellendurchmesser: 40.0" == item for item in context.confirmed_facts_summary)
    assert any("Drehzahl: 2000.0" == item for item in context.confirmed_facts_summary)


def test_build_governed_turn_context_uses_persisted_rotary_hint_after_reload() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Welche Drehzahl liegt an der rotierenden Welle in rpm an?",
        primary_question_reason="Bei einer rotierenden Welle ist die Drehzahl einer der wichtigsten Kernparameter fuer die technische Einengung.",
        response_mode="single_question",
    )
    state = GraphState(
        asserted=AssertedState(
            assertions={"medium": _claim("medium", "Salzwasser")},
            blocking_unknowns=["pressure_bar", "temperature_c"],
        ),
        governance=GovernanceState(
            gov_class="B",
            rfq_admissible=False,
            open_validation_points=["pressure_bar", "temperature_c"],
        ),
        medium_capture=MediumCaptureState(
            raw_mentions=["salzwasser"],
            primary_raw_text="salzwasser",
        ),
        medium_classification=MediumClassificationState(
            canonical_label="Salzwasser",
            family="waessrig_salzhaltig",
            confidence="high",
            status="recognized",
            normalization_source="deterministic_alias_map",
            mapping_confidence="confirmed",
        ),
        motion_hint=ContextHintState(
            label="rotary",
            confidence="high",
            source_turn_ref="turn:2",
            source_turn_index=2,
            source_type="deterministic_text_inference",
        ),
        application_hint=ContextHintState(
            label="shaft_sealing",
            confidence="medium",
            source_turn_ref="turn:2",
            source_turn_index=2,
            source_type="deterministic_text_inference",
        ),
    )

    context = build_governed_turn_context(state=state, strategy=strategy)

    assert context.open_points_summary[0] == "Drehzahl der rotierenden Welle"
    assert "Betriebsdruck" in context.open_points_summary


def test_build_governed_turn_context_uses_contract_points_for_rfq() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="rfq_handover",
        turn_goal="prepare_handover",
        response_mode="handover_summary",
    )
    state = GraphState(
        dispatch_contract=DispatchContractState(
            unresolved_points=["Zeichnung pruefen", "Empfaengerliste bestaetigen"]
        ),
    )

    context = build_governed_turn_context(
        state=state,
        strategy=strategy,
        response_class="rfq_ready",
    )

    assert context.open_points_summary == ["Zeichnung pruefen", "Empfaengerliste bestaetigen"]


def test_reply_composition_uses_turn_context_fields() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="narrowing",
        turn_goal="clarify_primary_open_point",
        primary_question="Welches Medium soll abgedichtet werden?",
        primary_question_reason="Das Medium entscheidet ueber Werkstoffwahl.",
        response_mode="single_question",
    )
    context = build_turn_context_contract(
        strategy=strategy,
        open_points_summary=["Medium", "Betriebsdruck", "Betriebstemperatur"],
    )

    reply = compose_clarification_reply(context, fallback_text="Fallback")

    assert "Welches Medium soll abgedichtet werden?" in reply
    assert "Das Medium entscheidet ueber Werkstoffwahl." not in reply
    assert reply.count("?") == 1


def test_correction_mouth_reframes_linear_context_and_sets_new_focus() -> None:
    state = GraphState(
        analysis_cycle=4,
        pending_message="Korrektur: keine rotierende Welle, sondern lineare Bewegung.",
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Wasser mit Reinigeranteil"),
            },
            blocking_unknowns=["pressure_bar", "temperature_c"],
        ),
        normalized=NormalizedState(
            parameters={
                "medium": NormalizedParameter(
                    field_name="medium",
                    value="Wasser mit Reinigeranteil",
                    confidence="confirmed",
                    source="user_override",
                    source_turn=4,
                ),
            }
        ),
        governance=GovernanceState(
            gov_class="B",
            rfq_admissible=False,
            open_validation_points=["pressure_bar", "temperature_c"],
        ),
        motion_hint=ContextHintState(
            label="linear",
            confidence="high",
            source_turn_ref="turn:4",
            source_turn_index=4,
            source_type="deterministic_text_inference",
        ),
        application_hint=ContextHintState(
            label="linear_sealing",
            confidence="high",
            source_turn_ref="turn:4",
            source_turn_index=4,
            source_type="deterministic_text_inference",
        ),
    )

    strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")
    context = build_governed_turn_context(state=state, strategy=strategy)
    reply = compose_clarification_reply(context, fallback_text="Fallback")

    assert "kein rotativer, sondern ein linearer Dichtkontext" in reply
    assert "Welche Geometrie oder vorhandene Bauform liegt an der Dichtstelle vor?" in reply


def test_medium_focus_is_invalidated_once_medium_is_already_set() -> None:
    state = GraphState(
        analysis_cycle=5,
        pending_message="Korrektur: nicht Oel, sondern Wasser mit Reinigeranteil.",
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Wasser mit Reinigeranteil"),
            },
            blocking_unknowns=["medium", "pressure_bar", "temperature_c"],
        ),
        normalized=NormalizedState(
            parameters={
                "medium": NormalizedParameter(
                    field_name="medium",
                    value="Wasser mit Reinigeranteil",
                    confidence="confirmed",
                    source="user_override",
                    source_turn=5,
                ),
            }
        ),
        governance=GovernanceState(
            gov_class="B",
            rfq_admissible=False,
            open_validation_points=["pressure_bar", "temperature_c"],
        ),
    )

    strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")
    context = build_governed_turn_context(state=state, strategy=strategy)

    assert strategy.primary_question == "Wie ist die Einbausituation bei Ihnen ausgeführt?"
    assert all("Medium" not in item for item in context.open_points_summary)


def test_turn_context_instruction_uses_shared_fields() -> None:
    strategy = ConversationStrategyContract(
        conversation_phase="exploration",
        turn_goal="invite_case_description",
        primary_question="Erzaehlen Sie mir kurz, worum es in Ihrer Anwendung geht?",
        primary_question_reason="Dann kann ich gezielt weiterfuehren.",
        response_mode="open_invitation",
    )
    context = build_turn_context_contract(
        strategy=strategy,
        confirmed_facts_summary=["Medium: Wasser"],
        open_points_summary=["Betriebsdruck"],
    )

    instruction = build_turn_context_instruction(context)

    assert instruction is not None
    assert "KOMMUNIKATIONSKONTEXT" in instruction
    assert "Relevanter offener Fokus: Erzaehlen Sie mir kurz, worum es in Ihrer Anwendung geht?" in instruction
    assert "Bestaetigte Fakten: Medium: Wasser" in instruction
    assert "Offene Punkte: Betriebsdruck" in instruction


def test_user_signal_mirror_is_optional_legacy_field() -> None:
    assert ConversationStrategyContract(user_signal_mirror="  ").user_signal_mirror == ""
    assert ConversationStrategyContract(user_signal_mirror="Verstanden.").user_signal_mirror == "Verstanden."


def test_primary_question_must_be_exactly_one_sentence() -> None:
    with pytest.raises(ValueError):
        ConversationStrategyContract(
            primary_question="Welches Medium soll abgedichtet werden? Und bei welcher Temperatur?",
        )
