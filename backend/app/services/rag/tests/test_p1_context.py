"""Tests for P1 Context Node (SEALAI v4.4.0 Sprint 4).

All tests are offline — no real LLM calls.
The merge/fallback logic is tested directly; LLM extraction is mocked.
"""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from app._legacy_v2.state import SealAIState
from app.services.rag.nodes.p1_context import (
    _P1Extraction,
    _merge_extraction_into_profile,
    node_p1_context,
)
from app.services.rag.state import WorkingProfile


# ---------------------------------------------------------------------------
# Unit tests: _merge_extraction_into_profile
# ---------------------------------------------------------------------------


class TestMergeExtraction:
    def test_new_case_creates_fresh_profile(self):
        extraction = _P1Extraction(medium="steam", pressure_max_bar=40.0)
        profile = _merge_extraction_into_profile(None, extraction)
        assert profile.medium == "steam"
        assert profile.pressure_max_bar == 40.0
        assert profile.temperature_max_c is None

    def test_follow_up_merges_onto_existing(self):
        existing = WorkingProfile(medium="water", pressure_max_bar=20.0, temperature_max_c=80.0)
        extraction = _P1Extraction(pressure_max_bar=40.0, flange_dn=100)
        profile = _merge_extraction_into_profile(existing, extraction)
        # Existing fields preserved
        assert profile.medium == "water"
        assert profile.temperature_max_c == 80.0
        # New fields merged in
        assert profile.pressure_max_bar == 40.0
        assert profile.flange_dn == 100

    def test_follow_up_overrides_only_non_none(self):
        existing = WorkingProfile(medium="oil", pressure_max_bar=50.0)
        extraction = _P1Extraction(medium="H2SO4")  # only medium changes
        profile = _merge_extraction_into_profile(existing, extraction)
        assert profile.medium == "H2SO4"
        assert profile.pressure_max_bar == 50.0  # preserved

    def test_empty_extraction_preserves_existing(self):
        existing = WorkingProfile(medium="gas", temperature_max_c=300.0)
        extraction = _P1Extraction()  # all None
        profile = _merge_extraction_into_profile(existing, extraction)
        assert profile.medium == "gas"
        assert profile.temperature_max_c == 300.0

    def test_new_case_with_no_extraction_gives_empty_profile(self):
        extraction = _P1Extraction()
        profile = _merge_extraction_into_profile(None, extraction)
        assert isinstance(profile, WorkingProfile)
        assert profile.medium is None
        assert profile.coverage_ratio() == 0.0

    def test_cyclic_load_extracted(self):
        extraction = _P1Extraction(cyclic_load=True)
        profile = _merge_extraction_into_profile(None, extraction)
        assert profile.cyclic_load is True

    def test_all_flange_fields_extracted(self):
        extraction = _P1Extraction(
            flange_standard="ASME B16.5",
            flange_dn=200,
            flange_pn=None,
            flange_class=300,
        )
        profile = _merge_extraction_into_profile(None, extraction)
        assert profile.flange_standard == "ASME B16.5"
        assert profile.flange_dn == 200
        assert profile.flange_class == 300

    def test_invalid_merge_falls_back_gracefully(self):
        """If merging produces invalid state (min > max), fall back without crash."""
        existing = WorkingProfile(pressure_min_bar=5.0, pressure_max_bar=50.0)
        # Extraction sets max below existing min — would violate min ≤ max
        extraction = _P1Extraction(pressure_max_bar=1.0)
        # Should not raise; returns a safe profile
        profile = _merge_extraction_into_profile(existing, extraction)
        assert isinstance(profile, WorkingProfile)

    def test_follow_up_does_not_overwrite_shaft_material_with_seal_material_token(self):
        existing = WorkingProfile(material="1.4404")
        extraction = _P1Extraction(material="PTFE")
        profile = _merge_extraction_into_profile(existing, extraction)
        assert profile.material == "1.4404"


# ---------------------------------------------------------------------------
# Integration tests: node_p1_context with mocked LLM
# ---------------------------------------------------------------------------


def _make_mock_extraction(**kwargs):
    """Return a mock that when called returns a _P1Extraction with given fields."""
    extraction = _P1Extraction(**kwargs)

    class _FakeLLM:
        def with_structured_output(self, *a, **kw):
            return self

        def invoke(self, messages):
            return extraction

    return _FakeLLM()


class TestNodeP1Context:
    def _state(self, text: str, **kwargs) -> SealAIState:
        return SealAIState(
            messages=[HumanMessage(content=text)],
            **kwargs,
        )

    def test_new_case_extracts_and_sets_working_profile(self):
        state = self._state(
            "DN100 PN40 Dampf 180°C 16 bar",
            router_classification="new_case",
        )
        extracted = _P1Extraction(
            medium="Dampf",
            pressure_max_bar=16.0,
            temperature_max_c=180.0,
            flange_dn=100,
            flange_pn=40,
        )
        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            return_value=_make_mock_extraction(
                medium="Dampf",
                pressure_max_bar=16.0,
                temperature_max_c=180.0,
                flange_dn=100,
                flange_pn=40,
            ),
        ):
            command = node_p1_context(state)

        result = command.update
        pillar = result["working_profile"]
        wp = pillar["engineering_profile"]
        assert isinstance(wp, WorkingProfile)
        assert wp.medium is None
        assert wp.pressure_max_bar is None
        assert wp.temperature_max_c is None
        assert wp.flange_dn is None
        assert pillar["extracted_params"]["medium"] == "Dampf"
        assert pillar["extracted_params"]["pressure_max_bar"] == 16.0
        assert pillar["extracted_params"]["temperature_max_c"] == 180.0
        assert pillar["extracted_params"]["flange_dn"] == 100
        assert result["reasoning"]["extracted_parameter_provenance"]["pressure_max_bar"] == "p1_context_extracted"
        assert result["reasoning"]["extracted_parameter_identity"]["medium"]["identity_class"] == "confirmed"
        assert result["reasoning"]["last_node"] == "node_p1_context"

    def test_new_case_extracts_material_and_product(self):
        state = self._state(
            "Was ist Kyrolon?",
            router_classification="new_case",
        )
        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            return_value=_make_mock_extraction(
                material="Kyrolon",
            ),
        ):
            command = node_p1_context(state)

        result = command.update
        wp = result["working_profile"]["engineering_profile"]
        assert wp.material is None
        assert result["working_profile"]["extracted_params"]["material"] == "Kyrolon"
        assert result["reasoning"]["extracted_parameter_identity"]["material"]["identity_class"] == "probable"

    def test_seal_material_is_stored_separately_and_shaft_material_is_protected(self):
        existing = WorkingProfile(material="Edelstahl")
        state = self._state(
            "Option A bitte, wir nehmen PTFE",
            router_classification="follow_up",
            working_profile=existing,
        )
        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            return_value=_make_mock_extraction(material="PTFE", seal_material="PTFE"),
        ):
            command = node_p1_context(state)

        result = command.update
        assert "engineering_profile" not in result["working_profile"]
        assert result["working_profile"]["extracted_params"].get("seal_material") == "PTFE"

    def test_follow_up_merges_onto_existing_profile(self):
        existing = WorkingProfile(medium="water", pressure_max_bar=20.0)
        state = self._state(
            "Ändere Druck auf 40 bar",
            router_classification="follow_up",
            working_profile=existing,
        )
        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            return_value=_make_mock_extraction(pressure_max_bar=40.0),
        ):
            command = node_p1_context(state)

        result = command.update
        assert "engineering_profile" not in result["working_profile"]
        assert result["working_profile"]["extracted_params"]["pressure_max_bar"] == 40.0

    def test_llm_failure_new_case_resets_existing_profile(self):
        existing = WorkingProfile(medium="H2", pressure_max_bar=200.0)
        state = self._state(
            "Neue Anfrage",
            router_classification="new_case",
            working_profile=existing,
        )
        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            command = node_p1_context(state)

        result = command.update
        wp = result["working_profile"]["engineering_profile"]
        assert isinstance(wp, WorkingProfile)
        assert wp.medium is None
        assert wp.pressure_max_bar is None
        assert "error" in result["system"]

    def test_llm_failure_with_no_prior_profile_returns_empty(self):
        state = self._state("Hallo", router_classification="new_case")
        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            side_effect=RuntimeError("LLM unavailable"),
        ):
            command = node_p1_context(state)

        result = command.update
        wp = result["working_profile"]["engineering_profile"]
        assert isinstance(wp, WorkingProfile)
        assert wp.medium is None
        assert "error" in result["system"]

    def test_phase_set_correctly(self):
        state = self._state("test", router_classification="new_case")
        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            return_value=_make_mock_extraction(),
        ):
            command = node_p1_context(state)
        result = command.update
        assert result["reasoning"]["phase"] == "frontdoor"

    def test_new_case_does_not_use_existing_profile(self):
        """new_case must always start fresh, ignoring existing working_profile."""
        existing = WorkingProfile(medium="oil", pressure_max_bar=50.0)
        state = self._state(
            "Neue Anfrage: Dampf 8 bar",
            router_classification="new_case",
            working_profile=existing,
        )
        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            return_value=_make_mock_extraction(medium="Dampf", pressure_max_bar=8.0),
        ):
            command = node_p1_context(state)

        result = command.update
        wp = result["working_profile"]["engineering_profile"]
        # old medium/pressure must be gone (fresh extraction)
        assert wp.medium is None
        assert wp.pressure_max_bar is None
        assert result["working_profile"]["extracted_params"]["medium"] == "Dampf"
        assert result["working_profile"]["extracted_params"]["pressure_max_bar"] == 8.0

    def test_resume_option_acceptance_applies_hrc_override_from_assistant_option(self):
        state = SealAIState(
            messages=[
                AIMessage(
                    content=(
                        "Die aktuelle Loesung hat einen Haerte-Blocker.\n"
                        "Option A: Welle auf 58 HRC haerten und PTFE-Loesung beibehalten.\n"
                        "Option B: Auf Gleitringdichtung wechseln."
                    )
                ),
                HumanMessage(content="Wir nehmen Option A."),
            ],
            router_classification="resume",
            qgate_has_blockers=True,
            extracted_params={"hrc_value": 40.0, "hrc": 40.0},
        )

        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            return_value=_make_mock_extraction(),
        ):
            command = node_p1_context(state)

        result = command.update
        assert result["working_profile"]["extracted_params"]["hrc_value"] == 58.0
        assert result["working_profile"]["extracted_params"]["hrc"] == 58.0

    def test_non_resume_option_a_does_not_force_hrc_override(self):
        state = SealAIState(
            messages=[
                AIMessage(content="Option A: Welle auf 58 HRC haerten."),
                HumanMessage(content="Option A."),
            ],
            router_classification="new_case",
            qgate_has_blockers=False,
            extracted_params={"hrc_value": 40.0, "hrc": 40.0},
        )

        with patch(
            "app.services.rag.nodes.p1_context.ChatOpenAI",
            return_value=_make_mock_extraction(),
        ):
            command = node_p1_context(state)

        result = command.update
        assert result["working_profile"]["extracted_params"] == {}
