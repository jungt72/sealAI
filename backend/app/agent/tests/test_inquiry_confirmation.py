"""
Tests for inquiry_ready confirmation flow — Phase H1.2

Coverage:
  ✓ admissible=False → response_class downgraded to structured_clarification
  ✓ admissible=False → blocking_reasons written to DecisionState
  ✓ admissible=True  → interrupt() called with correct payload
  ✓ confirmed=True   → response_class stays inquiry_ready
  ✓ confirmed=True   → action_readiness.inquiry_confirmed = True
  ✓ confirmed=False  → response_class downgraded to governed_state_update
  ✓ build_inquiry_summary() contains all required keys
  ✓ interrupt() not available (RuntimeError) → fallback: node returns without crash
  ✓ admissibility check runs BEFORE interrupt() — interrupt never called when not admissible
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.output_contract_node import (
    build_inquiry_summary,
    output_contract_node,
)
from app.agent.state.models import (
    ActionReadinessState,
    AssertedClaim,
    AssertedState,
    DecisionState,
    GovernanceState,
    ManufacturerRef,
    MatchingState,
    NormalizedParameter,
    NormalizedState,
    RequirementClass,
    RfqState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_param(field: str, value, unit: str | None = None) -> NormalizedParameter:
    return NormalizedParameter(field_name=field, value=value, unit=unit, confidence="confirmed")


def _full_normalized() -> NormalizedState:
    return NormalizedState(
        parameters={
            "medium":            _norm_param("medium", "Salzwasser"),
            "temperature_max_c": _norm_param("temperature_max_c", 80.0, "°C"),
            "pressure_max_bar":  _norm_param("pressure_max_bar", 6.0, "bar"),
            "shaft_diameter_mm": _norm_param("shaft_diameter_mm", 50.0, "mm"),
            "sealing_type":      _norm_param("sealing_type", "STS-TYPE-GS-S"),
        },
        parameter_status={
            "medium": "observed",
            "temperature_max_c": "observed",
            "pressure_max_bar": "observed",
            "shaft_diameter_mm": "observed",
            "sealing_type": "observed",
        },
    )


def _full_rfq_state() -> RfqState:
    return RfqState(
        rfq_ready=True,
        status="rfq_ready",
        rfq_admissible=True,
        critical_review_passed=True,
        blocking_findings=[],
        requirement_class=RequirementClass(class_id="RD50-2-1"),
    )


def _inquiry_ready_state() -> GraphState:
    """GraphState that routes to inquiry_ready with all admissibility fields present."""
    return GraphState(
        normalized=_full_normalized(),
        asserted=AssertedState(
            assertions={
                "medium": AssertedClaim(field_name="medium", asserted_value="Salzwasser"),
                "pressure_bar": AssertedClaim(field_name="pressure_bar", asserted_value=6.0),
                "temperature_c": AssertedClaim(field_name="temperature_c", asserted_value=80.0),
            }
        ),
        governance=GovernanceState(gov_class="A", rfq_admissible=True),
        matching=MatchingState(
            status="matched_primary_candidate",
            matchability_status="ready_for_matching",
            shortlist_ready=True,
            inquiry_ready=True,
            selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme GmbH"),
        ),
        rfq=_full_rfq_state(),
    )


def _not_admissible_state() -> GraphState:
    """inquiry_ready routing but missing mandatory fields → admissibility fails."""
    return GraphState(
        # empty normalized → missing all fields
        governance=GovernanceState(gov_class="A", rfq_admissible=True),
        matching=MatchingState(
            status="matched_primary_candidate",
            matchability_status="ready_for_matching",
            shortlist_ready=True,
            inquiry_ready=True,
            selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme GmbH"),
        ),
        rfq=_full_rfq_state(),
    )


# ---------------------------------------------------------------------------
# 1. Not admissible → downgrade to structured_clarification
# ---------------------------------------------------------------------------

class TestNotAdmissibleDowngrade:
    @pytest.mark.asyncio
    async def test_not_admissible_becomes_structured_clarification(self) -> None:
        state = _not_admissible_state()
        # Allow structured_clarification interrupt but stop it from blocking
        with patch(
            "app.agent.graph.nodes.output_contract_node.interrupt",
            side_effect=RuntimeError("interrupt stop"),
        ):
            result = await output_contract_node(state)
        assert result.output_response_class == "structured_clarification"

    @pytest.mark.asyncio
    async def test_not_admissible_blocking_reasons_in_decision_state(self) -> None:
        state = _not_admissible_state()
        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=RuntimeError):
            result = await output_contract_node(state)
        assert len(result.decision.blocking_reasons) > 0

    @pytest.mark.asyncio
    async def test_not_admissible_blocking_reasons_mention_missing_field(self) -> None:
        state = _not_admissible_state()
        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=RuntimeError):
            result = await output_contract_node(state)
        reasons_str = " ".join(result.decision.blocking_reasons)
        # At least one mandatory field must appear
        assert any(f in reasons_str for f in ("medium", "temperature_max_c", "pressure_max_bar",
                                               "shaft_diameter_mm", "sealing_type"))

    @pytest.mark.asyncio
    async def test_inquiry_confirmation_interrupt_never_called_when_not_admissible(self) -> None:
        """The inquiry_confirmation interrupt must not be called when admissibility fails.

        A structured_clarification interrupt may still be called legitimately
        after the downgrade — we only track inquiry_confirmation type payloads.
        """
        state = _not_admissible_state()
        inquiry_interrupts = []

        def _track_interrupt(payload):
            if isinstance(payload, dict) and payload.get("type") == "inquiry_confirmation":
                inquiry_interrupts.append(payload)
            raise RuntimeError("stop interrupt")

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_track_interrupt):
            await output_contract_node(state)
        assert inquiry_interrupts == [], "inquiry_confirmation interrupt must not be called when not admissible"


# ---------------------------------------------------------------------------
# 2. Admissible → interrupt() called with correct payload
# ---------------------------------------------------------------------------

class TestAdmissibleInterruptCalled:
    @pytest.mark.asyncio
    async def test_interrupt_called_with_inquiry_confirmation_type(self) -> None:
        state = _inquiry_ready_state()
        captured = []

        def _fake_interrupt(payload):
            captured.append(payload)
            raise RuntimeError("stop after capture")

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            await output_contract_node(state)

        assert len(captured) >= 1
        inquiry_interrupts = [p for p in captured if isinstance(p, dict) and p.get("type") == "inquiry_confirmation"]
        assert len(inquiry_interrupts) == 1

    @pytest.mark.asyncio
    async def test_interrupt_payload_contains_case_summary(self) -> None:
        state = _inquiry_ready_state()
        captured = []

        def _fake_interrupt(payload):
            captured.append(payload)
            raise RuntimeError

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            await output_contract_node(state)

        inquiry_payload = next(p for p in captured if isinstance(p, dict) and p.get("type") == "inquiry_confirmation")
        assert "case_summary" in inquiry_payload
        assert isinstance(inquiry_payload["case_summary"], dict)

    @pytest.mark.asyncio
    async def test_interrupt_payload_contains_basis_hash(self) -> None:
        state = _inquiry_ready_state()
        captured = []

        def _fake_interrupt(payload):
            captured.append(payload)
            raise RuntimeError

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            await output_contract_node(state)

        inquiry_payload = next(p for p in captured if isinstance(p, dict) and p.get("type") == "inquiry_confirmation")
        assert "basis_hash" in inquiry_payload
        assert isinstance(inquiry_payload["basis_hash"], str)

    @pytest.mark.asyncio
    async def test_interrupt_payload_blocking_reasons_empty_when_admissible(self) -> None:
        state = _inquiry_ready_state()
        captured = []

        def _fake_interrupt(payload):
            captured.append(payload)
            raise RuntimeError

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            await output_contract_node(state)

        inquiry_payload = next(p for p in captured if isinstance(p, dict) and p.get("type") == "inquiry_confirmation")
        assert inquiry_payload["blocking_reasons"] == []


# ---------------------------------------------------------------------------
# 3. confirmed=True → inquiry_ready stays, inquiry_confirmed=True
# ---------------------------------------------------------------------------

class TestConfirmedTrue:
    @pytest.mark.asyncio
    async def test_confirmed_true_keeps_inquiry_ready(self) -> None:
        state = _inquiry_ready_state()
        call_count = [0]

        def _fake_interrupt(payload):
            call_count[0] += 1
            if call_count[0] == 1 and isinstance(payload, dict) and payload.get("type") == "inquiry_confirmation":
                return {"confirmed": True}
            raise RuntimeError("stop")

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            result = await output_contract_node(state)
        assert result.output_response_class == "inquiry_ready"

    @pytest.mark.asyncio
    async def test_confirmed_true_sets_inquiry_confirmed(self) -> None:
        state = _inquiry_ready_state()
        call_count = [0]

        def _fake_interrupt(payload):
            call_count[0] += 1
            if call_count[0] == 1 and isinstance(payload, dict) and payload.get("type") == "inquiry_confirmation":
                return {"confirmed": True}
            raise RuntimeError("stop")

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            result = await output_contract_node(state)
        assert result.action_readiness.inquiry_confirmed is True

    @pytest.mark.asyncio
    async def test_confirmed_true_output_public_response_class_inquiry_ready(self) -> None:
        state = _inquiry_ready_state()
        call_count = [0]

        def _fake_interrupt(payload):
            call_count[0] += 1
            if call_count[0] == 1 and isinstance(payload, dict) and payload.get("type") == "inquiry_confirmation":
                return {"confirmed": True}
            raise RuntimeError("stop")

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            result = await output_contract_node(state)
        assert result.output_public.get("response_class") == "inquiry_ready"


# ---------------------------------------------------------------------------
# 4. confirmed=False → downgrade to governed_state_update
# ---------------------------------------------------------------------------

class TestConfirmedFalse:
    @pytest.mark.asyncio
    async def test_confirmed_false_downgrades_to_governed_state_update(self) -> None:
        state = _inquiry_ready_state()
        call_count = [0]

        def _fake_interrupt(payload):
            call_count[0] += 1
            if call_count[0] == 1 and isinstance(payload, dict) and payload.get("type") == "inquiry_confirmation":
                return {"confirmed": False}
            raise RuntimeError("stop")

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            result = await output_contract_node(state)
        assert result.output_response_class == "governed_state_update"

    @pytest.mark.asyncio
    async def test_confirmed_false_inquiry_confirmed_stays_false(self) -> None:
        state = _inquiry_ready_state()
        call_count = [0]

        def _fake_interrupt(payload):
            call_count[0] += 1
            if call_count[0] == 1 and isinstance(payload, dict) and payload.get("type") == "inquiry_confirmation":
                return {"confirmed": False}
            raise RuntimeError("stop")

        with patch("app.agent.graph.nodes.output_contract_node.interrupt", side_effect=_fake_interrupt):
            result = await output_contract_node(state)
        assert result.action_readiness.inquiry_confirmed is False


# ---------------------------------------------------------------------------
# 5. build_inquiry_summary() — required keys
# ---------------------------------------------------------------------------

class TestBuildInquirySummary:
    def test_returns_all_required_keys(self) -> None:
        state = _inquiry_ready_state()
        summary = build_inquiry_summary(state)
        required_keys = {
            "sealing_type",
            "material_combination",
            "key_parameters",
            "top_manufacturer",
            "open_points_count",
            "pdf_ready",
        }
        assert required_keys.issubset(set(summary.keys()))

    def test_sealing_type_extracted(self) -> None:
        state = _inquiry_ready_state()
        summary = build_inquiry_summary(state)
        assert summary["sealing_type"] == "STS-TYPE-GS-S"

    def test_key_parameters_contains_medium(self) -> None:
        state = _inquiry_ready_state()
        summary = build_inquiry_summary(state)
        assert "medium" in summary["key_parameters"]
        assert summary["key_parameters"]["medium"] == "Salzwasser"

    def test_key_parameters_contains_temperature(self) -> None:
        state = _inquiry_ready_state()
        summary = build_inquiry_summary(state)
        assert "temperature_max_c" in summary["key_parameters"]

    def test_key_parameters_contains_pressure(self) -> None:
        state = _inquiry_ready_state()
        summary = build_inquiry_summary(state)
        assert "pressure_max_bar" in summary["key_parameters"]

    def test_key_parameters_contains_shaft_diameter(self) -> None:
        state = _inquiry_ready_state()
        summary = build_inquiry_summary(state)
        assert "shaft_diameter_mm" in summary["key_parameters"]

    def test_open_points_count_is_int(self) -> None:
        state = _inquiry_ready_state()
        summary = build_inquiry_summary(state)
        assert isinstance(summary["open_points_count"], int)

    def test_pdf_ready_is_bool(self) -> None:
        state = _inquiry_ready_state()
        summary = build_inquiry_summary(state)
        assert isinstance(summary["pdf_ready"], bool)

    def test_top_manufacturer_from_matching(self) -> None:
        state = _inquiry_ready_state().model_copy(update={
            "matching": MatchingState(
                status="matched_primary_candidate",
                selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme GmbH"),
            )
        })
        summary = build_inquiry_summary(state)
        assert summary["top_manufacturer"] is not None
        assert summary["top_manufacturer"]["name"] == "Acme GmbH"

    def test_empty_state_no_crash(self) -> None:
        state = GraphState()
        summary = build_inquiry_summary(state)
        assert "sealing_type" in summary
        assert "key_parameters" in summary


# ---------------------------------------------------------------------------
# 6. interrupt() not available → no crash
# ---------------------------------------------------------------------------

class TestInterruptNotAvailable:
    @pytest.mark.asyncio
    async def test_runtime_error_on_interrupt_does_not_crash(self) -> None:
        state = _inquiry_ready_state()
        with patch(
            "app.agent.graph.nodes.output_contract_node.interrupt",
            side_effect=RuntimeError("no checkpointer"),
        ):
            # Should return without raising
            result = await output_contract_node(state)
        assert result is not None
        assert isinstance(result.output_response_class, str)
