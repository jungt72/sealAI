import pytest

from sealai_v2.core.contracts import CalcResult, ComputedValue
from sealai_v2.orchestration.execution_policy import (
    ExecutionClass,
    ExecutionFeatures,
    ModelTier,
    StreamingMode,
    VerificationMode,
    decide_execution,
    deterministic_response,
)
from sealai_v2.pipeline.routing import (
    RouteDecision,
    RouteName,
    classify_route_deterministic,
    requests_calculation,
    requests_solution,
)


def _route(name, *, forced=False, signals=0):
    return RouteDecision(name, "test", 1.0, forced, signals)


def test_deterministic_router_never_needs_an_llm_intent():
    assert (
        classify_route_deterministic("Hallo!").route is RouteName.SMALLTALK_NAVIGATION
    )


def test_calculation_context_requires_an_explicit_kernel_term():
    assert requests_calculation("Bitte die Umfangsgeschwindigkeit berechnen") is True
    assert (
        requests_calculation(
            "Erkläre ausführlich, warum ein RWDR bei zu hoher Umfangsgeschwindigkeit ausfällt."
        )
        is False
    )
    assert requests_calculation("FKM in Heißdampf bei 140 °C einordnen") is False
    assert (
        classify_route_deterministic("Was ist PTFE?").route
        is RouteName.MATERIAL_KNOWLEDGE
    )
    assert (
        classify_route_deterministic("Was ist eine Radialwellendichtung?").route
        is RouteName.GENERAL_SEALING_KNOWLEDGE
    )
    assert (
        classify_route_deterministic(
            "Erkläre ausführlich, warum ein RWDR bei zu hoher Umfangsgeschwindigkeit ausfällt."
        ).route
        is RouteName.GENERAL_SEALING_KNOWLEDGE
    )
    assert (
        classify_route_deterministic("Details zu Skydrol als Dichtungsmedium").route
        is RouteName.GENERAL_SEALING_KNOWLEDGE
    )
    assert (
        classify_route_deterministic("RWDR 40x62x8 bei 8000 U/min").route
        is RouteName.ENGINEERING_CASE
    )
    assert (
        classify_route_deterministic("Erzaehl mir etwas").route
        is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    )


def test_solution_request_recognises_goal_not_one_literal_sentence():
    assert requests_solution("Welche Dichtungslösung wäre sinnvoll?") is True
    assert requests_solution("Was wäre hier ein tragfähiger Ansatz?") is True
    assert requests_solution("Wie würdest du die Dichtstelle auslegen?") is True
    assert (
        requests_solution("Welcher Werkstoff passt unter diesen Bedingungen?") is True
    )
    assert requests_solution("Leckage null – was ist hier optimal?") is True
    assert requests_solution("Was ist ein RWDR?") is False


def test_missing_contract_field_stops_before_any_model():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True),
            contract_status="NEEDS_CLARIFICATION",
            required_missing=("Medium",),
        )
    )
    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert "Medium" in deterministic_response(decision, missing_fields=("Medium",))


def test_ready_kernel_result_precedes_unrelated_pack_missing_fields_without_evidence():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True),
            required_missing=("Betriebstemperatur",),
            calculation_requested=True,
            calculation_computed_count=1,
        )
    )
    calc = CalcResult(
        computed=(
            ComputedValue(
                calc_id="umfangsgeschwindigkeit",
                name="v_m_s",
                value=10.472,
                unit="m/s",
                stage=1,
                derivation_depth=1,
                formula="pi*d1*n/60000",
                input_origins=(
                    "vom Nutzer genannt (wellendurchmesser: »50 mm«)",
                    "vom Nutzer genannt (drehzahl: »4000 U/min«)",
                ),
            ),
        )
    )

    response = deterministic_response(decision, calc=calc)

    assert decision.reason == "deterministic_calculation"
    assert decision.model_tier is ModelTier.NONE
    assert "v_m_s = 10,472 m/s" in response
    assert "50 mm" in response and "4000 U/min" in response
    assert "Betriebstemperatur" not in response


def test_requested_kernel_result_stays_fact_only_when_risk_context_lacks_evidence():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True, signals=2),
            risk_flags=("Wasserstoff",),
            authoritative_evidence_count=0,
            calculation_requested=True,
            calculation_computed_count=1,
        )
    )

    # Only the reviewed kernel value may be rendered here; no model can synthesize a material or
    # safety recommendation. The pipeline attaches its independent risk badge to the response.
    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert decision.reason == "deterministic_calculation"


def test_exact_validated_cache_hit_is_d0_without_model():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.MATERIAL_KNOWLEDGE), exact_cache_hit=True
        )
    )
    assert decision.execution_class is ExecutionClass.D0
    assert decision.model_tier is ModelTier.NONE


def test_high_risk_without_evidence_requires_human_and_no_model():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True),
            risk_flags=("ATEX",),
            authoritative_evidence_count=0,
        )
    )
    assert decision.execution_class is ExecutionClass.H1
    assert decision.verification_mode is VerificationMode.HUMAN
    assert decision.streaming_mode is StreamingMode.ATOMIC


def test_ungrounded_technical_case_is_a_deterministic_evidence_gap():
    decision = decide_execution(
        ExecutionFeatures(route=_route(RouteName.ENGINEERING_CASE, forced=True))
    )

    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert decision.reason == "technical_evidence_gap"
    assert "kein unabhängig geprüfter Beleg" in deterministic_response(decision)


def test_signal_free_ambiguity_never_becomes_a_technical_evidence_gap():
    route = classify_route_deterministic("Erzaehl mir etwas")
    decision = decide_execution(ExecutionFeatures(route=route))
    response = deterministic_response(decision)

    assert route.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert route.deterministic_signal_count == 0
    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert decision.reason == "ambiguous_no_domain_signal"
    assert "fachliche Frage zur Dichtungstechnik" in response
    assert "Werkstoff" not in response
    assert "Herstellerdatenblatt" not in response


@pytest.mark.parametrize(
    "question",
    (
        "Welchen Elektromotor soll ich für mein Rührwerk nehmen?",
        "Kannst du mir auch sagen, welchen Elektromotor ich für mein Rührwerk nehmen soll?",
        "Weißt du, welchen Antrieb wir für den Mischer verwenden sollen?",
        "Kannst du den Antrieb für den Mischer auslegen?",
        "Welche Motorleistung empfiehlst du für den Reaktor?",
        "Motor für unsere Anlage, kannst du ihn auslegen?",
        "Antrieb für unsere Pumpe, kannst du den empfehlen?",
        "Elektromotor für den Rührwerksantrieb, könntest du diesen dimensionieren?",
        "Motorleistung für den Reaktor, kannst du sie dimensionieren?",
    ),
)
def test_adjacent_drive_request_marks_domain_boundary_and_keeps_sealing_value(question):
    route = classify_route_deterministic(question)
    decision = decide_execution(ExecutionFeatures(route=route))
    response = deterministic_response(decision, question=question)

    assert route.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert "außerhalb meiner Dichtungstechnik-Kompetenz" in response
    assert "nenne oder genehmige ich hier keinen Motor" in response
    assert "Drehzahl" in response and "Wellendichtung" in response
    assert "Antriebs- beziehungsweise Verfahrenstechnik" in response


@pytest.mark.parametrize(
    "question",
    (
        "Welchen Einfluss hat der Motor auf die Wellendichtung?",
        "Wie beeinflusst der Motor die passende Wellendichtung?",
        "Welchen Einfluss hat der Motor auf eine geeignete Wellendichtung?",
        "Warum ist der Motor für die Wellendichtung wichtig, die wir schon nehmen?",
        "Empfiehlst du eine Dichtung für den Antrieb dieser Pumpe?",
        "Wir brauchen eine Dichtung fuer den Motor der Pumpe.",
        "Der Antrieb läuft mit 1500 U/min, welche Dichtung empfiehlst du?",
        "Ich brauche eine Dichtung für den Motor, kannst du sie auslegen?",
    ),
)
def test_drive_effect_question_remains_in_sealing_domain(question):
    route = classify_route_deterministic(question)

    assert route.route is not RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert route.reason not in {
        "adjacent_component_selection_out_of_scope",
        "deterministic_adjacent_component_selection_out_of_scope",
    }


@pytest.mark.parametrize(
    "question",
    (
        "Wir haben den Motor schon gewählt, jetzt brauchen wir noch einen passenden Wellendichtring, kannst du den auslegen?",
        "Der Motor läuft bereits, jetzt fehlt nur noch ein passender O-Ring, kannst du den empfehlen?",
        "Antrieb ist spezifiziert, wir brauchen noch den passenden Werkstoff, kannst du den auswählen?",
        "Die Dichtung muss zur Motorleistung passen, kannst du sie für 90 Grad und Hydrauliköl auslegen?",
        "Motor mit O-Ring, kannst du ihn auslegen?",
        "Motor für unsere Anlage, wir brauchen noch eine Bewertung des Werkstoffs, kannst du ihn auslegen?",
        "Motorleistung für unsere Anlage, wir brauchen noch eine Einschätzung der Dichtung, kannst du sie dimensionieren?",
    ),
)
def test_same_gender_drive_seal_anaphora_gets_one_deterministic_clarification(
    question,
):
    route = classify_route_deterministic(question)
    decision = decide_execution(ExecutionFeatures(route=route))
    response = deterministic_response(decision, question=question)

    assert route.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert "den Bezug" in response
    assert "Motor beziehungsweise Antrieb" in response
    assert "Dichtung beziehungsweise den Werkstoff" in response
    assert response.count("?") == 1


@pytest.mark.parametrize(
    "question",
    (
        "Welchen Antrieb empfiehlst du, und welche Dichtung passt dazu?",
        "Welchen Motor soll ich nehmen, und welche Dichtung passt dazu?",
        "Kannst du sagen, welchen Motor ich nehmen soll und welche Dichtung dazu passt?",
        "Ich brauche einen Antrieb und eine Dichtung für die Pumpe.",
        "Welchen Motor soll ich für mein Rührwerk nehmen? Ich brauche auch eine passende Dichtung.",
        "Welchen Antrieb soll ich nehmen? Ich möchte auch eine passende Dichtung besprechen.",
        "Welchen Antrieb soll ich für den Mischer nehmen? Wir wollen dafür eine geeignete Dichtung.",
        "Welchen Motor soll ich nehmen? Ich hätte gern auch eine passende Dichtung.",
        "Ich brauche dazu eine neue Dichtung. Welchen Motor soll ich für das Rührwerk nehmen?",
    ),
)
def test_mixed_drive_and_seal_goal_is_decomposed_without_dropping_seal_work(question):
    route = classify_route_deterministic(question)
    decision = decide_execution(ExecutionFeatures(route=route))
    response = deterministic_response(decision, question=question)

    assert route.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert route.reason == "deterministic_adjacent_component_selection_out_of_scope"
    assert "außerhalb meiner Dichtungstechnik-Kompetenz" in response
    assert "Den Dichtungsteil deiner Anfrage bearbeite ich gern" in response
    assert "Welches konkrete Medium" in response
    assert response.count("?") == 1


@pytest.mark.parametrize(
    "question",
    (
        "Wir brauchen einen neuen Antrieb für den Mischer.",
        "Welchen Antrieb empfiehlst du für eine Anwendung mit Gleitringdichtung?",
        "Welchen Antrieb würdest du für unsere Pumpe mit Gleitringdichtung und 1500 U/min empfehlen?",
        "Ich brauche einen Motor mit Gleitringdichtung; welchen Antrieb empfiehlst du?",
        "Motor für unsere Anlage, wir suchen noch einen Ansprechpartner für den Werkstoff-Einkauf generell, kannst du ihn auslegen?",
        "Motor für die Pumpe, wir möchten außerdem einen neuen Werkstoff-Lieferanten finden, kannst du ihn auslegen?",
        "Motor für unsere Anlage, wir suchen außerdem Informationen zum Werkstoff für unser Reporting, kannst du ihn auslegen?",
        "Motorleistung für unsere Anlage, wir suchen außerdem Zahlen zur Dichtung für unser Reporting, kannst du sie dimensionieren?",
        "Ich brauche keine Dichtung, welchen Motor soll ich für den Mischer nehmen?",
    ),
)
def test_drive_selection_with_modifier_or_existing_seal_context_marks_boundary(
    question,
):
    route = classify_route_deterministic(question)

    assert route.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert route.reason == "deterministic_adjacent_component_selection_out_of_scope"


def test_ambiguous_high_risk_input_still_fails_closed():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.UNSUPPORTED_OR_AMBIGUOUS, forced=True),
            risk_flags=("Sauerstoff",),
        )
    )

    assert decision.execution_class is ExecutionClass.H1
    assert decision.model_tier is ModelTier.NONE
    assert decision.needs_human_review is True
    assert decision.reason == "ambiguous_high_risk_input"


def test_grounded_solution_request_uses_frontier_synthesis_and_claim_verification():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True, signals=1),
            authoritative_evidence_count=2,
            solution_requested=True,
        )
    )

    assert decision.execution_class is ExecutionClass.C1
    assert decision.model_tier is ModelTier.FRONTIER
    assert decision.verification_mode is VerificationMode.CLAIM_LLM
    assert decision.reason == "grounded_solution_synthesis"


def test_simple_knowledge_uses_standard_once_without_llm_verifier():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.MATERIAL_KNOWLEDGE),
            authoritative_evidence_count=1,
        )
    )
    assert decision.execution_class is ExecutionClass.S0
    assert decision.model_tier is ModelTier.STANDARD
    assert decision.verification_mode is VerificationMode.DETERMINISTIC


def test_case_intake_invite_is_deterministic_without_llm_verifier():
    # Intake is governed conversation planning, not technical generation.  The response is stable
    # across providers and cannot accidentally contain retrieved claims.
    decision = decide_execution(
        ExecutionFeatures(route=_route(RouteName.CASE_INTAKE_INVITE))
    )
    assert decision.execution_class is ExecutionClass.S0
    assert decision.model_tier is ModelTier.NONE
    assert decision.verification_mode is VerificationMode.DETERMINISTIC
    assert decision.streaming_mode is StreamingMode.ATOMIC


def test_ungrounded_knowledge_is_a_deterministic_evidence_gap():
    decision = decide_execution(
        ExecutionFeatures(route=_route(RouteName.MATERIAL_KNOWLEDGE))
    )

    assert decision.execution_class is ExecutionClass.D1
    assert decision.model_tier is ModelTier.NONE
    assert decision.reason == "knowledge_evidence_gap"
    response = deterministic_response(decision)
    assert "kein unabhängig geprüfter Beleg" in response
    assert "bestätige oder verwerfe" in response


def test_well_sourced_knowledge_does_not_escalate_only_because_of_citation_count():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.MATERIAL_KNOWLEDGE),
            authoritative_evidence_count=12,
            document_count=8,
        )
    )
    assert decision.execution_class is ExecutionClass.S0
    assert decision.model_tier is ModelTier.STANDARD


def test_untrusted_knowledge_context_still_uses_frontier():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.MATERIAL_KNOWLEDGE),
            authoritative_evidence_count=8,
            document_count=8,
            untrusted_content_count=1,
        )
    )
    assert decision.execution_class is ExecutionClass.C1
    assert decision.model_tier is ModelTier.FRONTIER


def test_standard_technical_case_uses_small_model_plus_selective_verifier():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True, signals=1),
            authoritative_evidence_count=2,
        )
    )
    assert decision.execution_class is ExecutionClass.S1
    assert decision.reasoning_effort == "high"
    assert decision.verification_mode is VerificationMode.CLAIM_LLM


def test_reviewed_policy_fact_routes_decision_case_directly_to_frontier():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True, signals=1),
            authoritative_evidence_count=1,
            reviewed_policy_fact_count=1,
        )
    )
    assert decision.execution_class is ExecutionClass.C2
    assert decision.model_tier is ModelTier.FRONTIER
    assert decision.needs_human_review is True


def test_complex_context_routes_frontier_directly_without_cheap_first_attempt():
    decision = decide_execution(
        ExecutionFeatures(
            route=_route(RouteName.ENGINEERING_CASE, forced=True),
            authoritative_evidence_count=3,
            document_count=4,
        )
    )
    assert decision.execution_class is ExecutionClass.C1
    assert decision.model_tier is ModelTier.FRONTIER
    assert decision.verification_mode is VerificationMode.DETERMINISTIC
