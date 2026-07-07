"""Phase 2C (LangGraph-suitability audit) — exhaustive route-telemetry safety hardening tests.

Verifies, with synthetic sensitive-looking fixtures, that NOTHING in a RouteTelemetry event —
across the full field set and across every code path that constructs a ``route_reason`` string —
can ever carry raw user/assistant text, tenant_id, case_id, a file name, an exact medium name, an
exact technical value, or other customer data. The dataclass schema itself (route_name, reason,
confidence, forced_full_pipeline, deterministic_signal_count, route_latency_ms) structurally
excludes these fields; this suite proves the VALUES populating those six fields stay safe too,
not just that the schema looks safe on paper.
"""

from __future__ import annotations

import dataclasses

from sealai_v2.core.contracts import Intent
from sealai_v2.pipeline.route_telemetry import RouteTelemetry
from sealai_v2.pipeline.routing import classify_route

# Synthetic, never-real sensitive fixtures.
_SYNTHETIC_TENANT_ID = "tenant-musterfirma-9f3e2a"
_SYNTHETIC_CASE_ID = "case-2026-07-08-XYZ-001"
_SYNTHETIC_FILE_NAME = "zeichnung_kunde_musterfirma_v3.pdf"
_SYNTHETIC_CUSTOMER = "Musterfirma Dichtungstechnik GmbH"
_SYNTHETIC_EXACT_TEMP = "847.319"
_SYNTHETIC_EXACT_RPM = "16755.42"
_SYNTHETIC_MEDIUM = "Musterfirma-Spezial-Kuehlmittel-X99"

_LOADED_QUESTION = (
    f"Ich bin von {_SYNTHETIC_CUSTOMER} (Kunde {_SYNTHETIC_TENANT_ID}, Fall {_SYNTHETIC_CASE_ID}). "
    f"Anbei die Zeichnung {_SYNTHETIC_FILE_NAME}. Bei {_SYNTHETIC_EXACT_TEMP} Grad und "
    f"{_SYNTHETIC_EXACT_RPM} U/min mit {_SYNTHETIC_MEDIUM}, RWDR 45x62x8 -- passt FKM?"
)

_ALL_SYNTHETIC_SECRETS = (
    _SYNTHETIC_TENANT_ID,
    _SYNTHETIC_CASE_ID,
    _SYNTHETIC_FILE_NAME,
    _SYNTHETIC_CUSTOMER,
    _SYNTHETIC_EXACT_TEMP,
    _SYNTHETIC_EXACT_RPM,
    _SYNTHETIC_MEDIUM,
)


def _assert_telemetry_is_clean(ev: RouteTelemetry) -> None:
    dumped = repr(ev)
    for secret in _ALL_SYNTHETIC_SECRETS:
        assert (
            secret not in dumped
        ), f"leaked {secret!r} into RouteTelemetry: {dumped!r}"
    assert _LOADED_QUESTION not in dumped


class TestRouteTelemetrySchemaIsClosed:
    """The dataclass itself must never grow a field outside the approved safe set — this is the
    schema-level guardrail the field-by-field tests below build on."""

    def test_field_set_is_exactly_the_approved_safe_fields(self) -> None:
        names = {f.name for f in dataclasses.fields(RouteTelemetry)}
        assert names == {
            "route_name",
            "route_reason",
            "route_confidence",
            "forced_full_pipeline",
            "deterministic_signal_count",
            "route_latency_ms",
        }

    def test_no_field_name_suggests_raw_content_or_identifiers(self) -> None:
        forbidden_substrings = (
            "question",
            "answer",
            "text",
            "case_id",
            "tenant",
            "user_id",
            "session",
            "file",
            "medium",
            "customer",
            "prompt",
            "message",
        )
        for f in dataclasses.fields(RouteTelemetry):
            for forbidden in forbidden_substrings:
                assert forbidden not in f.name, f"field {f.name!r} looks unsafe"


class TestRouteReasonNeverCarriesRawContent:
    """Every reason= construction site in routing.py, exercised with a maximally sensitive-looking
    synthetic question, across every branch of classify_route (forced-full-pipeline routes,
    each Stage-2 cheap route, and the ambiguous/no-intent fallback)."""

    def test_forced_route_with_loaded_question(self) -> None:
        d = classify_route(_LOADED_QUESTION, intent=Intent.FALLARBEIT)
        assert d.forced_full_pipeline is True
        for secret in _ALL_SYNTHETIC_SECRETS:
            assert secret not in d.reason

    def test_smalltalk_route_with_loaded_question_embedded(self) -> None:
        # Even if a message masquerades as smalltalk while embedding sensitive-looking tokens,
        # the reason string must stay a fixed label -- and here Stage 1 fires anyway (dimensions/
        # values present), forcing the full path regardless of the GESPRAECH intent guess.
        d = classify_route(_LOADED_QUESTION, intent=Intent.GESPRAECH)
        for secret in _ALL_SYNTHETIC_SECRETS:
            assert secret not in d.reason

    def test_genuine_smalltalk_reason_is_a_fixed_label(self) -> None:
        d = classify_route("Hallo, wie geht es dir?", intent=Intent.GESPRAECH)
        assert d.reason == "intent=gespraech"

    def test_knowledge_route_reason_is_a_fixed_label(self) -> None:
        d = classify_route("Was ist PTFE?", intent=Intent.WISSENSFRAGE)
        assert d.reason == "intent=wissensfrage"

    def test_no_intent_reason_is_a_fixed_label(self) -> None:
        d = classify_route("...", intent=None)
        assert d.reason == "no_intent_available"

    def test_unklar_reason_is_a_fixed_label(self) -> None:
        d = classify_route("...", intent=Intent.UNKLAR)
        assert d.reason == "intent=unklar_no_signals"

    def test_deterministic_signal_reason_only_lists_signal_names_not_content(
        self,
    ) -> None:
        d = classify_route("RWDR 45x62x8 FKM 1500 U/min", intent=Intent.FALLARBEIT)
        assert d.reason.startswith("deterministic_signals:")
        # every token after the prefix must be a known, closed-vocabulary signal name
        signal_names = d.reason.removeprefix("deterministic_signals:").split(",")
        _KNOWN_SIGNAL_NAMES = {
            "designation_or_dimensions",
            "recognized_failure_symptom",
            "material_and_medium_known",
            "case_state_nonempty",
            "manufacturer_alternatives_request",
            "engineering_value_with_unit",
            "compression_or_interference_language",
            "rfq_language",
            "leakage_or_failure_language",
            "replacement_or_case_language",
            "suitability_or_recommendation_request",
            "meta_or_directive_language",
            "kinematic_or_calc_term",
            "resistance_or_suitability_claim",
            "material_and_medium_in_message",
            "comparison_with_material",
        }
        for name in signal_names:
            assert name in _KNOWN_SIGNAL_NAMES, f"unexpected token in reason: {name!r}"


class TestFullTelemetryEventWithSyntheticSecrets:
    """End-to-end: build the actual RouteTelemetry event (not just the RouteDecision) for the
    maximally-loaded synthetic question and assert nothing leaks."""

    def test_engineering_case_telemetry_is_clean(self) -> None:
        d = classify_route(_LOADED_QUESTION, intent=Intent.FALLARBEIT)
        ev = RouteTelemetry(
            route_name=d.route.value,
            route_reason=d.reason,
            route_confidence=d.confidence,
            forced_full_pipeline=d.forced_full_pipeline,
            deterministic_signal_count=d.deterministic_signal_count,
            route_latency_ms=1.23,
        )
        _assert_telemetry_is_clean(ev)

    def test_smalltalk_telemetry_is_clean(self) -> None:
        d = classify_route("Hallo, danke dir!", intent=Intent.GESPRAECH)
        ev = RouteTelemetry(
            route_name=d.route.value,
            route_reason=d.reason,
            route_confidence=d.confidence,
            forced_full_pipeline=d.forced_full_pipeline,
            deterministic_signal_count=d.deterministic_signal_count,
            route_latency_ms=0.5,
        )
        _assert_telemetry_is_clean(ev)
