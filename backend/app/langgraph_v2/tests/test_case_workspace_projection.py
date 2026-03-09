# backend/app/langgraph_v2/tests/test_case_workspace_projection.py
"""Tests for the Case Workspace Projection (v1.3 Patch A1).

Covers:
1. Projection contains all core sections consistently
2. Canonical governance values are correctly projected
3. Stale / RFQ / release / completeness states appear correctly
4. Candidate / conflict / claim summaries are UI-tauglich aggregated
5. Empty / minimal state does not crash (graceful defaults)
"""
from __future__ import annotations

import pytest

from app.api.v1.schemas.case_workspace import CaseWorkspaceProjection
from app.langgraph_v2.projections.case_workspace import project_case_workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_state() -> dict:
    """Absolutely minimal valid state — empty pillars."""
    return {
        "conversation": {},
        "working_profile": {},
        "reasoning": {},
        "system": {},
    }


def _rich_state() -> dict:
    """Realistic mid-case state with populated governance, candidates, etc."""
    return {
        "conversation": {
            "thread_id": "t-abc-123",
            "user_id": "u-keycloak-42",
            "intent": {"goal": "design_recommendation", "confidence": 0.9},
            "application_category": "hydraulic_cylinder",
            "seal_family": "O-Ring",
            "motion_type": "dynamic_reciprocating",
            "user_persona": "erfahrener",
        },
        "working_profile": {
            "medium": "HLP 46",
            "pressure_bar": 250.0,
            "temperature_c": 80.0,
            "shaft_diameter": 50.0,
            "speed_rpm": None,
            "analysis_complete": False,
            "recommendation": {
                "seal_family": "O-Ring",
                "material": "FKM",
                "summary": "FKM O-Ring recommended",
                "rationale": "Good chemical resistance",
            },
            "live_calc_tile": {
                "v_surface_m_s": 2.5,
                "status": "warning",
                "pv_warning": True,
            },
        },
        "reasoning": {
            "phase": "gap_detection",
            "turn_count": 4,
            "max_turns": 12,
            "coverage_score": 0.65,
            "coverage_gaps": ["speed_rpm", "housing_bore"],
            "completeness_depth": "prequalification",
            "discovery_missing": ["speed_rpm"],
            "recommendation_ready": False,
            "current_assertion_cycle_id": 2,
            "state_revision": 7,
            "asserted_profile_revision": 3,
            "derived_artifacts_stale": False,
            "claims": [
                {"value": "FKM OK", "claim_type": "evidence_based_assertion", "claim_origin": "evidence"},
                {"value": "HLP compat", "claim_type": "deterministic_fact", "claim_origin": "deterministic"},
            ],
            "open_questions": [
                {
                    "id": "q1",
                    "question": "Welche Drehzahl?",
                    "reason": "Fuer PV-Berechnung",
                    "priority": "high",
                    "status": "open",
                    "category": "release_blocking_technical_unknown",
                },
                {
                    "id": "q2",
                    "question": "Gehaeusebohrung?",
                    "reason": "Fuer Passungsberechnung",
                    "priority": "medium",
                    "status": "answered",
                    "category": "clarification_gap",
                },
            ],
            "rfq_ready": False,
        },
        "system": {
            "rfq_admissibility": {
                "status": "provisional",
                "release_status": "precheck_only",
                "blockers": ["speed_rpm missing"],
                "open_points": ["housing_bore"],
            },
            "rfq_confirmed": False,
            "governance_metadata": {
                "scope_of_validity": ["hydraulic_cylinder", "dynamic_reciprocating"],
                "assumptions_active": ["standard_surface_finish"],
                "unknowns_release_blocking": ["speed_rpm"],
                "gate_failures": [],
            },
            "answer_contract": {
                "contract_id": "contract-c2-r3",
                "release_status": "precheck_only",
                "obsolete": False,
                "candidate_clusters": {
                    "plausibly_viable": [
                        {"kind": "material", "value": "FKM", "specificity": "family_only"},
                    ],
                    "viable_only_with_manufacturer_validation": [
                        {"kind": "material", "value": "HNBR", "specificity": "compound_required"},
                    ],
                    "inadmissible_or_excluded": [
                        {"kind": "material", "value": "NBR", "excluded_by_gate": "chemical_resistance"},
                    ],
                },
                "claims": [
                    {"value": "FKM OK", "claim_type": "evidence_based_assertion", "claim_origin": "evidence"},
                    {"value": "HLP compat", "claim_type": "deterministic_fact", "claim_origin": "deterministic"},
                    {"value": "NBR excluded", "claim_type": "deterministic_fact", "claim_origin": "deterministic"},
                ],
                "governance_metadata": {
                    "scope_of_validity": ["hydraulic_cylinder"],
                    "assumptions_active": ["standard_surface_finish"],
                    "unknowns_release_blocking": ["speed_rpm"],
                },
                "required_disclaimers": ["Precheck only — no manufacturer validation"],
                "requirement_spec": {
                    "missing_critical_parameters": ["speed_rpm"],
                },
            },
            "verification_report": {
                "contract_hash": "abc123",
                "draft_hash": "def456",
                "status": "pass",
                "conflicts": [
                    {
                        "conflict_type": "PARAMETER_CONFLICT",
                        "severity": "HARD",
                        "summary": "Pressure exceeds FKM limit",
                        "resolution_status": "OPEN",
                    },
                    {
                        "conflict_type": "SCOPE_CONFLICT",
                        "severity": "SOFT",
                        "summary": "Temperature range approximate",
                        "resolution_status": "RESOLVED",
                    },
                ],
            },
            "verification_passed": True,
            "sealing_requirement_spec": {
                "material_specificity_required": "compound_required",
            },
            "rfq_draft": {
                "rfq_id": "rfq-001",
                "manufacturer_questions_mandatory": [
                    "Compound-spezifische Freigabe fuer HLP 46?",
                    "AED-Variante verfuegbar?",
                ],
            },
        },
    }


# ---------------------------------------------------------------------------
# Test 1: Core sections present and consistent
# ---------------------------------------------------------------------------

class TestCoreProjectionStructure:
    def test_minimal_state_returns_valid_projection(self):
        result = project_case_workspace(_minimal_state())
        assert isinstance(result, CaseWorkspaceProjection)
        # All sections present with defaults
        assert result.case_summary.turn_count == 0
        assert result.completeness.coverage_score == 0.0
        assert result.governance_status.release_status == "inadmissible"
        assert result.rfq_status.admissibility_status == "inadmissible"
        assert result.artifact_status.has_answer_contract is False
        assert result.cycle_info.current_assertion_cycle_id == 0

    def test_empty_dict_returns_valid_projection(self):
        result = project_case_workspace({})
        assert isinstance(result, CaseWorkspaceProjection)

    def test_rich_state_populates_all_sections(self):
        result = project_case_workspace(_rich_state())
        assert result.case_summary.thread_id == "t-abc-123"
        assert result.case_summary.intent_goal == "design_recommendation"
        assert result.case_summary.seal_family == "O-Ring"
        assert result.completeness.coverage_score == 0.65
        assert result.governance_status.release_status == "precheck_only"
        assert result.candidate_clusters.total_candidates == 3
        assert result.conflicts.total == 2
        assert result.claims_summary.total == 3
        assert result.rfq_status.admissibility_status == "provisional"
        assert result.artifact_status.has_answer_contract is True
        assert result.cycle_info.current_assertion_cycle_id == 2

    def test_serialization_roundtrip(self):
        result = project_case_workspace(_rich_state())
        json_data = result.model_dump()
        restored = CaseWorkspaceProjection.model_validate(json_data)
        assert restored.case_summary.thread_id == "t-abc-123"
        assert restored.conflicts.total == 2


# ---------------------------------------------------------------------------
# Test 2: Governance values projected correctly
# ---------------------------------------------------------------------------

class TestGovernanceProjection:
    def test_governance_from_answer_contract(self):
        result = project_case_workspace(_rich_state())
        gov = result.governance_status
        assert gov.release_status == "precheck_only"
        assert "hydraulic_cylinder" in gov.scope_of_validity
        assert "standard_surface_finish" in gov.assumptions_active
        assert "speed_rpm" in gov.unknowns_release_blocking
        assert gov.verification_passed is True

    def test_required_disclaimers_projected(self):
        result = project_case_workspace(_rich_state())
        assert len(result.governance_status.required_disclaimers) == 1
        assert "Precheck only" in result.governance_status.required_disclaimers[0]

    def test_governance_fallback_to_system_metadata(self):
        state = _minimal_state()
        state["system"]["governance_metadata"] = {
            "scope_of_validity": ["static_seal"],
            "gate_failures": ["chem_guard_fail"],
        }
        result = project_case_workspace(state)
        assert "static_seal" in result.governance_status.scope_of_validity
        assert "chem_guard_fail" in result.governance_status.gate_failures

    def test_all_four_release_statuses(self):
        for status in ["inadmissible", "precheck_only", "manufacturer_validation_required", "rfq_ready"]:
            state = _minimal_state()
            state["system"]["answer_contract"] = {"release_status": status}
            result = project_case_workspace(state)
            assert result.governance_status.release_status == status


# ---------------------------------------------------------------------------
# Test 3: Stale / RFQ / release / completeness states
# ---------------------------------------------------------------------------

class TestStaleAndCompletenessProjection:
    def test_staleness_from_reasoning(self):
        state = _minimal_state()
        state["reasoning"]["derived_artifacts_stale"] = True
        state["reasoning"]["derived_artifacts_stale_reason"] = "parameter_changed"
        result = project_case_workspace(state)
        assert result.cycle_info.derived_artifacts_stale is True
        assert result.cycle_info.stale_reason == "parameter_changed"

    def test_staleness_from_working_profile(self):
        state = _minimal_state()
        state["working_profile"]["derived_artifacts_stale"] = True
        state["working_profile"]["derived_artifacts_stale_reason"] = "profile_updated"
        result = project_case_workspace(state)
        assert result.cycle_info.derived_artifacts_stale is True

    def test_staleness_from_system(self):
        state = _minimal_state()
        state["system"]["derived_artifacts_stale"] = True
        result = project_case_workspace(state)
        assert result.cycle_info.derived_artifacts_stale is True

    def test_rfq_ready_and_confirmed(self):
        state = _minimal_state()
        state["system"]["rfq_admissibility"] = {
            "status": "ready",
            "release_status": "rfq_ready",
        }
        state["system"]["rfq_confirmed"] = True
        state["reasoning"]["rfq_ready"] = True
        result = project_case_workspace(state)
        assert result.rfq_status.admissibility_status == "ready"
        assert result.rfq_status.release_status == "rfq_ready"
        assert result.rfq_status.rfq_confirmed is True
        assert result.rfq_status.rfq_ready is True

    def test_completeness_missing_critical_from_answer_contract(self):
        result = project_case_workspace(_rich_state())
        assert "speed_rpm" in result.completeness.missing_critical_parameters

    def test_completeness_fallback_to_sealing_requirement_spec(self):
        state = _minimal_state()
        state["system"]["sealing_requirement_spec"] = {
            "missing_critical_parameters": ["housing_bore"],
        }
        result = project_case_workspace(state)
        assert "housing_bore" in result.completeness.missing_critical_parameters

    def test_completeness_depth_projected(self):
        state = _minimal_state()
        state["reasoning"]["completeness_depth"] = "critical_review"
        result = project_case_workspace(state)
        assert result.completeness.completeness_depth == "critical_review"
        assert result.specificity.completeness_depth == "critical_review"

    def test_rfq_pdf_presence(self):
        state = _minimal_state()
        state["system"]["rfq_pdf_base64"] = "base64data..."
        state["system"]["rfq_html_report"] = "<html>...</html>"
        result = project_case_workspace(state)
        assert result.rfq_status.has_pdf is True
        assert result.rfq_status.has_html_report is True


# ---------------------------------------------------------------------------
# Test 4: Candidate / conflict / claim summaries
# ---------------------------------------------------------------------------

class TestCandidateConflictClaimAggregation:
    def test_candidate_clusters_counts(self):
        result = project_case_workspace(_rich_state())
        cc = result.candidate_clusters
        assert len(cc.plausibly_viable) == 1
        assert len(cc.manufacturer_validation_required) == 1
        assert len(cc.inadmissible_or_excluded) == 1
        assert cc.total_candidates == 3

    def test_candidate_clusters_empty(self):
        result = project_case_workspace(_minimal_state())
        cc = result.candidate_clusters
        assert cc.total_candidates == 0
        assert cc.plausibly_viable == []

    def test_conflict_summary_aggregation(self):
        result = project_case_workspace(_rich_state())
        c = result.conflicts
        assert c.total == 2
        assert c.open == 1
        assert c.resolved == 1
        assert c.by_severity.get("HARD") == 1
        assert c.by_severity.get("SOFT") == 1

    def test_conflict_items_ui_shape(self):
        result = project_case_workspace(_rich_state())
        item = result.conflicts.items[0]
        assert "conflict_type" in item
        assert "severity" in item
        assert "summary" in item
        assert "resolution_status" in item
        # Should NOT contain internal fields like sources_involved
        assert "sources_involved" not in item

    def test_claims_summary_by_type(self):
        result = project_case_workspace(_rich_state())
        cs = result.claims_summary
        assert cs.total == 3
        assert cs.by_type.get("evidence_based_assertion") == 1
        assert cs.by_type.get("deterministic_fact") == 2

    def test_claims_summary_by_origin(self):
        result = project_case_workspace(_rich_state())
        cs = result.claims_summary
        assert cs.by_origin.get("evidence") == 1
        assert cs.by_origin.get("deterministic") == 2

    def test_claims_fallback_to_reasoning(self):
        state = _minimal_state()
        state["reasoning"]["claims"] = [
            {"value": "X", "claim_type": "heuristic_hint", "claim_origin": "heuristic"},
        ]
        result = project_case_workspace(state)
        assert result.claims_summary.total == 1
        assert result.claims_summary.by_type.get("heuristic_hint") == 1


# ---------------------------------------------------------------------------
# Test 5: Manufacturer questions and open questions
# ---------------------------------------------------------------------------

class TestManufacturerQuestionsProjection:
    def test_mandatory_questions_from_rfq_draft(self):
        result = project_case_workspace(_rich_state())
        mq = result.manufacturer_questions
        assert len(mq.mandatory) == 2
        assert "Compound" in mq.mandatory[0]

    def test_open_questions_filtered(self):
        result = project_case_workspace(_rich_state())
        mq = result.manufacturer_questions
        # Only status=open should appear
        assert mq.total_open == 1
        assert mq.open_questions[0]["id"] == "q1"

    def test_open_questions_ui_shape(self):
        result = project_case_workspace(_rich_state())
        q = result.manufacturer_questions.open_questions[0]
        assert "id" in q
        assert "question" in q
        assert "reason" in q
        assert "priority" in q
        assert "category" in q
        # Should NOT contain status (filtered for open only)


# ---------------------------------------------------------------------------
# Test 6: Artifact status
# ---------------------------------------------------------------------------

class TestArtifactStatusProjection:
    def test_rich_state_artifacts(self):
        result = project_case_workspace(_rich_state())
        a = result.artifact_status
        assert a.has_answer_contract is True
        assert a.contract_id == "contract-c2-r3"
        assert a.contract_obsolete is False
        assert a.has_verification_report is True
        assert a.has_sealing_requirement_spec is True
        assert a.has_rfq_draft is True
        assert a.has_recommendation is True
        assert a.has_live_calc_tile is True
        assert a.live_calc_status == "warning"

    def test_live_calc_insufficient_data(self):
        state = _minimal_state()
        state["working_profile"]["live_calc_tile"] = {"status": "insufficient_data"}
        result = project_case_workspace(state)
        assert result.artifact_status.has_live_calc_tile is False
        assert result.artifact_status.live_calc_status == "insufficient_data"

    def test_obsolete_contract(self):
        state = _minimal_state()
        state["system"]["answer_contract"] = {
            "contract_id": "old-contract",
            "obsolete": True,
        }
        result = project_case_workspace(state)
        assert result.artifact_status.contract_obsolete is True


# ---------------------------------------------------------------------------
# Test 7: Edge cases and robustness
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_intent_as_string(self):
        state = _minimal_state()
        state["conversation"]["intent"] = "smalltalk"
        result = project_case_workspace(state)
        assert result.case_summary.intent_goal == "smalltalk"

    def test_none_pillars(self):
        state = {
            "conversation": None,
            "working_profile": None,
            "reasoning": None,
            "system": None,
        }
        result = project_case_workspace(state)
        assert isinstance(result, CaseWorkspaceProjection)

    def test_non_dict_pillar_values_handled(self):
        state = {
            "conversation": "invalid",
            "working_profile": 42,
            "reasoning": [],
            "system": True,
        }
        result = project_case_workspace(state)
        assert isinstance(result, CaseWorkspaceProjection)


# ---------------------------------------------------------------------------
# Test 8: RFQ Package projection (v1.3 Patch B1)
# ---------------------------------------------------------------------------

class TestRFQPackageProjection:
    def test_rfq_package_defaults_when_no_draft(self):
        result = project_case_workspace(_minimal_state())
        pkg = result.rfq_package
        assert pkg.has_draft is False
        assert pkg.rfq_id is None
        assert pkg.rfq_basis_status == "inadmissible"
        assert pkg.operating_context_redacted == {}
        assert pkg.manufacturer_questions_mandatory == []
        assert pkg.conflicts_visible_count == 0
        assert pkg.buyer_assumptions_acknowledged == []

    def test_rfq_package_populated_from_draft(self):
        result = project_case_workspace(_rich_state())
        pkg = result.rfq_package
        assert pkg.has_draft is True
        assert pkg.rfq_id == "rfq-001"
        assert len(pkg.manufacturer_questions_mandatory) == 2
        assert "Compound" in pkg.manufacturer_questions_mandatory[0]

    def test_rfq_package_with_full_draft(self):
        state = _minimal_state()
        state["system"]["rfq_draft"] = {
            "rfq_id": "rfq-c3-r5",
            "rfq_basis_status": "manufacturer_validation_required",
            "operating_context_redacted": {
                "medium": "HLP 46",
                "pressure_bar": 250.0,
                "temperature_C": 80.0,
                "shaft_diameter": 50.0,
            },
            "manufacturer_questions_mandatory": ["Compound release?"],
            "conflicts_visible": [
                {"conflict_type": "PARAMETER_CONFLICT", "severity": "HARD", "summary": "Pressure limit"},
            ],
            "buyer_assumptions_acknowledged": ["Standard surface finish assumed"],
        }
        result = project_case_workspace(state)
        pkg = result.rfq_package
        assert pkg.has_draft is True
        assert pkg.rfq_id == "rfq-c3-r5"
        assert pkg.rfq_basis_status == "manufacturer_validation_required"
        assert pkg.operating_context_redacted["medium"] == "HLP 46"
        assert pkg.operating_context_redacted["pressure_bar"] == 250.0
        assert len(pkg.operating_context_redacted) == 4
        assert pkg.manufacturer_questions_mandatory == ["Compound release?"]
        assert pkg.conflicts_visible_count == 1
        assert pkg.buyer_assumptions_acknowledged == ["Standard surface finish assumed"]

    def test_rfq_package_empty_draft_object(self):
        state = _minimal_state()
        state["system"]["rfq_draft"] = {}
        result = project_case_workspace(state)
        assert result.rfq_package.has_draft is False

    def test_rfq_package_serialization_roundtrip(self):
        state = _minimal_state()
        state["system"]["rfq_draft"] = {
            "rfq_id": "rfq-test",
            "rfq_basis_status": "rfq_ready",
            "operating_context_redacted": {"medium": "Water"},
            "manufacturer_questions_mandatory": [],
            "conflicts_visible": [],
            "buyer_assumptions_acknowledged": ["Assumption A"],
        }
        result = project_case_workspace(state)
        json_data = result.model_dump()
        restored = CaseWorkspaceProjection.model_validate(json_data)
        assert restored.rfq_package.rfq_id == "rfq-test"
        assert restored.rfq_package.rfq_basis_status == "rfq_ready"
        assert restored.rfq_package.operating_context_redacted == {"medium": "Water"}
        assert restored.rfq_package.buyer_assumptions_acknowledged == ["Assumption A"]

    def test_rfq_package_inadmissible_no_context_leak(self):
        """When rfq_basis_status is inadmissible, the draft should still be surfaced
        if it exists — the UI decides what to show based on status."""
        state = _minimal_state()
        state["system"]["rfq_draft"] = {
            "rfq_id": "rfq-blocked",
            "rfq_basis_status": "inadmissible",
            "operating_context_redacted": {"medium": "H2S"},
        }
        result = project_case_workspace(state)
        assert result.rfq_package.has_draft is True
        assert result.rfq_package.rfq_basis_status == "inadmissible"
        assert result.rfq_package.operating_context_redacted == {"medium": "H2S"}


# ---------------------------------------------------------------------------
# Test 9: RFQ Confirmation gate logic (v1.3 Patch B2)
# ---------------------------------------------------------------------------

class TestRFQConfirmationGates:
    """Tests that confirm gates are derivable from projection state."""

    def _confirmable_state(self) -> dict:
        """State where RFQ confirmation should be allowed."""
        state = _minimal_state()
        state["system"]["rfq_draft"] = {
            "rfq_id": "rfq-c1-r1",
            "rfq_basis_status": "precheck_only",
            "operating_context_redacted": {"medium": "HLP 46"},
        }
        state["system"]["rfq_admissibility"] = {
            "status": "provisional",
            "release_status": "precheck_only",
        }
        state["system"]["rfq_confirmed"] = False
        return state

    def test_confirmable_state_passes_all_gates(self):
        result = project_case_workspace(self._confirmable_state())
        assert result.rfq_package.has_draft is True
        assert result.rfq_status.release_status != "inadmissible"
        assert result.cycle_info.derived_artifacts_stale is False
        assert result.rfq_status.rfq_confirmed is False

    def test_gate_no_draft_blocks(self):
        state = self._confirmable_state()
        state["system"]["rfq_draft"] = None
        result = project_case_workspace(state)
        assert result.rfq_package.has_draft is False

    def test_gate_inadmissible_blocks(self):
        state = self._confirmable_state()
        state["system"]["rfq_admissibility"] = {
            "status": "inadmissible",
            "release_status": "inadmissible",
        }
        result = project_case_workspace(state)
        assert result.rfq_status.release_status == "inadmissible"

    def test_gate_stale_blocks(self):
        state = self._confirmable_state()
        state["reasoning"]["derived_artifacts_stale"] = True
        result = project_case_workspace(state)
        assert result.cycle_info.derived_artifacts_stale is True

    def test_gate_already_confirmed_blocks(self):
        state = self._confirmable_state()
        state["system"]["rfq_confirmed"] = True
        result = project_case_workspace(state)
        assert result.rfq_status.rfq_confirmed is True

    def test_rfq_ready_state_is_confirmable(self):
        state = self._confirmable_state()
        state["system"]["rfq_admissibility"] = {
            "status": "ready",
            "release_status": "rfq_ready",
        }
        result = project_case_workspace(state)
        assert result.rfq_status.release_status == "rfq_ready"
        assert result.rfq_package.has_draft is True
        assert result.rfq_status.rfq_confirmed is False

    def test_confirmed_state_reflects_in_projection(self):
        state = self._confirmable_state()
        state["system"]["rfq_confirmed"] = True
        result = project_case_workspace(state)
        assert result.rfq_status.rfq_confirmed is True
        # Draft should still be present
        assert result.rfq_package.has_draft is True


# ---------------------------------------------------------------------------
# Test 10: Partner Matching projection (v1.3 Patch B4)
# ---------------------------------------------------------------------------

class TestPartnerMatchingProjection:
    """Tests for _build_partner_matching — manufacturer fit surface."""

    def _matching_ready_state(self) -> dict:
        """State where partner matching should be ready."""
        state = _minimal_state()
        state["system"]["rfq_confirmed"] = True
        state["system"]["rfq_draft"] = {
            "rfq_id": "rfq-c1-r1",
            "rfq_basis_status": "precheck_only",
            "operating_context_redacted": {"medium": "HLP 46"},
            "manufacturer_questions_mandatory": ["Compound-spezifische Freigabe?"],
        }
        state["system"]["rfq_admissibility"] = {
            "status": "provisional",
            "release_status": "precheck_only",
        }
        state["system"]["answer_contract"] = {
            "release_status": "precheck_only",
            "candidate_clusters": {
                "plausibly_viable": [
                    {"kind": "material", "value": "FKM", "specificity": "family_only"},
                ],
                "viable_only_with_manufacturer_validation": [
                    {"kind": "material", "value": "HNBR", "specificity": "compound_required"},
                ],
                "inadmissible_or_excluded": [],
            },
        }
        return state

    def test_defaults_when_minimal_state(self):
        result = project_case_workspace(_minimal_state())
        pm = result.partner_matching
        assert pm.matching_ready is False
        assert pm.data_source == "candidate_derived"
        assert pm.material_fit_items == []
        assert len(pm.not_ready_reasons) > 0

    def test_not_ready_when_rfq_not_confirmed(self):
        state = self._matching_ready_state()
        state["system"]["rfq_confirmed"] = False
        result = project_case_workspace(state)
        assert result.partner_matching.matching_ready is False
        assert any("not yet confirmed" in r for r in result.partner_matching.not_ready_reasons)

    def test_not_ready_when_no_draft(self):
        state = self._matching_ready_state()
        state["system"]["rfq_draft"] = None
        result = project_case_workspace(state)
        assert result.partner_matching.matching_ready is False
        assert any("No RFQ draft" in r for r in result.partner_matching.not_ready_reasons)

    def test_not_ready_when_inadmissible(self):
        state = self._matching_ready_state()
        state["system"]["rfq_admissibility"] = {
            "status": "inadmissible",
            "release_status": "inadmissible",
        }
        result = project_case_workspace(state)
        assert result.partner_matching.matching_ready is False
        assert any("inadmissible" in r for r in result.partner_matching.not_ready_reasons)

    def test_not_ready_when_stale(self):
        state = self._matching_ready_state()
        state["reasoning"]["derived_artifacts_stale"] = True
        result = project_case_workspace(state)
        assert result.partner_matching.matching_ready is False
        assert any("stale" in r.lower() for r in result.partner_matching.not_ready_reasons)

    def test_ready_when_all_gates_pass(self):
        result = project_case_workspace(self._matching_ready_state())
        pm = result.partner_matching
        assert pm.matching_ready is True
        assert pm.not_ready_reasons == []

    def test_viable_candidate_produces_fit_item(self):
        result = project_case_workspace(self._matching_ready_state())
        pm = result.partner_matching
        viable = [i for i in pm.material_fit_items if i.cluster == "viable"]
        assert len(viable) == 1
        assert viable[0].material == "FKM"
        assert viable[0].requires_validation is False
        assert viable[0].specificity == "family_only"

    def test_mfr_validation_candidate_produces_fit_item(self):
        result = project_case_workspace(self._matching_ready_state())
        pm = result.partner_matching
        mfr = [i for i in pm.material_fit_items if i.cluster == "manufacturer_validation"]
        assert len(mfr) == 1
        assert mfr[0].material == "HNBR"
        assert mfr[0].requires_validation is True
        assert mfr[0].specificity == "compound_required"

    def test_open_questions_collected(self):
        result = project_case_workspace(self._matching_ready_state())
        pm = result.partner_matching
        assert len(pm.open_manufacturer_questions) >= 1
        assert any("Compound" in q for q in pm.open_manufacturer_questions)

    def test_rich_state_partner_matching(self):
        result = project_case_workspace(_rich_state())
        pm = result.partner_matching
        # rich_state has rfq_confirmed=False, so not ready
        assert pm.matching_ready is False
        # But should still have material fit items from candidates
        assert len(pm.material_fit_items) == 2  # FKM viable + HNBR mfr_validation

    def test_serialization_roundtrip(self):
        result = project_case_workspace(self._matching_ready_state())
        json_data = result.model_dump()
        restored = CaseWorkspaceProjection.model_validate(json_data)
        assert restored.partner_matching.matching_ready is True
        assert len(restored.partner_matching.material_fit_items) == 2
        assert restored.partner_matching.data_source == "candidate_derived"


# ---------------------------------------------------------------------------
# Test 11: RFQ HTML document generation (v1.3 Patch B3)
# ---------------------------------------------------------------------------

class TestRFQDocumentGeneration:
    """Tests for render_rfq_html and PDF CTA gate logic."""

    def _pdf_ready_state(self) -> dict:
        """State where PDF generation should be allowed (confirmed, not stale, has draft)."""
        state = _minimal_state()
        state["system"]["rfq_confirmed"] = True
        state["system"]["rfq_draft"] = {
            "rfq_id": "rfq-c1-r1",
            "rfq_basis_status": "precheck_only",
            "operating_context_redacted": {
                "medium": "HLP 46",
                "pressure_bar": 250.0,
                "temperature_C": 80.0,
            },
            "manufacturer_questions_mandatory": ["Compound-Freigabe?"],
            "buyer_assumptions_acknowledged": ["Standard surface finish"],
        }
        state["system"]["rfq_admissibility"] = {
            "status": "provisional",
            "release_status": "precheck_only",
        }
        state["system"]["answer_contract"] = {
            "release_status": "precheck_only",
            "candidate_clusters": {
                "plausibly_viable": [
                    {"kind": "material", "value": "FKM", "specificity": "family_only"},
                ],
                "viable_only_with_manufacturer_validation": [],
                "inadmissible_or_excluded": [],
            },
            "required_disclaimers": ["Precheck only — no manufacturer validation"],
            "governance_metadata": {
                "assumptions_active": ["Standard surface finish"],
            },
        }
        state["system"]["governance_metadata"] = {}
        return state

    def test_pdf_gate_requires_confirmed(self):
        """PDF generation requires rfq_confirmed=True."""
        state = self._pdf_ready_state()
        state["system"]["rfq_confirmed"] = False
        result = project_case_workspace(state)
        assert result.rfq_status.rfq_confirmed is False

    def test_pdf_gate_requires_draft(self):
        """PDF generation requires has_draft=True."""
        state = self._pdf_ready_state()
        state["system"]["rfq_draft"] = None
        result = project_case_workspace(state)
        assert result.rfq_package.has_draft is False

    def test_pdf_gate_blocks_inadmissible(self):
        """PDF generation blocked when inadmissible."""
        state = self._pdf_ready_state()
        state["system"]["rfq_admissibility"]["release_status"] = "inadmissible"
        result = project_case_workspace(state)
        assert result.rfq_status.release_status == "inadmissible"

    def test_pdf_gate_blocks_stale(self):
        """PDF generation blocked when artifacts stale."""
        state = self._pdf_ready_state()
        state["reasoning"]["derived_artifacts_stale"] = True
        result = project_case_workspace(state)
        assert result.cycle_info.derived_artifacts_stale is True

    def test_pdf_gate_all_pass(self):
        """When all gates pass, PDF generation is allowed."""
        result = project_case_workspace(self._pdf_ready_state())
        assert result.rfq_status.rfq_confirmed is True
        assert result.rfq_package.has_draft is True
        assert result.rfq_status.release_status != "inadmissible"
        assert result.cycle_info.derived_artifacts_stale is False

    def test_has_html_report_false_by_default(self):
        """No HTML report until generated."""
        result = project_case_workspace(self._pdf_ready_state())
        assert result.rfq_status.has_html_report is False

    def test_has_html_report_true_when_stored(self):
        """has_html_report becomes True when rfq_html_report is in state."""
        state = self._pdf_ready_state()
        state["system"]["rfq_html_report"] = "<html>report</html>"
        result = project_case_workspace(state)
        assert result.rfq_status.has_html_report is True

    def test_render_rfq_html_produces_valid_html(self):
        """render_rfq_html produces a non-empty HTML document."""
        from app.api.v1.renderers.rfq_html import render_rfq_html
        result = project_case_workspace(self._pdf_ready_state())
        html = render_rfq_html(result)
        assert "<!doctype html>" in html.lower()
        assert "SEALAI" in html
        assert "rfq-c1-r1" in html

    def test_render_rfq_html_includes_operating_context(self):
        """Rendered HTML includes the redacted operating context."""
        from app.api.v1.renderers.rfq_html import render_rfq_html
        result = project_case_workspace(self._pdf_ready_state())
        html = render_rfq_html(result)
        assert "HLP 46" in html
        assert "250.0" in html
        assert "80.0" in html

    def test_render_rfq_html_includes_candidates(self):
        """Rendered HTML includes candidate materials."""
        from app.api.v1.renderers.rfq_html import render_rfq_html
        result = project_case_workspace(self._pdf_ready_state())
        html = render_rfq_html(result)
        assert "FKM" in html
        assert "Viable" in html

    def test_render_rfq_html_includes_disclaimers(self):
        """Rendered HTML includes required disclaimers."""
        from app.api.v1.renderers.rfq_html import render_rfq_html
        result = project_case_workspace(self._pdf_ready_state())
        html = render_rfq_html(result)
        assert "Precheck only" in html

    def test_render_rfq_html_includes_questions(self):
        """Rendered HTML includes mandatory manufacturer questions."""
        from app.api.v1.renderers.rfq_html import render_rfq_html
        result = project_case_workspace(self._pdf_ready_state())
        html = render_rfq_html(result)
        assert "Compound-Freigabe?" in html

    def test_render_rfq_html_minimal_state_no_crash(self):
        """render_rfq_html handles minimal state without crashing."""
        from app.api.v1.renderers.rfq_html import render_rfq_html
        result = project_case_workspace(_minimal_state())
        html = render_rfq_html(result)
        assert "<!doctype html>" in html.lower()
        assert "SEALAI" in html

    def test_html_report_cleared_on_stale(self):
        """When artifacts become stale, has_html_report reflects stored state.
        (assertion_cycle.py clears rfq_html_report to None on staleness.)"""
        state = self._pdf_ready_state()
        state["system"]["rfq_html_report"] = "<html>old</html>"
        state["reasoning"]["derived_artifacts_stale"] = True
        result = project_case_workspace(state)
        # HTML report still shows as present (it's stored), but stale flag is set
        assert result.rfq_status.has_html_report is True
        assert result.cycle_info.derived_artifacts_stale is True


# ---------------------------------------------------------------------------
# Test 12: Case Lifecycle Surface data (v1.3 Patch A4)
# ---------------------------------------------------------------------------

class TestCaseLifecycleProjection:
    """Verifies all lifecycle-relevant fields are correctly projected."""

    def test_lifecycle_fields_on_rich_state(self):
        """A rich state should project all lifecycle-relevant booleans/markers."""
        result = project_case_workspace(_rich_state())
        # Cycle info
        assert result.cycle_info.current_assertion_cycle_id == 2
        assert result.cycle_info.state_revision == 7
        assert result.cycle_info.asserted_profile_revision == 3
        assert result.cycle_info.derived_artifacts_stale is False
        # Artifacts
        assert result.artifact_status.has_answer_contract is True
        assert result.artifact_status.contract_id == "contract-c2-r3"
        assert result.artifact_status.contract_obsolete is False
        assert result.artifact_status.has_verification_report is True
        assert result.artifact_status.has_rfq_draft is True
        # RFQ
        assert result.rfq_status.rfq_confirmed is False
        assert result.rfq_status.has_html_report is False
        # Governance
        assert result.governance_status.verification_passed is True
        assert result.governance_status.release_status == "precheck_only"
        # Case summary
        assert result.case_summary.turn_count == 4

    def test_lifecycle_all_done_state(self):
        """A fully progressed state should show all lifecycle markers as done."""
        state = _rich_state()
        state["system"]["rfq_confirmed"] = True
        state["system"]["rfq_html_report"] = "<html>done</html>"
        result = project_case_workspace(state)
        assert result.rfq_status.rfq_confirmed is True
        assert result.rfq_status.has_html_report is True
        assert result.artifact_status.has_answer_contract is True
        assert result.artifact_status.has_verification_report is True
        assert result.artifact_status.has_rfq_draft is True
        assert result.cycle_info.derived_artifacts_stale is False

    def test_lifecycle_stale_invalidates_freshness(self):
        """When stale, lifecycle freshness should reflect correctly."""
        state = _rich_state()
        state["reasoning"]["derived_artifacts_stale"] = True
        state["reasoning"]["derived_artifacts_stale_reason"] = "parameter_changed"
        result = project_case_workspace(state)
        assert result.cycle_info.derived_artifacts_stale is True
        assert result.cycle_info.stale_reason == "parameter_changed"
        # Other lifecycle markers still present
        assert result.artifact_status.has_answer_contract is True
        assert result.rfq_status.rfq_confirmed is False

    def test_lifecycle_minimal_state_safe_defaults(self):
        """Minimal state should not crash lifecycle derivation."""
        result = project_case_workspace(_minimal_state())
        assert result.cycle_info.current_assertion_cycle_id == 0
        assert result.cycle_info.state_revision == 0
        assert result.cycle_info.derived_artifacts_stale is False
        assert result.artifact_status.has_answer_contract is False
        assert result.rfq_status.rfq_confirmed is False
        assert result.rfq_status.has_html_report is False

    def test_lifecycle_obsolete_contract_flagged(self):
        """Obsolete contract should be visible in lifecycle."""
        state = _minimal_state()
        state["system"]["answer_contract"] = {
            "contract_id": "old-c",
            "obsolete": True,
        }
        result = project_case_workspace(state)
        assert result.artifact_status.has_answer_contract is True
        assert result.artifact_status.contract_obsolete is True
        assert result.artifact_status.contract_id == "old-c"
