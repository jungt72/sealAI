from __future__ import annotations

import hashlib

from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app.langgraph_v2.nodes.answer_subgraph.state import AnswerSubgraphState
from app.langgraph_v2.state.sealai_state import SealAIState, WorkingProfile, WorkingMemory


def _contract_hash(contract) -> str:
    return hashlib.sha256(contract.model_dump_json().encode()).hexdigest()


def test_evidence_authority_prefers_din_norm_pressure_truth() -> None:
    state = SealAIState(
        reasoning={
            "working_memory": WorkingMemory(
                panel_material={
                    "technical_docs": [
                        {
                            "text": "Max Druck 100 bar",
                            "source": "Forum/Unknown",
                            "metadata": {
                                "document_id": "forum_doc",
                                "chunk_id": "c1",
                                "source_type": "forum",
                            },
                            "score": 0.95,
                        },
                        {
                            "text": "Max Druck 80 bar",
                            "source": "DIN-Norm",
                            "metadata": {
                                "document_id": "din_doc",
                                "chunk_id": "c2",
                                "source_type": "DIN standard",
                            },
                            "score": 0.40,
                        },
                    ]
                }
            )
        }
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.resolved_parameters.get("pressure_bar") == 80.0
    assert "din_doc:c2" in contract.selected_fact_ids
    assert "forum_doc:c1" in contract.selected_fact_ids


def test_smalltalk_heuristic_when_no_params_and_no_rag_chunks() -> None:
    state = SealAIState()

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.resolved_parameters.get("response_style") == "friendly_greeting"
    assert contract.calc_results.get("message_type") == "smalltalk"
    assert contract.selected_fact_ids == ["friendly_greeting"]
    assert contract.respond_with_uncertainty is False


def test_parameter_patching_copies_user_parameters_into_contract() -> None:
    state = SealAIState(
        working_profile={"engineering_profile": {"medium": "Wasser"}},
        reasoning={"current_assertion_cycle_id": 3, "asserted_profile_revision": 7},
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.resolved_parameters.get("medium") == "Wasser"
    assert patch["system"]["derived_from_assertion_cycle_id"] == 3
    assert patch["system"]["derived_from_assertion_revision"] == 7
    assert patch["system"]["derived_artifacts_stale"] is False


def test_extracted_rpm_and_shaft_aliases_flow_into_contract_parameters() -> None:
    state = SealAIState(
        working_profile={
            "extracted_params": {
                "rpm": 1450.0,
                "shaft_d1_mm": 55.0,
            }
        }
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]
    allowed_tokens = set(patch["reasoning"]["flags"].get("answer_subgraph_allowed_number_tokens") or [])

    assert contract.resolved_parameters.get("rpm") == 1450.0
    assert contract.resolved_parameters.get("shaft_d1_mm") == 55.0
    assert contract.resolved_parameters.get("speed_rpm") == 1450.0
    assert contract.resolved_parameters.get("shaft_diameter") == 55.0
    assert "1450.0" in allowed_tokens
    assert "55.0" in allowed_tokens


def test_prepare_contract_ignores_unconfirmed_identity_guarded_extracted_fields() -> None:
    state = SealAIState(
        working_profile={
            "extracted_params": {
                "material": "Kyrolon",
                "medium": "Hydraulikoel HLP46",
                "pressure_bar": 120.0,
            }
        },
        reasoning={
            "extracted_parameter_identity": {
                "material": {
                    "identity_class": "probable",
                    "normalized_value": "Kyrolon",
                    "lookup_allowed": False,
                    "promotion_allowed": False,
                },
                "medium": {
                    "identity_class": "family_only",
                    "normalized_value": "oil",
                    "lookup_allowed": False,
                    "promotion_allowed": False,
                },
                "pressure_bar": {
                    "identity_class": "confirmed",
                    "normalized_value": 120.0,
                    "lookup_allowed": True,
                    "promotion_allowed": True,
                },
            }
        },
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert "material" not in contract.resolved_parameters
    assert "medium" not in contract.resolved_parameters
    assert contract.resolved_parameters.get("pressure_bar") == 120.0


def test_prepare_contract_exposes_candidate_specificity_for_unconfirmed_material_choice() -> None:
    state = SealAIState(
        material_choice={
            "material": "Kyrolon",
            "details": "Dokumenttreffer oder Produktname, noch nicht compoundscharf bestaetigt.",
            "confidence": "heuristic",
        },
        reasoning={
            "extracted_parameter_identity": {
                "material": {
                    "identity_class": "probable",
                    "normalized_value": "Kyrolon",
                    "lookup_allowed": False,
                    "promotion_allowed": False,
                }
            }
        },
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.candidate_semantics
    assert contract.candidate_semantics[0]["value"] == "Kyrolon"
    assert contract.candidate_semantics[0]["specificity"] == "unresolved"
    assert contract.candidate_semantics[0]["governed"] is False


def test_prepare_contract_collects_governance_metadata() -> None:
    state = SealAIState(
        material_choice={
            "material": "PTFE",
            "details": "Heuristischer Familienvorschlag.",
            "confidence": "heuristic",
        },
        reasoning={
            "missing_params": ["temperature_C"],
            "qgate_result": {
                "checks": [
                    {
                        "check_id": "medium_compatibility",
                        "severity": "CRITICAL",
                        "passed": False,
                        "message": "Medienvertraeglichkeit fuer aktuelles Medium ungeklaert.",
                    }
                ]
            },
        },
        system={"requires_human_review": True},
    )

    patch = node_prepare_contract(state)
    governance = patch["system"]["answer_contract"].governance_metadata

    assert governance.scope_of_validity
    assert any("aktuellen Assertion-Stand" in item for item in governance.scope_of_validity)
    assert any("temperature_C" in item for item in governance.assumptions_active)
    assert "Medienvertraeglichkeit fuer aktuelles Medium ungeklaert." in governance.unknowns_release_blocking
    assert any("PTFE" in item and "family_level" in item for item in governance.unknowns_manufacturer_validation)
    assert any(item.startswith("CRITICAL:") for item in governance.gate_failures)


def test_prepare_contract_allowlists_live_calc_and_rounded_numbers() -> None:
    state = SealAIState(
        working_profile={
            "extracted_params": {"rpm": 1500, "hrc_value": 40},
            "live_calc_tile": {
                "v_surface_m_s": 3.92,
                "pv_value_mpa_m_s": 117.8,
                "hrc_value": 40.0,
                "parameters": {"rpm": 1500, "hrc_value": 40},
                "status": "warning",
            },
            "calculation_result": {"recommended_hardness_hrc": 58.0},
        },
    )

    patch = node_prepare_contract(state)
    allowed_tokens = set(patch["reasoning"]["flags"].get("answer_subgraph_allowed_number_tokens") or [])

    assert "1500" in allowed_tokens
    assert "40" in allowed_tokens
    assert "58" in allowed_tokens
    assert "118" in allowed_tokens
    assert "3.92" in allowed_tokens
    assert "117.8" in allowed_tokens


def test_prepare_contract_moves_seal_compound_out_of_material_and_sets_seal_material() -> None:
    state = SealAIState(
        working_profile={
            "extracted_params": {"material": "PTFE"},
            "material_choice": {"material": "PTFE"},
        }
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.resolved_parameters.get("seal_material") == "PTFE"
    assert contract.resolved_parameters.get("material") is None
    assert contract.candidate_semantics[0]["specificity"] == "family_level"


def test_prepare_contract_accepts_dict_working_profile_in_answer_subgraph_state() -> None:
    state = AnswerSubgraphState(
        working_profile={
            "engineering_profile": {"medium": "Wasser"},
            "extracted_params": {"rpm": 1450.0},
            "material_choice": {"material": "PTFE"},
            "calc_results": {"safety_factor": 1.5},
        }
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.resolved_parameters.get("medium") == "Wasser"
    assert contract.resolved_parameters.get("rpm") == 1450.0
    assert contract.resolved_parameters.get("seal_material") == "PTFE"
    assert contract.calc_results.get("safety_factor") == 1.5


def test_contract_hash_integrity_identical_vs_minimal_change() -> None:
    base_state = SealAIState(
        reasoning={
            "working_memory": WorkingMemory(
                panel_material={
                    "technical_docs": [
                        {
                            "text": "Max Druck 80 bar",
                            "source": "DIN-Norm",
                            "metadata": {"document_id": "din_doc", "chunk_id": "c2", "source_type": "DIN"},
                        }
                    ]
                }
            )
        },
        working_profile={"engineering_profile": {"medium": "Wasser"}},
    )

    patch_a = node_prepare_contract(base_state)
    patch_b = node_prepare_contract(base_state)

    hash_a = patch_a["reasoning"]["flags"]["answer_contract_hash"]
    hash_b = patch_b["reasoning"]["flags"]["answer_contract_hash"]
    assert hash_a == hash_b
    assert hash_a == _contract_hash(patch_a["system"]["answer_contract"])
    assert hash_b == _contract_hash(patch_b["system"]["answer_contract"])

    changed_state = SealAIState(
        reasoning={
            "working_memory": WorkingMemory(
                panel_material={
                    "technical_docs": [
                        {
                            "text": "Max Druck 80 bar",
                            "source": "DIN-Norm",
                            "metadata": {"document_id": "din_doc", "chunk_id": "c3", "source_type": "DIN"},
                        }
                    ]
                }
            )
        },
        working_profile={"engineering_profile": {"medium": "Wasser"}},
    )
    patch_changed = node_prepare_contract(changed_state)
    changed_hash = patch_changed["reasoning"]["flags"]["answer_contract_hash"]

    assert changed_hash != hash_a


def test_upstream_blocker_flag_sets_excluded_by_gate_on_candidate() -> None:
    """excluded_by_gate derives from reasoning.flags set by combinatorial_chemistry_guard — no new lookup."""
    state = SealAIState(
        material_choice={"material": "FKM"},
        reasoning={
            "flags": {
                "combinatorial_chemistry_has_blocker": True,
                "combinatorial_chemistry_blocker_rule_ids": ["CHEM_FKM_AMINE_BLOCKER"],
            }
        },
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.candidate_semantics[0]["excluded_by_gate"] == "gate:CHEM_FKM_AMINE_BLOCKER"
    assert contract.candidate_clusters["inadmissible_or_excluded"][0]["value"] == "FKM"
    assert contract.candidate_clusters["plausibly_viable"] == []


def test_upstream_blocker_flag_does_not_exclude_unrelated_material() -> None:
    """A CHEM_FKM blocker must not exclude an NBR candidate."""
    state = SealAIState(
        material_choice={"material": "NBR"},
        reasoning={
            "flags": {
                "combinatorial_chemistry_has_blocker": True,
                "combinatorial_chemistry_blocker_rule_ids": ["CHEM_FKM_AMINE_BLOCKER"],
            }
        },
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.candidate_semantics[0]["excluded_by_gate"] is None
    assert contract.candidate_clusters["inadmissible_or_excluded"] == []


def test_mech_blocker_flag_excludes_any_material() -> None:
    """MECH_ blockers are geometry constraints — they exclude all materials."""
    state = SealAIState(
        material_choice={"material": "PTFE"},
        reasoning={
            "flags": {
                "combinatorial_chemistry_has_blocker": True,
                "combinatorial_chemistry_blocker_rule_ids": ["MECH_HIGH_PRESSURE_GAP_BLOCKER"],
            }
        },
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.candidate_semantics[0]["excluded_by_gate"] == "gate:MECH_HIGH_PRESSURE_GAP_BLOCKER"
    assert contract.candidate_clusters["inadmissible_or_excluded"][0]["value"] == "PTFE"


def test_no_blocker_flag_leaves_candidate_unexcluded() -> None:
    """When the guard ran but found no blocker, excluded_by_gate must be None."""
    state = SealAIState(
        material_choice={"material": "FKM"},
        reasoning={
            "flags": {
                "combinatorial_chemistry_has_blocker": False,
                "combinatorial_chemistry_blocker_rule_ids": [],
            }
        },
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert contract.candidate_semantics[0]["excluded_by_gate"] is None
    assert contract.candidate_clusters["inadmissible_or_excluded"] == []


def test_extreme_temperature_query_injects_required_factcards(monkeypatch) -> None:
    def _fake_search_technical_docs(query, material_code=None, *, tenant_id=None, k=5, metadata_filters=None):  # noqa: ARG001
        if "PTFE-F-008" in query:
            return {
                "hits": [
                    {
                        "snippet": "FactCard PTFE-F-008: PTFE remains usable at cryogenic temperatures with design controls.",
                        "source": "ptfe_factcards",
                        "document_id": "PTFE-F-008",
                        "metadata": {"id": "PTFE-F-008", "doc_type": "ptfe_factcard"},
                        "score": 0.99,
                    }
                ]
            }
        if "PTFE-F-062" in query:
            return {
                "hits": [
                    {
                        "snippet": "FactCard PTFE-F-062: sealing requires spring-energization/preload because PTFE creeps.",
                        "source": "ptfe_factcards",
                        "document_id": "PTFE-F-062",
                        "metadata": {"id": "PTFE-F-062", "doc_type": "ptfe_factcard"},
                        "score": 0.98,
                    }
                ]
            }
        return {"hits": []}

    monkeypatch.setattr("app.mcp.knowledge_tool.search_technical_docs", _fake_search_technical_docs)

    state = SealAIState(
        working_profile={"engineering_profile": {"temperature_C": -200.0}},
        conversation={"messages": [HumanMessage(content="Ist PTFE bei -200°C noch einsetzbar?")]},
        reasoning={"flags": {"frontdoor_intent_category": "ENGINEERING_CALCULATION"}},
    )

    patch = node_prepare_contract(state)
    selected_fact_ids = patch["system"]["answer_contract"].selected_fact_ids

    assert any("PTFE-F-008" in item for item in selected_fact_ids)
    assert any("PTFE-F-062" in item for item in selected_fact_ids)


def test_requirement_spec_is_populated_with_technical_conditions() -> None:
    state = SealAIState(
        working_profile={
            "engineering_profile": {
                "medium": "Hydrauliköl",
                "pressure_bar": 250.0,
                "temperature_C": 120.0,
            }
        }
    )
    # Inject missing_critical_parameters manually if needed, but here we test base extraction
    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]
    spec = contract.requirement_spec

    assert spec is not None
    assert spec.operating_conditions["medium"] == "Hydrauliköl"
    assert spec.operating_conditions["pressure_bar"] == 250.0
    assert spec.operating_conditions["temperature_C"] == 120.0

    # Verify it also exists in the state patch for working_profile
    assert patch["reasoning"]["working_memory"]["material_requirements"] == spec

