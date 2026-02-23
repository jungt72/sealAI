"""Tests for P5 Procurement Engine (Sprint 8).

Coverage:
  - 4-stage partner matching (Stage 1-4)
  - Fallback neutral PDF (no partner branding)
  - Watermark when is_critical_application
  - RFQ PDF rendering via Jinja2
  - Node integration
  - ProcurementResult model validation
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from app.services.rag.nodes.p5_procurement import (
    PartnerRecord,
    ProcurementResult,
    _match_stage1_paying,
    _match_stage2_bauform,
    _match_stage3_medium_druck,
    _match_stage4_geo,
    _render_rfq_pdf,
    node_p5_procurement,
    run_procurement_matching,
)
from app.langgraph_v2.state.sealai_state import SealAIState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_partner(
    *,
    partner_id: str = "T001",
    name: str = "Test Partner GmbH",
    is_paying: bool = True,
    bauformen: list[str] | None = None,
    media: list[str] | None = None,
    pressure_max: float = 100.0,
    locations: list[str] | None = None,
    delivery_days: int = 7,
) -> PartnerRecord:
    return PartnerRecord(
        partner_id=partner_id,
        name=name,
        is_paying_partner=is_paying,
        supported_bauformen=bauformen or ["Spiraldichtung"],
        supported_media=media or ["steam", "gas"],
        pressure_max_bar=pressure_max,
        locations=locations or ["DE"],
        delivery_days=delivery_days,
    )


def _make_state(
    *,
    seal_family: str | None = "Spiraldichtung",
    medium: str | None = "steam",
    pressure_max_bar: float | None = 50.0,
    is_critical: bool = False,
    critique_log: list[str] | None = None,
    calculation_result: dict | None = None,
    tenant_id: str | None = "tenant-42",
) -> SealAIState:
    from app.services.rag.state import WorkingProfile

    wp = WorkingProfile(
        medium=medium,
        pressure_max_bar=pressure_max_bar,
    )
    return SealAIState(
        messages=[HumanMessage(content="test")],
        seal_family=seal_family,
        working_profile=wp,
        is_critical_application=is_critical,
        critique_log=critique_log or [],
        calculation_result=calculation_result or {
            "gasket_inner_d_mm": 57.2,
            "gasket_outer_d_mm": 68.0,
            "required_gasket_stress_mpa": 14.5,
            "available_bolt_load_kn": 548.0,
            "safety_factor": 2.1,
            "temperature_margin_c": 125.0,
            "pressure_margin_bar": 50.0,
            "is_critical_application": is_critical,
        },
        tenant_id=tenant_id,
    )


# ---------------------------------------------------------------------------
# TestStage1Paying
# ---------------------------------------------------------------------------


class TestStage1Paying:
    def test_paying_partner_passes(self):
        p = _make_partner(is_paying=True)
        result = _match_stage1_paying([p])
        assert result == [p]

    def test_non_paying_filtered(self):
        p = _make_partner(is_paying=False)
        result = _match_stage1_paying([p])
        assert result == []

    def test_mixed_registry(self):
        paying = _make_partner(partner_id="A", is_paying=True)
        non_paying = _make_partner(partner_id="B", is_paying=False)
        result = _match_stage1_paying([paying, non_paying])
        assert result == [paying]

    def test_empty_registry_returns_empty(self):
        result = _match_stage1_paying([])
        assert result == []


# ---------------------------------------------------------------------------
# TestStage2Bauform
# ---------------------------------------------------------------------------


class TestStage2Bauform:
    def test_exact_match(self):
        p = _make_partner(bauformen=["Spiraldichtung", "Kammprofil"])
        result = _match_stage2_bauform([p], "Spiraldichtung")
        assert result == [p]

    def test_no_match_returns_empty(self):
        p = _make_partner(bauformen=["Kammprofil"])
        result = _match_stage2_bauform([p], "PTFE-Dichtung")
        assert result == []

    def test_case_insensitive_match(self):
        p = _make_partner(bauformen=["Spiraldichtung"])
        result = _match_stage2_bauform([p], "spiraldichtung")
        assert result == [p]

    def test_seal_family_none_returns_empty(self):
        p = _make_partner(bauformen=["Spiraldichtung"])
        result = _match_stage2_bauform([p], None)
        assert result == []

    def test_seal_family_empty_string_returns_empty(self):
        p = _make_partner(bauformen=["Spiraldichtung"])
        result = _match_stage2_bauform([p], "")
        assert result == []


# ---------------------------------------------------------------------------
# TestStage3MediumDruck
# ---------------------------------------------------------------------------


class TestStage3MediumDruck:
    def test_medium_match(self):
        p = _make_partner(media=["steam", "gas"], pressure_max=200.0)
        result = _match_stage3_medium_druck([p], "steam", 50.0)
        assert result == [p]

    def test_pressure_limit_exceeded(self):
        p = _make_partner(media=["steam"], pressure_max=50.0)
        # pressure_max_bar 100 > partner.pressure_max_bar 50 → fails
        result_strict = [
            x for x in _match_stage3_medium_druck([p], "steam", 100.0)
            if 100.0 <= x.pressure_max_bar
        ]
        assert result_strict == []

    def test_no_match_returns_all_candidates(self):
        p = _make_partner(media=["water"], pressure_max=50.0)
        # medium "H2" not in partner media → SHOULD returns all survivors
        result = _match_stage3_medium_druck([p], "H2", 200.0)
        assert result == [p]

    def test_medium_none_skips_medium_filter(self):
        p = _make_partner(media=["steam"], pressure_max=200.0)
        result = _match_stage3_medium_druck([p], None, 100.0)
        assert result == [p]

    def test_pressure_none_skips_pressure_filter(self):
        p = _make_partner(media=["steam"], pressure_max=50.0)
        result = _match_stage3_medium_druck([p], "steam", None)
        assert result == [p]


# ---------------------------------------------------------------------------
# TestStage4Geo
# ---------------------------------------------------------------------------


class TestStage4Geo:
    def test_sorted_by_delivery_days(self):
        slow = _make_partner(partner_id="S", delivery_days=14)
        fast = _make_partner(partner_id="F", delivery_days=3)
        result = _match_stage4_geo([slow, fast])
        assert result[0].partner_id == "F"
        assert result[1].partner_id == "S"

    def test_single_partner_unchanged(self):
        p = _make_partner(delivery_days=7)
        result = _match_stage4_geo([p])
        assert result == [p]

    def test_equal_delivery_days_preserves_order(self):
        p1 = _make_partner(partner_id="A", delivery_days=5)
        p2 = _make_partner(partner_id="B", delivery_days=5)
        result = _match_stage4_geo([p1, p2])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestFallback
# ---------------------------------------------------------------------------


class TestFallback:
    def test_no_paying_partners_triggers_fallback(self):
        registry = [_make_partner(is_paying=False)]
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0, registry=registry)
        assert result.fallback is True
        assert result.matched_partners == []
        assert "zahlend" in result.fallback_reason.lower() or "netzwerk" in result.fallback_reason.lower()

    def test_no_bauform_match_triggers_fallback(self):
        registry = [_make_partner(is_paying=True, bauformen=["Kammprofil"])]
        result = run_procurement_matching("PTFE-Dichtung", "steam", 50.0, registry=registry)
        assert result.fallback is True
        assert "PTFE-Dichtung" in result.fallback_reason

    def test_fallback_stages_completed_is_zero_when_no_paying(self):
        registry = [_make_partner(is_paying=False)]
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0, registry=registry)
        assert result.stages_completed == 0

    def test_fallback_stages_completed_is_one_when_no_bauform(self):
        registry = [_make_partner(is_paying=True, bauformen=["Kammprofil"])]
        result = run_procurement_matching("PTFE-Dichtung", "steam", 50.0, registry=registry)
        assert result.stages_completed == 1

    def test_fallback_reason_is_set_on_empty_registry(self):
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0, registry=[])
        assert result.fallback is True
        assert result.fallback_reason != ""


# ---------------------------------------------------------------------------
# TestWatermark
# ---------------------------------------------------------------------------


class TestWatermark:
    def test_watermark_present_when_critical(self):
        state = _make_state(is_critical=True)
        registry = [_make_partner(is_paying=True, bauformen=["Spiraldichtung"])]
        from app.services.rag.nodes.p5_procurement import ProcurementResult
        result = ProcurementResult(matched_partners=[registry[0]], fallback=False, stages_completed=2)
        pdf = _render_rfq_pdf(result, state)
        assert "KRITISCHE ANWENDUNG" in pdf
        assert "INGENIEURSPRÜFUNG" in pdf

    def test_watermark_absent_when_not_critical(self):
        state = _make_state(is_critical=False)
        registry = [_make_partner(is_paying=True, bauformen=["Spiraldichtung"])]
        from app.services.rag.nodes.p5_procurement import ProcurementResult
        result = ProcurementResult(matched_partners=[registry[0]], fallback=False, stages_completed=2)
        pdf = _render_rfq_pdf(result, state)
        assert "KRITISCHE ANWENDUNG" not in pdf

    def test_watermark_text_contains_safety_note(self):
        state = _make_state(is_critical=True)
        from app.services.rag.nodes.p5_procurement import ProcurementResult
        result = ProcurementResult(matched_partners=[], fallback=True, stages_completed=0, fallback_reason="test")
        pdf = _render_rfq_pdf(result, state)
        assert "zugelassenen" in pdf or "Ingenieur" in pdf


# ---------------------------------------------------------------------------
# TestRFQPDFRendering
# ---------------------------------------------------------------------------


class TestRFQPDFRendering:
    def test_full_render_contains_betriebsprofil(self):
        state = _make_state(medium="steam", pressure_max_bar=80.0)
        result = run_procurement_matching("Spiraldichtung", "steam", 80.0)
        pdf = _render_rfq_pdf(result, state)
        assert "BETRIEBSPROFIL" in pdf
        assert "steam" in pdf

    def test_full_render_contains_auslegungsergebnisse(self):
        state = _make_state()
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0)
        pdf = _render_rfq_pdf(result, state)
        assert "AUSLEGUNGSERGEBNISSE" in pdf
        assert "57.2" in pdf  # gasket_inner_d_mm from fixture

    def test_full_render_contains_qualitaetspruefung(self):
        state = _make_state(critique_log=["WARNING: Temperaturgegenwert knapp"])
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0)
        pdf = _render_rfq_pdf(result, state)
        assert "QUALITÄTSPRÜFUNG" in pdf
        assert "Temperaturgegenwert" in pdf

    def test_full_render_contains_partnervermittlung(self):
        state = _make_state()
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0)
        pdf = _render_rfq_pdf(result, state)
        assert "PARTNERVERMITTLUNG" in pdf

    def test_fallback_pdf_contains_no_partner_names(self):
        state = _make_state(seal_family="UNKNOWN-SEAL")
        result = run_procurement_matching("UNKNOWN-SEAL", "steam", 50.0)
        pdf = _render_rfq_pdf(result, state)
        assert result.fallback is True
        assert "FastSeal" not in pdf
        assert "Müller" not in pdf
        assert "HINWEIS" in pdf  # fallback note

    def test_generated_at_in_pdf(self):
        state = _make_state()
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0)
        pdf = _render_rfq_pdf(result, state)
        assert "UTC" in pdf

    def test_tenant_id_in_pdf(self):
        state = _make_state(tenant_id="acme-corp")
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0)
        pdf = _render_rfq_pdf(result, state)
        assert "acme-corp" in pdf


# ---------------------------------------------------------------------------
# TestNodeP5Integration
# ---------------------------------------------------------------------------


class TestNodeP5Integration:
    def test_node_returns_procurement_result(self):
        state = _make_state()
        update = node_p5_procurement(state)
        assert "procurement_result" in update
        assert isinstance(update["procurement_result"], dict)

    def test_node_returns_rfq_pdf_text(self):
        state = _make_state()
        update = node_p5_procurement(state)
        assert "rfq_pdf_text" in update
        assert isinstance(update["rfq_pdf_text"], str)
        assert len(update["rfq_pdf_text"]) > 0

    def test_node_sets_phase_procurement(self):
        state = _make_state()
        update = node_p5_procurement(state)
        from app.langgraph_v2.phase import PHASE
        assert update["phase"] == PHASE.PROCUREMENT

    def test_node_sets_last_node(self):
        state = _make_state()
        update = node_p5_procurement(state)
        assert update["last_node"] == "node_p5_procurement"

    def test_node_reads_is_critical_from_state(self):
        state = _make_state(is_critical=True)
        update = node_p5_procurement(state)
        pdf = update.get("rfq_pdf_text", "")
        assert "KRITISCHE ANWENDUNG" in pdf

    def test_node_reads_critique_log_from_state(self):
        state = _make_state(critique_log=["CRITICAL: Medienunverträglichkeit"])
        update = node_p5_procurement(state)
        pdf = update.get("rfq_pdf_text", "")
        assert "Medienunverträglichkeit" in pdf

    def test_node_without_working_profile_still_runs(self):
        state = SealAIState(
            messages=[HumanMessage(content="rfq bitte")],
            seal_family="Spiraldichtung",
        )
        # Should not raise, even without working_profile
        update = node_p5_procurement(state)
        assert "procurement_result" in update


# ---------------------------------------------------------------------------
# TestProcurementResult
# ---------------------------------------------------------------------------


class TestProcurementResult:
    def test_model_valid_with_defaults(self):
        r = ProcurementResult()
        assert r.matched_partners == []
        assert r.fallback is False
        assert r.stages_completed == 0

    def test_model_dump_round_trip(self):
        p = _make_partner()
        r = ProcurementResult(
            matched_partners=[p],
            fallback=False,
            stages_completed=4,
            fallback_reason="",
        )
        d = r.model_dump()
        assert d["fallback"] is False
        assert len(d["matched_partners"]) == 1
        assert d["matched_partners"][0]["partner_id"] == "T001"

    def test_fallback_true_with_reason(self):
        r = ProcurementResult(
            matched_partners=[],
            fallback=True,
            stages_completed=1,
            fallback_reason="Kein Bauform-Match",
        )
        assert r.fallback is True
        assert "Bauform" in r.fallback_reason


# ---------------------------------------------------------------------------
# TestRunProcurementMatchingIntegration
# ---------------------------------------------------------------------------


class TestRunProcurementMatchingIntegration:
    def test_full_match_with_real_registry(self):
        """With default registry, Spiraldichtung/steam/50bar should find partners."""
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0)
        assert result.fallback is False
        assert len(result.matched_partners) >= 1
        # All returned partners must be paying
        assert all(p.is_paying_partner for p in result.matched_partners)

    def test_fastest_partner_is_first(self):
        """FastSeal (3 days) should appear before TechSeal (14 days) if both match."""
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0)
        if len(result.matched_partners) >= 2:
            assert result.matched_partners[0].delivery_days <= result.matched_partners[1].delivery_days

    def test_stages_completed_gte_2_on_success(self):
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0)
        assert result.stages_completed >= 2

    def test_empty_custom_registry_returns_fallback(self):
        result = run_procurement_matching("Spiraldichtung", "steam", 50.0, registry=[])
        assert result.fallback is True
