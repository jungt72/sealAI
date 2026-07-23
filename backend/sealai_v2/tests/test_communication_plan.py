from __future__ import annotations

from sealai_v2.core.communication_plan import (
    build_communication_plan,
    enforce_communication,
    evaluate_communication,
    render_case_clarification,
    render_case_intake_response,
)


def test_case_intake_plan_acknowledges_goal_and_asks_exactly_one_question() -> None:
    question = (
        "Hallo und guten Morgen, ich möchte eine Dichtungslösung entwickeln. "
        "Was benötigst du von mir?"
    )
    plan = build_communication_plan(question=question, route_name="case_intake_invite")
    answer = render_case_intake_response(question, plan)

    assert plan.answer_first is True
    assert plan.max_questions == 1
    assert answer.count("?") == 1
    assert "Dichtungslösung Schritt für Schritt" in answer
    assert "Welche Anwendung und Dichtstelle" in answer
    assert "Davon hängt ab" in answer
    assert evaluate_communication(answer, plan).passed


def test_intake_guard_rejects_unrelated_evidence_and_question_lists() -> None:
    plan = build_communication_plan(
        question="Ich möchte eine Dichtung entwickeln",
        route_name="case_intake_invite",
    )
    verdict = evaluate_communication(
        "**Belege** Fachkarte X. Welches Medium? Welcher Druck?", plan
    )

    assert verdict.passed is False
    assert "question_budget_exceeded" in verdict.violations
    assert "intake_contains_evidence" in verdict.violations
    assert "planned_question_missing" in verdict.violations


def test_communication_enforcement_keeps_only_planned_question_and_reason() -> None:
    plan = build_communication_plan(
        question="Was brauchst du noch?",
        route_name="engineering_case",
        missing_fields=("Druck", "Drehzahl"),
    )
    repaired = enforce_communication(
        "Der Fall ist erfasst. Welches Medium? Welche Drehzahl?",
        plan,
    )

    assert repaired.count("?") == 1
    assert repaired.endswith(f"{plan.next_question} {plan.question_reason}")
    assert evaluate_communication(repaired, plan).passed


def test_guard_requires_the_governed_question_not_an_arbitrary_model_question() -> None:
    plan = build_communication_plan(
        question="Welcher Werkstoff wäre für diese Anwendung zu prüfen?",
        route_name="engineering_case",
    )

    verdict = evaluate_communication(
        "Ich grenze den Fall ein. Welche Farbe hat die Dichtung?", plan
    )

    assert not verdict.passed
    assert "planned_question_missing" in verdict.violations


def test_communication_enforcement_removes_questions_from_answer_only_route() -> None:
    plan = build_communication_plan(
        question="Was ist PTFE?",
        route_name="material_knowledge",
    )
    repaired = enforce_communication("PTFE ist ein Fluorpolymer. Warum relevant?", plan)

    assert repaired == "PTFE ist ein Fluorpolymer. Warum relevant."
    assert evaluate_communication(repaired, plan).passed


def test_active_case_plan_uses_only_first_missing_field_with_reason() -> None:
    plan = build_communication_plan(
        question="Was brauchst du noch?",
        route_name="engineering_case",
        case_fields=("dichtungstyp", "medium"),
        missing_fields=("Betriebstemperatur", "Druck", "Drehzahl"),
    )
    answer = render_case_clarification(plan)

    assert plan.case_bound is True
    assert "Welche minimale, normale und maximale Temperatur" in answer
    assert "Druck" not in plan.next_question
    assert answer.count("?") == 1
    assert "Fallkontext" in answer


def test_knowledge_plan_answers_first_and_does_not_invent_case_questions() -> None:
    plan = build_communication_plan(
        question="Was ist PTFE?", route_name="material_knowledge"
    )

    assert plan.goal == "answer_requested_knowledge"
    assert plan.answer_first is True
    assert plan.max_questions == 0
    assert plan.next_question == ""


def test_material_comparison_allows_one_discriminating_question() -> None:
    plan = build_communication_plan(
        question="PTFE gegenüber einem Elastomer: Welche Vor- und Nachteile gibt es?",
        route_name="material_comparison",
    )

    answer = "Ich kann PTFE zuordnen. Welches Elastomer möchtest du vergleichen?"
    assert plan.max_questions == 1
    assert evaluate_communication(answer, plan).passed


def test_leakage_plan_prioritises_diagnosis_over_material_replacement() -> None:
    plan = build_communication_plan(
        question="Der Wellendichtring ist undicht. Was soll ich prüfen?",
        route_name="leakage_troubleshooting",
        missing_fields=("Druck", "Drehzahl"),
    )

    assert plan.goal == "diagnose_failure"
    assert plan.depth == "brief"
    assert plan.max_questions == 1
    assert "cause_before_replacement" in plan.must_include


def test_unknown_replacement_plan_answers_identification_goal_not_failure_detour() -> None:
    plan = build_communication_plan(
        question="Wie finde ich Ersatz für meine kaputte Wellendichtung ohne Code am Altteil?",
        route_name="engineering_case",
    )

    assert plan.goal == "identify_replacement_seal"
    assert "Innen- und Außendurchmesser" in plan.next_question
    assert "failure_diagnosis_detour" in plan.must_not_include


def test_leakage_plan_supplies_one_discriminating_question_without_case_gaps() -> None:
    plan = build_communication_plan(
        question="Der Wellendichtring ist undicht. Was soll ich prüfen?",
        route_name="leakage_troubleshooting",
    )

    assert plan.next_question.count("?") == 1
    assert "direkt nach Montage oder erst nach Betriebszeit" in plan.next_question
    assert "Montagefehler" in plan.question_reason


def test_solution_oriented_process_diagnosis_keeps_solution_goal_and_case_discriminator() -> None:
    plan = build_communication_plan(
        question=(
            "Die Gleitringdichtung am Mischer wird bei abrasivem, zähflüssigem Medium heiß "
            "und leckt. Entwickle eine sinnvolle Lösungsrichtung."
        ),
        route_name="leakage_troubleshooting",
        solution_requested=True,
    )

    assert plan.goal == "diagnose_failure"
    assert plan.depth == "normal"
    assert "provisional_solution_direction" in plan.must_include
    assert "Welches konkrete Medium" in plan.next_question
    assert "Feststoffanteil" in plan.next_question
    assert plan.max_questions == 1


def test_environmental_nbr_cracks_get_a_cause_specific_next_step() -> None:
    plan = build_communication_plan(
        question="NBR-Dichtung im Freien mit feinen Rissen an der Außenfläche: Ursache?",
        route_name="leakage_troubleshooting",
    )

    assert "Öl oder Fett" in plan.next_question
    assert "Ozon-/Witterungsriss" in plan.question_reason
    assert plan.next_question.count("?") == 1


def test_hardened_nbr_lip_asks_for_lip_temperature_and_exact_oil() -> None:
    plan = build_communication_plan(
        question="Der NBR-RWDR ist hart und rissig. Was tun?",
        route_name="leakage_troubleshooting",
    )

    assert "direkt an der Dichtlippe" in plan.next_question
    assert "Basis und Additivpaket" in plan.next_question
    assert "thermische Alterung" in plan.question_reason


def test_application_contrast_gets_a_runout_specific_next_step() -> None:
    plan = build_communication_plan(
        question=(
            "Der gleiche RWDR leckt im Rührwerk ständig, im baugleichen Getriebe nie."
        ),
        route_name="leakage_troubleshooting",
    )

    assert "Rundlauf" in plan.next_question
    assert "Rührwerk gegenüber dem Getriebe" in plan.next_question
    assert "dynamischen Kontakt" in plan.question_reason
    assert "application_contrast" in plan.must_include


def test_bare_application_request_is_bounded_to_one_grouped_question() -> None:
    plan = build_communication_plan(
        question="Ich brauche eine Dichtung für meine Pumpe.",
        route_name="engineering_case",
    )
    answer = render_case_clarification(plan)

    assert plan.goal == "clarify_under_specified_case"
    assert "rotierende Wellenabdichtung" in plan.next_question
    assert "welches Medium" in plan.next_question
    assert answer.count("?") == 1
    assert "wenigen Schritten" in answer
    assert "Vollkatalog" in answer


def test_steam_material_request_gets_brief_orientation_contract_and_one_key_question() -> (
    None
):
    plan = build_communication_plan(
        question="Bitte empfiehl mir ein Material für eine Wasserdampf-Anwendung.",
        route_name="engineering_case",
    )

    assert plan.goal == "orient_material_selection"
    assert plan.depth == "brief"
    assert "gesättigten oder überhitzten Dampf" in plan.next_question
    assert "Temperatur" in plan.next_question and "Druck" in plan.next_question
    assert plan.next_question.count("?") == 1


def test_dynamic_zero_leakage_target_gets_an_explicit_tradeoff_contract() -> None:
    plan = build_communication_plan(
        question="Maximale Dichtheit an der Welle, Leckage null – was ist optimal?",
        route_name="engineering_case",
    )

    assert plan.goal == "resolve_dynamic_sealing_tradeoff"
    assert "explicit_tradeoff" in plan.must_include
    assert "welche Leckagerate" in plan.next_question
    assert "Schmierfilm, Reibung und Verschleiß" in plan.question_reason
    assert plan.next_question.count("?") == 1
