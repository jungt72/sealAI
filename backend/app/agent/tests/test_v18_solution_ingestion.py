"""V1.8 §6.4 datasheet ingestion → SolutionProfile candidates (P2-K2).

Covers the pure derivation/merge helpers and the commit-seam wiring that turns
datasheet document evidence into a candidate SolutionProfile (never confirmed).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.api.loaders import _update_governed_state_post_graph
from app.agent.graph import GraphState
from app.agent.state.models import (
    DocumentEvidenceState,
    GovernedSessionState,
    SolutionProfile,
)
from app.agent.state.solution import (
    merge_solution_profiles,
    solution_profiles_from_document_evidence,
)
from app.services.auth.dependencies import RequestUser


def _datasheet_evidence() -> DocumentEvidenceState:
    return DocumentEvidenceState(
        documents_seen=[
            {"document_ref": "doc_17", "document_type": "datasheet"},
            {"document_ref": "dwg_3", "document_type": "drawing"},
        ],
        candidate_facts=[
            {
                "field": "material",
                "value": "FKM",
                "source_ref": "doc_17",
                "source_page": 2,
            },
            {"field": "temp_max_continuous_c", "value": 150, "source_ref": "doc_17"},
            # drawing-sourced fact must NOT become a solution field
            {"field": "shaft_diameter_mm", "value": 35, "source_ref": "dwg_3"},
        ],
    )


def test_datasheet_candidates_become_one_candidate_profile() -> None:
    profiles = solution_profiles_from_document_evidence(_datasheet_evidence())
    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.solution_id == "sol_doc_doc_17"
    assert profile.state == "candidate"
    assert [f.field for f in profile.fields] == ["material", "temp_max_continuous_c"]
    material = profile.fields[0]
    assert material.origin == "datasheet_extracted"
    assert material.status == "pending_confirmation"  # never confirmed
    assert (material.source_doc, material.source_page) == ("doc_17", 2)
    # missing page → None (chunk-level page not always on the candidate)
    assert profile.fields[1].source_page is None


def test_non_solution_documents_are_ignored() -> None:
    evidence = DocumentEvidenceState(
        documents_seen=[{"document_ref": "sds_1", "document_type": "sds"}],
        candidate_facts=[{"field": "medium", "value": "oil", "source_ref": "sds_1"}],
    )
    assert solution_profiles_from_document_evidence(evidence) == []


def test_empty_evidence_returns_empty() -> None:
    assert solution_profiles_from_document_evidence(DocumentEvidenceState()) == []


def test_merge_is_idempotent_on_re_derivation() -> None:
    derived = solution_profiles_from_document_evidence(_datasheet_evidence())
    once = merge_solution_profiles([], derived)
    twice = merge_solution_profiles(once, derived)
    assert [p.solution_id for p in twice] == ["sol_doc_doc_17"]  # no duplicate
    assert twice == once


def test_merge_preserves_curated_profiles() -> None:
    curated = SolutionProfile(
        solution_id="sol_manual", label="Manual", state="selected"
    )
    derived = solution_profiles_from_document_evidence(_datasheet_evidence())
    merged = merge_solution_profiles([curated], derived)
    assert [p.solution_id for p in merged] == ["sol_manual", "sol_doc_doc_17"]


@pytest.mark.asyncio
async def test_post_graph_commit_derives_solution_profile_from_datasheet() -> None:
    result_state = GraphState(document_evidence=_datasheet_evidence())
    persist = AsyncMock()
    with (
        patch(
            "app.agent.api.loaders._load_live_governed_state",
            AsyncMock(return_value=GovernedSessionState()),
        ),
        patch("app.agent.api.loaders._persist_live_governed_state", persist),
    ):
        updated = await _update_governed_state_post_graph(
            current_user=RequestUser(
                user_id="u1",
                username="u1",
                sub="u1",
                roles=["user"],
                scopes=[],
                tenant_id="t1",
            ),
            session_id="case-sol",
            result_state=result_state,
            pre_gate_classification="DOMAIN_INQUIRY",
        )

    assert [p.solution_id for p in updated.solution_profiles] == ["sol_doc_doc_17"]
    field = updated.solution_profiles[0].fields[0]
    assert field.origin == "datasheet_extracted"
    assert field.status == "pending_confirmation"
    persist.assert_awaited_once()
    assert (
        persist.await_args.kwargs["state"].solution_profiles[0].solution_id
        == "sol_doc_doc_17"
    )
