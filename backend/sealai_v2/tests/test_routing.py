"""Phase 2B (LangGraph-suitability audit) — conservative route classification tests.

Core invariant under test throughout: the router may only become MORE conservative, never less.
Any deterministic engineering signal MUST force the full pipeline (forced_full_pipeline=True) —
this is asserted both per-case and as a standalone property test.
"""

from __future__ import annotations

from sealai_v2.core.contracts import Intent, Turn
from sealai_v2.pipeline.routing import (
    RouteName,
    classify_route,
    classify_route_deterministic,
    resolve_material_comparison_followup,
    detect_engineering_signals,
)


def test_material_comparison_followup_resolves_prior_user_subject() -> None:
    resolution = resolve_material_comparison_followup(
        "danke, bitte vergleiche mit ptfe",
        (
            Turn(role="user", text="Bitte gib mir Details ueber NBR"),
            Turn(role="assistant", text="NBR-Fachantwort"),
        ),
    )

    assert resolution is not None
    assert resolution.subjects == ("NBR", "PTFE")
    assert "NBR und PTFE" in resolution.resolved_question


def test_material_comparison_followup_does_not_trust_assistant_subjects() -> None:
    assert (
        resolve_material_comparison_followup(
            "Bitte vergleiche mit PTFE",
            (Turn(role="assistant", text="NBR waere eine Option"),),
        )
        is None
    )


def test_material_comparison_followup_rejects_case_bound_or_complete_queries() -> None:
    prior = (Turn(role="user", text="Details zu NBR"),)

    assert (
        resolve_material_comparison_followup("Vergleiche NBR und PTFE", prior) is None
    )
    assert (
        resolve_material_comparison_followup(
            "Vergleiche mit PTFE bei 130 °C in meiner Anwendung", prior
        )
        is None
    )


def test_material_comparison_followup_stops_at_explicit_topic_change() -> None:
    turns = (
        Turn(role="user", text="Details zu NBR"),
        Turn(role="assistant", text="NBR-Fachantwort"),
        Turn(role="user", text="Erklaere mir einen O-Ring"),
        Turn(role="assistant", text="O-Ring-Fachantwort"),
    )

    assert (
        resolve_material_comparison_followup("Bitte vergleiche mit PTFE", turns) is None
    )


class TestSmalltalkNavigation:
    def test_clear_smalltalk_routes_cheap(self) -> None:
        d = classify_route("Hallo, wie geht es dir?", intent=Intent.GESPRAECH)
        assert d.route == RouteName.SMALLTALK_NAVIGATION
        assert d.forced_full_pipeline is False
        assert d.deterministic_signal_count == 0

    def test_thanks_and_greeting_variants(self) -> None:
        for q in ("Danke dir!", "Guten Morgen", "Vielen Dank fuer die Hilfe"):
            d = classify_route(q, intent=Intent.GESPRAECH)
            assert d.route == RouteName.SMALLTALK_NAVIGATION
            assert d.forced_full_pipeline is False

    def test_natural_courtesy_after_greeting_routes_smalltalk(self) -> None:
        d = classify_route("Hallo, schön dass es euch gibt!", intent=Intent.GESPRAECH)
        assert d.route == RouteName.SMALLTALK_NAVIGATION
        assert d.forced_full_pipeline is False

    def test_greeting_never_hides_engineering_signal(self) -> None:
        d = classify_route(
            "Hallo, ich brauche eine Dichtung für 150 °C.", intent=Intent.GESPRAECH
        )
        assert d.route == RouteName.ENGINEERING_CASE
        assert d.forced_full_pipeline is True

    def test_greeting_never_hides_material_knowledge(self) -> None:
        for question in (
            "Hallo und guten Morgen, bitte gebe mir Details zu NBR",
            "Hallo, kannst du mir sagen, was NBR ist?",
            "Ich brauche Informationen ueber NBR",
        ):
            for decision in (
                classify_route(question, intent=Intent.GESPRAECH),
                classify_route_deterministic(question),
            ):
                assert decision.route is RouteName.MATERIAL_KNOWLEDGE, question
                assert decision.forced_full_pipeline is False

    def test_unknown_content_after_greeting_is_never_swallowed_as_smalltalk(
        self,
    ) -> None:
        decision = classify_route_deterministic(
            "Hallo, ordne bitte das unbekannte Fachthema ZetaSeal ein"
        )
        assert decision.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
        assert decision.forced_full_pipeline is True


class TestGeneralAndMaterialKnowledge:
    def test_general_ptfe_knowledge_question_routes_material_knowledge(self) -> None:
        d = classify_route("Was ist PTFE?", intent=Intent.WISSENSFRAGE)
        assert d.route == RouteName.MATERIAL_KNOWLEDGE
        assert d.forced_full_pipeline is False
        assert d.deterministic_signal_count == 0

    def test_general_sealing_knowledge_question_without_material_name(self) -> None:
        d = classify_route(
            "Was ist eine Dichtung allgemein?", intent=Intent.WISSENSFRAGE
        )
        assert d.route == RouteName.GENERAL_SEALING_KNOWLEDGE
        assert d.forced_full_pipeline is False

    def test_faktfrage_with_material_name_is_material_knowledge(self) -> None:
        d = classify_route("Ist FKM ein Elastomer?", intent=Intent.FAKTFRAGE)
        assert d.route == RouteName.MATERIAL_KNOWLEDGE
        assert d.forced_full_pipeline is False

    def test_catalog_material_term_routes_without_router_code_change(self) -> None:
        d = classify_route_deterministic(
            "Bitte erklaere mir AEM",
            material_terms=("AEM", "Ethylen-Acrylat-Kautschuk"),
        )
        assert d.route is RouteName.MATERIAL_KNOWLEDGE
        assert d.forced_full_pipeline is False

    def test_ambiguous_short_catalog_term_requires_canonical_uppercase(self) -> None:
        assert (
            classify_route_deterministic(
                "Was bedeutet die EU-Regel?", material_terms=("EU",)
            ).route
            is not RouteName.MATERIAL_KNOWLEDGE
        )
        assert (
            classify_route_deterministic("Details zu CR", material_terms=("CR",)).route
            is RouteName.MATERIAL_KNOWLEDGE
        )

    def test_current_knowledge_question_outranks_existing_case_context(self) -> None:
        d = classify_route_deterministic("Details ueber NBR", case_state_nonempty=True)
        assert d.route is RouteName.MATERIAL_KNOWLEDGE
        assert d.forced_full_pipeline is False

    def test_explicit_oring_design_overview_is_not_misrouted_as_a_case(self) -> None:
        question = (
            "Erkläre die technische Auslegung eines O-Rings auf Ingenieursniveau: "
            "Dichtprinzip, Verpressung, Einbaudehnung, Nutfüllgrad, Extrusionsspalt, "
            "Toleranzkette, Oberflächen, Werkstoff-/Medieneinfluss, Versagensbilder und "
            "die Rolle von ISO 3601."
        )
        for decision in (
            classify_route(question, intent=Intent.WISSENSFRAGE),
            classify_route_deterministic(question),
        ):
            assert decision.route is RouteName.GENERAL_SEALING_KNOWLEDGE
            assert decision.forced_full_pipeline is False
            assert decision.deterministic_signal_count == 0

    def test_incidental_diagnosis_match_does_not_hijack_knowledge_overview(
        self,
    ) -> None:
        question = (
            "Erkläre die technische Auslegung eines O-Rings: Verpressung, "
            "Extrusionsspalt und Versagensbilder."
        )
        decision = classify_route_deterministic(
            question,
            diagnosis={"ursache": "Spaltextrusion", "fix": "Stützring"},
        )
        assert decision.route is RouteName.GENERAL_SEALING_KNOWLEDGE
        assert decision.forced_full_pipeline is False
        assert decision.deterministic_signal_count == 0

    def test_short_oring_compression_explanation_is_knowledge(self) -> None:
        decision = classify_route_deterministic(
            "Erkläre die Verpressung und Auslegung eines O-Rings."
        )
        assert decision.route is RouteName.GENERAL_SEALING_KNOWLEDGE
        assert decision.forced_full_pipeline is False

    def test_glrd_overview_may_name_leakage_and_failure_mechanisms(self) -> None:
        question = (
            "Erkläre eine Gleitringdichtung auf Ingenieursniveau: Dichtspalt und "
            "Leckage, Gleitflächen, Schmierfilm, Bauformen und Druckentlastung, "
            "Werkstoffpaarungen, Prozessphase/Dampfdruck/Feststoffe, Versorgungssysteme, "
            "Versagensmechanismen sowie ISO 21049/API 682."
        )
        for decision in (
            classify_route(question, intent=Intent.WISSENSFRAGE),
            classify_route_deterministic(question),
        ):
            assert decision.route is RouteName.GENERAL_SEALING_KNOWLEDGE
            assert decision.forced_full_pipeline is False
            assert decision.deterministic_signal_count == 0

    def test_case_bound_leakage_explanation_stays_troubleshooting(self) -> None:
        decision = classify_route_deterministic(
            "Erkläre, warum meine Gleitringdichtung leckt."
        )
        assert decision.route is RouteName.LEAKAGE_TROUBLESHOOTING
        assert decision.forced_full_pipeline is True

    def test_engineering_method_for_unknown_hydraulic_medium_is_knowledge(self) -> None:
        question = (
            "Wie muss ein Dichtungsingenieur die Verträglichkeit eines unbekannten "
            "Hydraulikmediums wie Skydrol bewerten? Nenne die erforderliche Stoffidentität, "
            "Konzentration/Additive, Temperatur/Phase, Prüfmethodik, Werkstoffwechselwirkungen, "
            "Systemeffekte und warum keine pauschale Freigabe zulässig ist."
        )
        decision = classify_route_deterministic(question)
        assert decision.route is RouteName.GENERAL_SEALING_KNOWLEDGE
        assert decision.forced_full_pipeline is False
        assert decision.deterministic_signal_count == 0

    def test_concrete_hydraulic_medium_suitability_stays_full(self) -> None:
        decision = classify_route_deterministic(
            "Ist NBR für mein Hydraulikmedium Skydrol bei 80 °C geeignet?"
        )
        assert decision.route is RouteName.ENGINEERING_CASE
        assert decision.forced_full_pipeline is True
        assert decision.deterministic_signal_count >= 1


class TestMaterialComparison:
    def test_explicit_comparison_question_forces_full_pipeline(self) -> None:
        d = classify_route("PTFE vs FKM, was ist besser?", intent=Intent.WISSENSFRAGE)
        assert d.route == RouteName.MATERIAL_COMPARISON
        assert d.forced_full_pipeline is True

    def test_comparison_axes_do_not_become_a_reported_failure(self) -> None:
        question = (
            "Vergleiche NBR und PTFE als Dichtungswerkstoffe auf Ingenieursniveau. "
            "Nutze dieselben Achsen: Werkstoffklasse, Rückstellung/Kriechen, Temperatur, "
            "Medienverhalten, Reibung/Verschleiß, Bauformen, typische Anwendungen, Grenzen, "
            "Versagensmechanismen und Auswahlparameter. Nenne keinen universellen Sieger."
        )
        decision = classify_route_deterministic(
            question,
            diagnosis={"ursache": "RWDR-Verschleiß", "fix": "Welle prüfen"},
        )
        assert decision.route is RouteName.MATERIAL_COMPARISON
        assert decision.forced_full_pipeline is True
        assert decision.deterministic_signal_count == 1

    def test_concrete_comparison_with_operating_value_is_not_suppressed(self) -> None:
        decision = classify_route_deterministic(
            "NBR oder PTFE für meine Dichtung bei 130 °C: was ist besser?",
            diagnosis={"ursache": "Schaden", "fix": "prüfen"},
        )
        assert decision.route is RouteName.LEAKAGE_TROUBLESHOOTING
        assert decision.forced_full_pipeline is True

    def test_comparison_forces_even_when_intent_says_knowledge(self) -> None:
        """The trap catalog's sharpest edge (comparative-suitability claims) must force the full
        path regardless of what the soft LLM intent guessed — the deterministic signal wins."""
        d = classify_route(
            "Welches Material ist besser, EPDM oder Silikon?",
            intent=Intent.WISSENSFRAGE,
        )
        assert d.forced_full_pipeline is True
        assert d.route == RouteName.MATERIAL_COMPARISON

    def test_vor_und_nachteile_phrasing(self) -> None:
        d = classify_route(
            "Vor- und Nachteile von NBR gegenueber HNBR?", intent=Intent.WISSENSFRAGE
        )
        assert d.forced_full_pipeline is True
        assert d.route == RouteName.MATERIAL_COMPARISON


class TestEngineeringCase:
    def test_request_for_a_seal_is_an_application_not_general_knowledge(self) -> None:
        d = classify_route_deterministic("Ich brauche eine Dichtung")
        assert d.route is RouteName.ENGINEERING_CASE
        assert d.forced_full_pipeline is True

    def test_concrete_rwdr_case_with_dimensions_forces_full_pipeline(self) -> None:
        d = classify_route(
            "RWDR 45x62x8 FKM, 1500 U/min, welches Material?", intent=Intent.FALLARBEIT
        )
        assert d.forced_full_pipeline is True
        assert d.route == RouteName.ENGINEERING_CASE

    def test_dimensions_like_45x62x8_alone_force_full_pipeline(self) -> None:
        d = classify_route("Passt das fuer 45x62x8?", intent=None)
        assert d.forced_full_pipeline is True

    def test_pressure_temperature_rpm_question_forces_full_pipeline(self) -> None:
        for q in (
            "Wie hoch darf der Druck bei 10 bar sein?",
            "Ist 150 °C fuer FKM okay?",
            "Bei 1500 U/min, welche Dichtung?",
        ):
            d = classify_route(q, intent=Intent.WISSENSFRAGE)
            assert d.forced_full_pipeline is True, q

    def test_medium_and_operating_condition_combination_forces_full_pipeline(
        self,
    ) -> None:
        d = classify_route(
            "Ist PTFE fuer Hydrauliköl geeignet?", intent=Intent.FALLARBEIT
        )
        assert d.forced_full_pipeline is True
        assert d.route == RouteName.ENGINEERING_CASE

    def test_replacement_case_language_forces_full_pipeline(self) -> None:
        d = classify_route(
            "Ich brauche einen Ersatz fuer meine Dichtung.", intent=Intent.FALLARBEIT
        )
        assert d.forced_full_pipeline is True

    def test_compression_language_forces_full_pipeline(self) -> None:
        d = classify_route(
            "Wie viel Verpressung braucht der O-Ring?", intent=Intent.FALLARBEIT
        )
        assert d.forced_full_pipeline is True

    def test_concrete_values_keep_explanation_shaped_design_question_on_full_path(
        self,
    ) -> None:
        d = classify_route_deterministic(
            "Erkläre die Auslegung meines O-Rings bei 10 bar und 120 °C."
        )
        assert d.route is RouteName.ENGINEERING_CASE
        assert d.forced_full_pipeline is True

    def test_concrete_values_keep_diagnosis_signal_on_full_path(self) -> None:
        d = classify_route_deterministic(
            "Erkläre die Extrusion meines O-Rings bei 10 bar.",
            diagnosis={"ursache": "Spaltextrusion", "fix": "Stützring"},
        )
        assert d.route is RouteName.LEAKAGE_TROUBLESHOOTING
        assert d.forced_full_pipeline is True

    def test_possessive_case_reference_keeps_design_question_on_full_path(self) -> None:
        d = classify_route_deterministic("Erkläre meine O-Ring-Auslegung.")
        assert d.route is RouteName.ENGINEERING_CASE
        assert d.forced_full_pipeline is True


class TestLeakageTroubleshooting:
    def test_leakage_case_forces_full_pipeline(self) -> None:
        d = classify_route("Meine Dichtung leckt, was tun?", intent=Intent.FALLARBEIT)
        assert d.forced_full_pipeline is True
        assert d.route == RouteName.LEAKAGE_TROUBLESHOOTING

    def test_leakage_verb_forms(self) -> None:
        for q in (
            "Der RWDR tropft seit gestern.",
            "Die Dichtung ist undicht geworden.",
        ):
            d = classify_route(q, intent=Intent.FALLARBEIT)
            assert d.forced_full_pipeline is True, q
            assert d.route == RouteName.LEAKAGE_TROUBLESHOOTING


class TestRfqManufacturerBrief:
    def test_rfq_request_forces_full_pipeline(self) -> None:
        d = classify_route("Bitte RFQ fuer Herstelleranfrage", intent=None)
        assert d.forced_full_pipeline is True
        assert d.route == RouteName.RFQ_MANUFACTURER_BRIEF

    def test_manufacturer_alternatives_request_forces_full_pipeline(self) -> None:
        d = classify_route(
            "Welcher Hersteller kann eine vergleichbare Dichtung liefern?", intent=None
        )
        assert d.forced_full_pipeline is True


class TestAmbiguousAndMissingIntent:
    def test_ambiguous_technical_request_with_no_intent_forces_full_pipeline(
        self,
    ) -> None:
        d = classify_route("Kannst du mir helfen?", intent=None)
        assert d.route == RouteName.UNSUPPORTED_OR_AMBIGUOUS
        assert d.forced_full_pipeline is True

    def test_unklar_intent_forces_full_pipeline(self) -> None:
        d = classify_route("Ähm, also, das mit dem Ding da...", intent=Intent.UNKLAR)
        assert d.route == RouteName.UNSUPPORTED_OR_AMBIGUOUS
        assert d.forced_full_pipeline is True

    def test_fallarbeit_intent_with_zero_signals_still_forces_full_pipeline(
        self,
    ) -> None:
        """Defensive: if understand() ever says fallarbeit despite zero deterministic signals,
        doubt must still win — never trust the soft LLM label alone."""
        d = classify_route("irgendwas technisches", intent=Intent.FALLARBEIT)
        assert d.forced_full_pipeline is True


class TestCaseStateAndPipelineHints:
    def test_nonempty_case_state_forces_full_pipeline_even_for_a_short_followup(
        self,
    ) -> None:
        """A case already in progress must never downgrade on a short follow-up turn like 'und?'"""
        d = classify_route("und?", case_state_nonempty=True, intent=Intent.GESPRAECH)
        assert d.forced_full_pipeline is True

    def test_decode_result_hint_forces_full_pipeline(self) -> None:
        d = classify_route(
            "passt das so", decode_result={"dims_mm": (45, 62, 8)}, intent=None
        )
        assert d.forced_full_pipeline is True

    def test_diagnosis_hint_forces_leakage_route(self) -> None:
        d = classify_route(
            "was mache ich jetzt",
            diagnosis={"ursache": "x", "fix": "y"},
            intent=Intent.GESPRAECH,
        )
        assert d.forced_full_pipeline is True
        assert d.route == RouteName.LEAKAGE_TROUBLESHOOTING

    def test_gegencheck_verdict_hint_forces_full_pipeline(self) -> None:
        d = classify_route(
            "und weiter?",
            gegencheck_verdict={"bewertung": "vertraeglich"},
            intent=Intent.GESPRAECH,
        )
        assert d.forced_full_pipeline is True


class TestFalsePositiveSafety:
    """Cases explicitly checking the router does NOT over-trigger on knowledge-question phrasing
    that superficially resembles engineering language but carries no real signal."""

    def test_bare_material_name_alone_never_forces(self) -> None:
        d = classify_route("PTFE ist ein Fluorpolymer.", intent=Intent.WISSENSFRAGE)
        assert d.forced_full_pipeline is False

    def test_bare_seal_type_word_alone_never_forces(self) -> None:
        d = classify_route("Was ist ein RWDR?", intent=Intent.WISSENSFRAGE)
        assert d.forced_full_pipeline is False

    def test_bare_medium_name_alone_never_forces(self) -> None:
        d = classify_route(
            "Was ist Hydrauliköl chemisch gesehen?", intent=Intent.WISSENSFRAGE
        )
        assert d.forced_full_pipeline is False

    def test_number_without_engineering_unit_never_forces(self) -> None:
        d = classify_route("Ich habe 3 Fragen an dich.", intent=Intent.GESPRAECH)
        assert d.forced_full_pipeline is False


class TestForcedFullPipelineInvariant:
    """Property-style: ANY non-empty detect_engineering_signals() result must, through
    classify_route, always yield forced_full_pipeline=True — never a route in CHEAP_ROUTES."""

    _SIGNAL_BEARING_QUESTIONS = [
        "RWDR 45x62x8 FKM",
        "1500 U/min",
        "10 bar Druck",
        "150 °C",
        "PV-Wert berechnen",
        "Verpressung pruefen",
        "RFQ anfrage bitte",
        "Dichtung leckt",
        "Ersatzteil auslegen",
        "PTFE vs FKM",
        "Ist PTFE fuer Öl geeignet",
    ]

    def test_every_signal_bearing_question_forces_full_pipeline(self) -> None:
        for q in self._SIGNAL_BEARING_QUESTIONS:
            signals = detect_engineering_signals(q)
            if not signals:
                continue  # this particular phrasing didn't trip a signal; not what's under test
            d = classify_route(
                q, intent=Intent.WISSENSFRAGE
            )  # even with a "cheap" intent guess
            assert (
                d.forced_full_pipeline is True
            ), f"{q!r} had signals {signals} but was not forced"
            from sealai_v2.pipeline.routing import CHEAP_ROUTES

            assert d.route not in CHEAP_ROUTES

    def test_at_least_one_signal_bearing_question_exists_in_the_fixture(self) -> None:
        """Guards the test above against a silent no-op (every fixture failing detection)."""
        assert any(
            detect_engineering_signals(q) for q in self._SIGNAL_BEARING_QUESTIONS
        )
