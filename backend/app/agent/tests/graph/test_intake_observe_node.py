"""
Tests for graph/nodes/intake_observe_node.py — Phase F-C.1

Key invariant under test:
    LLM writes ONLY into ObservedState. NormalizedState, AssertedState,
    and GovernanceState must remain at their defaults after this node runs,
    regardless of what the LLM or regex extraction returns.

Coverage:
    1. Numeric patterns → ObservedExtractions created (regex pass)
    2. Material/medium tokens → ObservedExtractions (regex pass)
    3. LLM mock → extractions appear in ObservedState
    4. LLM adds only fields NOT already covered by regex
    5. NormalizedState untouched after node
    6. AssertedState untouched after node
    7. GovernanceState untouched after node
    8. Empty pending_message → state unchanged
    9. LLM disabled → regex-only extractions
    10. LLM error → graceful fallback (regex results preserved)
    11. LLM unknown field_name → silently discarded
    12. Turn index propagated correctly
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.intake_observe_node import (
    _apply_contextual_regex_fallbacks,
    _ALLOWED_FIELD_NAMES,
    _regex_params_to_extractions,
    intake_observe_node,
)
from app.agent.state.models import (
    AssertedState,
    ObservedExtraction,
    ObservedState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_state(**kwargs) -> GraphState:
    """Return a GraphState with all layers at defaults + optional overrides."""
    return GraphState(**kwargs)


def _make_llm_response(items: list[dict]) -> MagicMock:
    """Build a minimal mock that looks like an openai streaming response."""
    import json
    content = json.dumps(items)
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# 1. Regex pass — numeric patterns
# ---------------------------------------------------------------------------

class TestRegexExtraction:
    @pytest.mark.asyncio
    async def test_temperature_extracted(self):
        state = _fresh_state(pending_message="PTFE-Dichtung bei 180°C")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        names = {e.field_name for e in result.observed.raw_extractions}
        assert "temperature_c" in names

    @pytest.mark.asyncio
    async def test_temperature_value_correct(self):
        state = _fresh_state(pending_message="Betrieb bei 180°C")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        temp = next(e for e in result.observed.raw_extractions if e.field_name == "temperature_c")
        assert float(temp.raw_value) == pytest.approx(180.0)

    @pytest.mark.asyncio
    async def test_contextual_rotary_turn_maps_bare_40mm_to_shaft_diameter(self):
        state = _fresh_state(
            pending_message="40mm",
            motion_hint={"label": "rotary", "confidence": "high"},
            application_hint={"label": "shaft_sealing", "confidence": "medium"},
        )
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        diameter = next(e for e in result.observed.raw_extractions if e.field_name == "shaft_diameter_mm")
        assert float(diameter.raw_value) == pytest.approx(40.0)

    @pytest.mark.asyncio
    async def test_pressure_extracted(self):
        state = _fresh_state(pending_message="Betriebsdruck 12 bar")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        names = {e.field_name for e in result.observed.raw_extractions}
        assert "pressure_bar" in names

    @pytest.mark.asyncio
    async def test_speed_extracted(self):
        state = _fresh_state(pending_message="Drehzahl 1500 rpm")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        names = {e.field_name for e in result.observed.raw_extractions}
        assert "speed_rpm" in names

    @pytest.mark.asyncio
    async def test_multiple_params_extracted(self):
        state = _fresh_state(pending_message="PTFE-Dichtung für 180°C Dampf bei 12 bar")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        names = {e.field_name for e in result.observed.raw_extractions}
        # temperature and pressure are in the message
        assert "temperature_c" in names
        assert "pressure_bar" in names

    @pytest.mark.asyncio
    async def test_extended_need_analysis_fields_extracted(self):
        state = _fresh_state(
            pending_message=(
                "Gleitringdichtung fuer chemische Pumpe, 10 bar, 90°C, "
                "Betrieb 24/7, Druck von innen nach aussen, Salzsaeure 10%, "
                "etwas Schmutz, FDA."
            )
        )
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        values = {e.field_name: e.raw_value for e in result.observed.raw_extractions}

        assert values["sealing_type"] == "mechanical_seal"
        assert values["duty_profile"] == "continuous"
        assert values["pressure_direction"] == "inside_out"
        assert values["installation"] == "pump"
        assert values["contamination"] == "solids_or_particles"
        assert "food_contact" in values["compliance"]
        assert "concentration_context" in values["medium_qualifiers"]


# ---------------------------------------------------------------------------
# 2. Regex pass — material / medium tokens
# ---------------------------------------------------------------------------

class TestRegexMaterialMedium:
    @pytest.mark.asyncio
    async def test_ptfe_material_extracted(self):
        state = _fresh_state(pending_message="PTFE-Dichtung für Hochtemperaturanwendung")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        names = {e.field_name for e in result.observed.raw_extractions}
        assert "material" in names

    @pytest.mark.asyncio
    async def test_fkm_material_extracted(self):
        state = _fresh_state(pending_message="FKM-Dichtring gesucht")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        names = {e.field_name for e in result.observed.raw_extractions}
        assert "material" in names

    @pytest.mark.asyncio
    async def test_wasser_medium_extracted(self):
        state = _fresh_state(pending_message="Dichtung für Wasser, 5 bar")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        names = {e.field_name for e in result.observed.raw_extractions}
        assert "medium" in names


# ---------------------------------------------------------------------------
# 3. Invariant: LLM writes ONLY to ObservedState
# ---------------------------------------------------------------------------

class TestArchitectureInvariant:
    @pytest.mark.asyncio
    async def test_normalized_state_unchanged(self):
        """After intake_observe_node, NormalizedState must be the default (empty)."""
        state = _fresh_state(pending_message="PTFE-Dichtung bei 180°C")

        mock_resp = _make_llm_response([
            {"field_name": "temperature_c", "raw_value": 180, "raw_unit": "°C", "confidence": 0.95}
        ])
        with patch(
            "app.agent.graph.nodes.intake_observe_node.openai"
        ) as mock_openai:
            mock_openai.AsyncOpenAI.return_value.chat.completions.create = AsyncMock(
                return_value=mock_resp
            )
            result = await intake_observe_node(state)

        # NormalizedState was not touched by this node — must still be empty
        assert result.normalized.parameters == {}
        assert result.normalized.conflicts == []
        assert result.normalized.assumptions == []

    @pytest.mark.asyncio
    async def test_asserted_state_unchanged(self):
        """After intake_observe_node, AssertedState must be the default."""
        state = _fresh_state(pending_message="12 bar Hydrauliköl")
        default_asserted = AssertedState()

        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)

        assert result.asserted == default_asserted
        assert result.asserted.assertions == {}
        assert result.asserted.blocking_unknowns == []

    @pytest.mark.asyncio
    async def test_governance_state_unchanged(self):
        """After intake_observe_node, GovernanceState must be the default (no class set)."""
        state = _fresh_state(pending_message="FKM, 15 bar, 120°C, Wasser")

        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)

        # GovernanceState was not touched — no class assigned yet, not rfq_admissible
        assert result.governance.gov_class is None
        assert result.governance.rfq_admissible is False
        assert result.governance.validity_limits == []
        assert result.governance.open_validation_points == []

    @pytest.mark.asyncio
    async def test_observed_state_has_extractions(self):
        """ObservedState must have extractions after the node runs."""
        state = _fresh_state(pending_message="NBR, 8 bar, 80°C")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        assert len(result.observed.raw_extractions) > 0

    @pytest.mark.asyncio
    async def test_extraction_source_is_llm(self):
        """All extractions produced by this node must have source='llm'."""
        state = _fresh_state(pending_message="FKM, 10 bar, 100°C")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        for e in result.observed.raw_extractions:
            assert e.source == "llm", f"Expected source='llm', got '{e.source}' for {e.field_name}"


# ---------------------------------------------------------------------------
# 4. LLM mock — extractions appear in ObservedState
# ---------------------------------------------------------------------------

class TestLLMExtractionMock:
    @pytest.mark.asyncio
    async def test_llm_extraction_lands_in_observed(self):
        """LLM extraction result must appear in ObservedState.raw_extractions."""
        state = _fresh_state(pending_message="Das Medium ist Dampf")

        mock_resp = _make_llm_response([
            {"field_name": "medium", "raw_value": "Dampf", "raw_unit": None, "confidence": 0.80}
        ])
        with patch(
            "app.agent.graph.nodes.intake_observe_node.openai"
        ) as mock_openai:
            mock_openai.AsyncOpenAI.return_value.chat.completions.create = AsyncMock(
                return_value=mock_resp
            )
            result = await intake_observe_node(state)

        names = {e.field_name for e in result.observed.raw_extractions}
        assert "medium" in names

    @pytest.mark.asyncio
    async def test_llm_does_not_duplicate_regex_fields(self):
        """LLM must not add extractions for fields already covered by regex."""
        # 180°C is caught by regex — LLM also returns temperature_c
        state = _fresh_state(pending_message="Betrieb bei 180°C")

        mock_resp = _make_llm_response([
            {"field_name": "temperature_c", "raw_value": 180, "raw_unit": "°C", "confidence": 0.95}
        ])
        with patch(
            "app.agent.graph.nodes.intake_observe_node.openai"
        ) as mock_openai:
            mock_openai.AsyncOpenAI.return_value.chat.completions.create = AsyncMock(
                return_value=mock_resp
            )
            result = await intake_observe_node(state)

        # Should appear exactly once (from regex, not duplicated by LLM)
        temp_extractions = [e for e in result.observed.raw_extractions if e.field_name == "temperature_c"]
        assert len(temp_extractions) == 1

    @pytest.mark.asyncio
    async def test_llm_unknown_field_discarded(self):
        """LLM proposing a field_name not in _ALLOWED_FIELD_NAMES must be silently dropped."""
        state = _fresh_state(pending_message="Gummiabdichtung")

        mock_resp = _make_llm_response([
            {"field_name": "manufacturer", "raw_value": "Acme", "confidence": 0.9},
            {"field_name": "material",     "raw_value": "NBR",  "confidence": 0.85},
        ])
        with patch(
            "app.agent.graph.nodes.intake_observe_node.openai"
        ) as mock_openai:
            mock_openai.AsyncOpenAI.return_value.chat.completions.create = AsyncMock(
                return_value=mock_resp
            )
            result = await intake_observe_node(state)

        names = {e.field_name for e in result.observed.raw_extractions}
        assert "manufacturer" not in names   # rejected
        assert "material" in names           # accepted


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_message_returns_unchanged_state(self):
        state = _fresh_state(pending_message="")
        result = await intake_observe_node(state)
        assert result is state

    @pytest.mark.asyncio
    async def test_no_params_in_message_observed_unchanged(self):
        """A message with no extractable params leaves ObservedState empty."""
        state = _fresh_state(pending_message="Guten Morgen, wie kann ich helfen?")
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        assert result.observed.raw_extractions == []

    @pytest.mark.asyncio
    async def test_llm_error_falls_back_to_regex(self):
        """LLM connection error must not suppress regex extractions."""
        state = _fresh_state(pending_message="PTFE bei 180°C")

        with patch(
            "app.agent.graph.nodes.intake_observe_node.openai"
        ) as mock_openai:
            mock_openai.AsyncOpenAI.return_value.chat.completions.create = AsyncMock(
                side_effect=ConnectionError("network down")
            )
            result = await intake_observe_node(state)

        names = {e.field_name for e in result.observed.raw_extractions}
        # Regex should still have caught temperature from "180°C"
        assert "temperature_c" in names

    @pytest.mark.asyncio
    async def test_turn_index_assigned_from_analysis_cycle(self):
        """turn_index falls back to analysis_cycle when user_turn_index is 0."""
        state = _fresh_state(pending_message="12 bar", analysis_cycle=3, user_turn_index=0)
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        # user_turn_index=0 → falsy → falls back to analysis_cycle=3
        for e in result.observed.raw_extractions:
            assert e.turn_index == 3

    @pytest.mark.asyncio
    async def test_user_turn_index_takes_priority_over_analysis_cycle(self):
        """user_turn_index must be used as turn_index when non-zero."""
        state = _fresh_state(pending_message="12 bar", analysis_cycle=0, user_turn_index=5)
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)
        for e in result.observed.raw_extractions:
            assert e.turn_index == 5

    @pytest.mark.asyncio
    async def test_newer_turn_overrides_older_extraction_in_reducer(self):
        """Reducer must pick the extraction with higher turn_index for same field."""
        from app.agent.state.models import ObservedState, ObservedExtraction
        from app.agent.state.reducers import reduce_observed_to_normalized

        old = ObservedExtraction(field_name="temperature_c", raw_value=80.0, raw_unit="°C",
                                 source="llm", confidence=0.92, turn_index=0)
        new = ObservedExtraction(field_name="temperature_c", raw_value=90.0, raw_unit="°C",
                                 source="llm", confidence=0.92, turn_index=1)
        observed = ObservedState(raw_extractions=[old, new])
        normalized = reduce_observed_to_normalized(observed)
        assert normalized.parameters["temperature_c"].value == 90.0

    @pytest.mark.asyncio
    async def test_llm_disabled_only_regex_runs(self):
        """With LLM disabled, only regex extractions are present."""
        state = _fresh_state(pending_message="Das Medium ist Dampf, 12 bar")

        called = []

        async def _mock_create(**kwargs):
            called.append(True)
            return _make_llm_response([])

        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            with patch(
                "app.agent.graph.nodes.intake_observe_node.openai"
            ) as mock_openai:
                mock_openai.AsyncOpenAI.return_value.chat.completions.create = _mock_create
                await intake_observe_node(state)

        assert called == [], "LLM must not be called when feature flag is off"

    @pytest.mark.asyncio
    async def test_existing_extractions_preserved(self):
        """Pre-existing extractions in ObservedState must not be dropped."""
        from app.agent.state.models import ObservedExtraction
        prior = ObservedExtraction(
            field_name="medium", raw_value="Wasser", source="user", confidence=1.0, turn_index=0
        )
        initial_observed = ObservedState().with_extraction(prior)
        state = _fresh_state(
            observed=initial_observed,
            pending_message="12 bar, 60°C",
        )
        with patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", False):
            result = await intake_observe_node(state)

        # Prior extraction must still be there
        assert any(e.field_name == "medium" and e.raw_value == "Wasser"
                   for e in result.observed.raw_extractions)

    @pytest.mark.asyncio
    async def test_primary_medium_correction_promotes_user_override(self):
        state = _fresh_state(
            pending_message="Korrektur: nicht Oel, sondern Wasser mit Reinigeranteil.",
            normalized={
                "parameters": {
                    "medium": {
                        "field_name": "medium",
                        "value": "Oel",
                        "confidence": "confirmed",
                        "source": "llm",
                    }
                }
            },
            asserted={
                "assertions": {
                    "medium": {
                        "field_name": "medium",
                        "asserted_value": "Oel",
                        "confidence": "confirmed",
                    }
                }
            },
            analysis_cycle=2,
        )

        with (
            patch("app.agent.graph.nodes.intake_observe_node._ENABLE_LLM_EXTRACTION", True),
            patch(
                "app.agent.graph.nodes.intake_observe_node._llm_extract_params",
                AsyncMock(
                    return_value=[
                        ObservedExtraction(
                            field_name="medium",
                            raw_value="Wasser mit Reinigeranteil",
                            source="llm",
                            confidence=0.8,
                            turn_index=2,
                        )
                    ]
                ),
            ),
        ):
            result = await intake_observe_node(state)

        assert result.observed.user_overrides
        override = result.observed.user_overrides[-1]
        assert override.field_name == "medium"
        assert override.override_value == "Wasser mit Reinigeranteil"
        assert override.turn_index == 2


# ---------------------------------------------------------------------------
# 6. _regex_params_to_extractions unit tests (pure function)
# ---------------------------------------------------------------------------

class TestRegexParamsToExtractions:
    def test_temperature_mapped(self):
        exts = _regex_params_to_extractions({"temperature_c": 100.0}, turn_index=0)
        assert any(e.field_name == "temperature_c" and float(e.raw_value) == 100.0 for e in exts)

    def test_pressure_mapped(self):
        exts = _regex_params_to_extractions({"pressure_bar": 8.0}, turn_index=0)
        assert any(e.field_name == "pressure_bar" for e in exts)

    def test_diameter_maps_to_shaft_diameter_mm(self):
        exts = _regex_params_to_extractions({"diameter_mm": 50.0}, turn_index=0)
        assert any(e.field_name == "shaft_diameter_mm" for e in exts)

    def test_none_value_skipped(self):
        exts = _regex_params_to_extractions({"temperature_c": None}, turn_index=0)
        assert exts == []

    def test_medium_normalized_preferred_over_confirmation(self):
        exts = _regex_params_to_extractions(
            {"medium_normalized": "Wasser", "medium_confirmation_required": "Dampf"},
            turn_index=0,
        )
        medium_exts = [e for e in exts if e.field_name == "medium"]
        assert len(medium_exts) == 1
        assert medium_exts[0].raw_value == "Wasser"

    def test_confidence_less_for_confirmation_required(self):
        exts_norm = _regex_params_to_extractions({"medium_normalized": "Wasser"}, turn_index=0)
        exts_conf = _regex_params_to_extractions({"medium_confirmation_required": "Dampf"}, turn_index=0)
        c_norm = next(e.confidence for e in exts_norm if e.field_name == "medium")
        c_conf = next(e.confidence for e in exts_conf if e.field_name == "medium")
        assert c_norm > c_conf

    def test_medium_status_controls_regex_bridge_confidence(self):
        confirmed = _regex_params_to_extractions(
            {"medium_normalized": "Wasser", "medium_normalization_status": "confirmed"},
            turn_index=0,
        )
        inferred = _regex_params_to_extractions(
            {"medium_normalized": "Spezialkraftstoff", "medium_normalization_status": "inferred"},
            turn_index=0,
        )
        c_confirmed = next(e.confidence for e in confirmed if e.field_name == "medium")
        c_inferred = next(e.confidence for e in inferred if e.field_name == "medium")
        assert c_confirmed == 0.92
        assert c_inferred == 0.60

    def test_contextual_fallback_maps_bare_mm_to_shaft_diameter_when_rotary_hint_exists(self):
        state = _fresh_state(
            pending_message="40 mm",
            motion_hint={"label": "rotary", "confidence": "high"},
        )
        params = _apply_contextual_regex_fallbacks(state, {})
        assert params["diameter_mm"] == 40.0


# ---------------------------------------------------------------------------
# 7. _ALLOWED_FIELD_NAMES whitelist
# ---------------------------------------------------------------------------

class TestAllowedFieldNames:
    def test_expected_fields_present(self):
        expected = {"medium", "pressure_bar", "temperature_c", "material", "shaft_diameter_mm", "speed_rpm"}
        assert expected <= _ALLOWED_FIELD_NAMES

    def test_governance_fields_not_allowed(self):
        """Governance fields must never be in the allowed extraction set."""
        forbidden = {"gov_class", "rfq_admissible", "requirement_class", "manufacturer"}
        assert forbidden.isdisjoint(_ALLOWED_FIELD_NAMES)
