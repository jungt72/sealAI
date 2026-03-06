from __future__ import annotations

from app.langgraph_v2.nodes.combinatorial_chemistry_guard import (
    combinatorial_chemistry_guard_node,
)
from app.langgraph_v2.state import SealAIState
from app.services.rag.state import ConflictRecord, WorkingProfile


def test_combinatorial_chemistry_guard_allows_generic_fkm_amines_terms() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            material="FKM",
            medium_additives="Filming amines and inhibitor package",
        )
    )

    command = combinatorial_chemistry_guard_node(state)
    profile = command.update["working_profile"]["engineering_profile"]

    assert command.goto == "node_router"
    assert profile.risk_mitigated is True
    assert all(item.severity != "BLOCKER" for item in profile.conflicts_detected)
    assert all(item.rule_id != "CHEM_FKM_AMINE_BLOCKER" for item in profile.conflicts_detected)


def test_combinatorial_chemistry_guard_sets_blocker_for_fkm_specific_amines() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            material="FKM",
            medium_additives="Contains morpholine and inhibitor package",
        )
    )

    command = combinatorial_chemistry_guard_node(state)
    profile = command.update["working_profile"]["engineering_profile"]

    assert command.goto == "request_clarification_node"
    assert profile.risk_mitigated is False
    assert any(item.severity == "BLOCKER" for item in profile.conflicts_detected)
    assert any(item.rule_id == "CHEM_FKM_AMINE_BLOCKER" for item in profile.conflicts_detected)


def test_combinatorial_chemistry_guard_sets_blocker_for_aed_without_certification() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            material="FKM",
            aed_required=True,
            compound_aed_certified=False,
        )
    )

    command = combinatorial_chemistry_guard_node(state)
    profile = command.update["working_profile"]["engineering_profile"]

    assert profile.risk_mitigated is False
    assert any(item.rule_id == "CHEM_FKM_AED_CERT_BLOCKER" for item in profile.conflicts_detected)


def test_combinatorial_chemistry_guard_appends_conflicts_and_keeps_non_blocker_risk_flag() -> None:
    existing = ConflictRecord(
        rule_id="EXISTING_NOTE",
        severity="NOTE",
        title="Existing note",
        condition="seeded",
        reason="Seeded conflict for merge behavior",
    )
    state = SealAIState(
        working_profile=WorkingProfile(
            material="EPDM",
            pressure_max_bar=120.0,
            extrusion_gap_mm=0.35,
            risk_mitigated=True,
            conflicts_detected=[existing],
        )
    )

    command = combinatorial_chemistry_guard_node(state)
    profile = command.update["working_profile"]["engineering_profile"]

    assert any(item.rule_id == "EXISTING_NOTE" for item in profile.conflicts_detected)
    assert any(item.rule_id == "MECH_HIGH_PRESSURE_GAP_BLOCKER" for item in profile.conflicts_detected)
    assert profile.risk_mitigated is False
