"""Route-aware chat-UI display flags — the trust-bug fix.

Two layers are exercised here:

  1. ``pipeline/route_prompt_matrix.py`` — every RouteName's four ``show_*`` render flags carry the
     exact, reviewed values (smalltalk/off-topic show NOTHING; knowledge routes show evidence only;
     engineering/RFQ keep the full section set). This is the one authoritative per-route table.

  2. ``api/serializers.py::chat_response()`` — the flags reach the wire, AND the backward-compat
     default holds: when no route was classified (``route_name`` None/absent, or an unrecognized
     value) all four flags default to True, i.e. today's always-show behavior is byte-unchanged.

Render-only: none of this touches L1/L3/kernel/RAG. Offline, no LLM.
"""

from __future__ import annotations

import pytest

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import Answer, Flags, PipelineResult
from sealai_v2.pipeline.route_prompt_matrix import plan_for
from sealai_v2.pipeline.routing import RouteName

# The single source of truth for what each route may show, per the reviewed design.
# (technical_preassessment, evidence, calculations, rfq_sections)
EXPECTED_FLAGS: dict[RouteName, tuple[bool, bool, bool, bool]] = {
    RouteName.SMALLTALK_NAVIGATION: (False, False, False, False),
    RouteName.GENERAL_SEALING_KNOWLEDGE: (False, True, False, False),
    RouteName.MATERIAL_KNOWLEDGE: (False, True, False, False),
    RouteName.MATERIAL_COMPARISON: (False, True, False, False),
    RouteName.ENGINEERING_CASE: (True, True, True, True),
    RouteName.LEAKAGE_TROUBLESHOOTING: (True, True, True, False),
    RouteName.RFQ_MANUFACTURER_BRIEF: (True, True, True, True),
    RouteName.UNSUPPORTED_OR_AMBIGUOUS: (False, False, False, False),
}


class TestMatrixDisplayFlags:
    @pytest.mark.parametrize("route", list(RouteName))
    def test_every_route_has_the_reviewed_flag_values(self, route: RouteName) -> None:
        plan = plan_for(route)
        assert (
            plan.show_technical_preassessment,
            plan.show_evidence,
            plan.show_calculations,
            plan.show_rfq_sections,
        ) == EXPECTED_FLAGS[route], f"display flags drifted for {route.value}"

    def test_smalltalk_and_offtopic_show_nothing(self) -> None:
        for route in (
            RouteName.SMALLTALK_NAVIGATION,
            RouteName.UNSUPPORTED_OR_AMBIGUOUS,
        ):
            plan = plan_for(route)
            assert not any(
                (
                    plan.show_technical_preassessment,
                    plan.show_evidence,
                    plan.show_calculations,
                    plan.show_rfq_sections,
                )
            )

    def test_material_comparison_l3_flag_is_untouched(self) -> None:
        # Guard the explicit design constraint: adding display flags must not have touched L3.
        assert plan_for(RouteName.MATERIAL_COMPARISON).l3 is True


def _result(route_name: str | None) -> PipelineResult:
    return PipelineResult(
        question="Hallo, wer bist du?",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
        route_name=route_name,
    )


class TestChatResponseDisplayFlags:
    def test_defaults_all_true_when_route_name_absent(self) -> None:
        # Backward compat: route optimization off / first request → today's always-show behavior.
        out = chat_response(_result(None))
        assert out["route_name"] is None
        assert out["show_technical_preassessment"] is True
        assert out["show_evidence"] is True
        assert out["show_calculations"] is True
        assert out["show_rfq_sections"] is True

    def test_defaults_all_true_for_unrecognized_route(self) -> None:
        # A future / unknown route value must also fall back to always-show, never crash.
        out = chat_response(_result("some_future_route"))
        assert out["show_technical_preassessment"] is True
        assert out["show_evidence"] is True
        assert out["show_calculations"] is True
        assert out["show_rfq_sections"] is True

    def test_smalltalk_narrows_everything_off(self) -> None:
        out = chat_response(_result(RouteName.SMALLTALK_NAVIGATION.value))
        assert out["route_name"] == "smalltalk_navigation"
        assert out["show_technical_preassessment"] is False
        assert out["show_evidence"] is False
        assert out["show_calculations"] is False
        assert out["show_rfq_sections"] is False

    def test_general_knowledge_shows_evidence_only(self) -> None:
        out = chat_response(_result(RouteName.GENERAL_SEALING_KNOWLEDGE.value))
        assert out["show_technical_preassessment"] is False
        assert out["show_evidence"] is True
        assert out["show_calculations"] is False
        assert out["show_rfq_sections"] is False

    def test_engineering_case_keeps_full_section_set(self) -> None:
        out = chat_response(_result(RouteName.ENGINEERING_CASE.value))
        assert out["show_technical_preassessment"] is True
        assert out["show_evidence"] is True
        assert out["show_calculations"] is True
        assert out["show_rfq_sections"] is True
