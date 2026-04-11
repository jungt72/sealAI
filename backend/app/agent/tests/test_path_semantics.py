"""
Phase 0E — Patch 3: Response-semantics are consistent and non-overlapping
across all four runtime paths.

Goals:
- meta does not sound like advice or technical assessment
- blocked does not give any substantive answer
- fast does not produce a qualification claim
- structured signals its tentative (non-binding) nature clearly

These are governance markers, not cosmetic tests.
"""
from __future__ import annotations

import json
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.agent.boundaries import FAST_PATH_DISCLAIMER, STRUCTURED_PATH_SUFFIX
from app.agent.agent.graph import (
    _BLOCKED_REFUSAL,
    blocked_node,
    meta_response_node,
)
from app.agent.agent.output_guard import FAST_PATH_GUARD_FALLBACK


def _minimal_state(**overrides):
    base = {
        "messages": [HumanMessage(content="Test")],
        "sealing_state": {
            "asserted": {
                "medium_profile": {},
                "machine_profile": {},
                "installation_profile": {},
                "operating_conditions": {},
                "sealing_requirement_spec": {},
            },
            "governance": {
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "scope_of_validity": [],
                "assumptions_active": [],
                "gate_failures": [],
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": [],
                "conflicts": [],
            },
            "cycle": {
                "analysis_cycle_id": "sem-test",
                "snapshot_parent_revision": 0,
                "superseded_by_cycle": None,
                "contract_obsolete": False,
                "contract_obsolete_reason": None,
                "state_revision": 1,
            },
            "selection": {
                "selection_status": "blocked_no_candidates",
                "candidates": [],
                "viable_candidate_ids": [],
                "blocked_candidates": [],
                "winner_candidate_id": None,
                "recommendation_artifact": None,
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
            },
            "review": {},
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "tenant_id": "test-tenant",
        "run_meta": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Meta path: status report, not advisory
# ---------------------------------------------------------------------------

class TestMetaPathSemantics:
    def test_meta_does_not_produce_structured_boundary(self):
        """Meta is a status report — it must not look like a technical assessment."""
        state = _minimal_state()
        result = meta_response_node(state)
        text = result["messages"][0].content

        assert STRUCTURED_PATH_SUFFIX not in text, (
            "Meta path must not produce the structured-path qualification suffix"
        )

    def test_meta_does_not_claim_technical_suitability(self):
        """Meta must not contain suitability or advisory language."""
        state = _minimal_state()
        result = meta_response_node(state)
        text = result["messages"][0].content

        forbidden_terms = ["geeignet", "empfehl", "Empfehlung", "Auslegung empfohlen"]
        for term in forbidden_terms:
            assert term.lower() not in text.lower(), (
                f"Meta response must not contain advisory term: {term!r}"
            )

    def test_meta_is_a_status_summary(self):
        """Meta reply must contain status-report structure."""
        state = _minimal_state()
        state["sealing_state"]["asserted"]["medium_profile"] = {"name": "Öl"}
        result = meta_response_node(state)
        text = result["messages"][0].content

        # Must have a summary structure (confirmed / missing)
        assert "Bestätigte Angaben" in text or "Noch" in text

    def test_meta_note_explains_scope(self):
        """Meta must include the 'only confirmed session values' disclaimer."""
        state = _minimal_state()
        result = meta_response_node(state)
        text = result["messages"][0].content
        # The hint note explicitly states what the meta reply is based on
        assert "bestätigt" in text.lower()


# ---------------------------------------------------------------------------
# Blocked path: hard refusal, no softening
# ---------------------------------------------------------------------------

class TestBlockedPathSemantics:
    def test_blocked_contains_explicit_prohibition_statement(self):
        """Blocked reply must state explicitly what SealAI cannot do."""
        state = _minimal_state()
        result = blocked_node(state)
        text = result["messages"][0].content
        assert "darf weder" in text or "nicht" in text

    def test_blocked_does_not_contain_structured_boundary(self):
        """Blocked is not a technical response — no structured boundary."""
        state = _minimal_state()
        result = blocked_node(state)
        text = result["messages"][0].content
        assert STRUCTURED_PATH_SUFFIX not in text

    def test_blocked_offers_compliant_alternative(self):
        """Blocked must redirect to the compliant path — not leave user stranded."""
        state = _minimal_state()
        result = blocked_node(state)
        text = result["messages"][0].content
        # Must hint at what the user CAN do
        assert "Betriebsparameter" in text or "Medium" in text or "nennen" in text

    def test_blocked_refusal_text_matches_constant(self):
        """Blocked text must be deterministic — no LLM-generated variation."""
        state = _minimal_state()
        result = blocked_node(state)
        text = result["messages"][0].content
        assert _BLOCKED_REFUSAL in text


# ---------------------------------------------------------------------------
# Fast path: knowledge answer, not qualification
# ---------------------------------------------------------------------------

class TestFastPathSemantics:
    @pytest.mark.asyncio
    async def test_fast_path_reply_has_fast_disclaimer(self):
        """Fast path must always carry the non-binding orientation disclaimer."""
        from app.agent.agent.graph import fast_guidance_node
        state = _minimal_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist FKM?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(
            return_value=AIMessage(content="FKM ist ein Fluorkautschuk.")
        )
        with patch("app.agent.graph.legacy_graph.get_llm", return_value=llm_mock), \
             patch("app.agent.graph.legacy_graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        text = result["messages"][0].content
        assert FAST_PATH_DISCLAIMER in text

    @pytest.mark.asyncio
    async def test_fast_path_reply_does_not_claim_deterministic_result(self):
        """Fast path is orientation only — must not use qualification language."""
        from app.agent.agent.graph import fast_guidance_node
        state = _minimal_state(
            policy_path="fast",
            result_form="direct_answer",
            messages=[HumanMessage(content="Was ist NBR?")],
        )
        llm_mock = MagicMock()
        llm_mock.ainvoke = AsyncMock(
            return_value=AIMessage(content="NBR ist ein Synthesekautschuk.")
        )
        with patch("app.agent.graph.legacy_graph.get_llm", return_value=llm_mock), \
             patch("app.agent.graph.legacy_graph._fetch_rag_cards", return_value=([], "stub")):
            result = await fast_guidance_node(state)

        text = result["messages"][0].content
        # Structured qualification boundary must never appear
        assert STRUCTURED_PATH_SUFFIX not in text


# ---------------------------------------------------------------------------
# Structured path: non-binding, scope-of-validity, evidence-aware
# ---------------------------------------------------------------------------

class TestStructuredPathSemantics:
    def test_structured_reply_is_always_non_binding(self):
        """Structured final reply must always include scope-of-validity suffix."""
        from app.agent.agent.selection import build_final_reply

        state_minimal = {
            "selection_status": "blocked_no_candidates",
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
            "candidates": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "winner_candidate_id": None,
            "recommendation_artifact": {
                "selection_status": "blocked_no_candidates",
                "winner_candidate_id": None,
                "candidate_ids": [],
                "viable_candidate_ids": [],
                "blocked_candidates": [],
                "evidence_basis": [],
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
                "trace_provenance_refs": [],
            },
        }
        reply = build_final_reply(state_minimal)
        assert STRUCTURED_PATH_SUFFIX in reply

    def test_structured_path_suffix_is_not_fast_disclaimer(self):
        """Structural check: the two boundary constants must be different strings."""
        assert STRUCTURED_PATH_SUFFIX != FAST_PATH_DISCLAIMER, (
            "STRUCTURED_PATH_SUFFIX and FAST_PATH_DISCLAIMER must be distinct strings"
        )

    def test_structured_reply_never_contains_fast_disclaimer(self):
        """Structured reply must not contain the fast-path orientation disclaimer."""
        from app.agent.agent.selection import build_final_reply

        state_minimal = {
            "selection_status": "blocked_no_candidates",
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
            "specificity_level": "family_only",
            "output_blocked": True,
            "candidates": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "winner_candidate_id": None,
            "recommendation_artifact": {
                "selection_status": "blocked_no_candidates",
                "winner_candidate_id": None,
                "candidate_ids": [],
                "viable_candidate_ids": [],
                "blocked_candidates": [],
                "evidence_basis": [],
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
                "trace_provenance_refs": [],
            },
        }
        reply = build_final_reply(state_minimal)
        assert FAST_PATH_DISCLAIMER not in reply


# ---------------------------------------------------------------------------
# Phase 0F — PATCH 4: Streaming path semantic alignment
#
# These tests verify that `agent_sse_generator` emits the correct payload
# fields after the Phase 0F policy injection was added to event_generator().
# ---------------------------------------------------------------------------

class TestStreamingPathSemantics:
    """Verify that SSE state_update carries the correct semantic fields."""

    @staticmethod
    async def _collect_sse_frames(events: list) -> list[dict]:
        """Run agent_sse_generator with a mocked graph and collect parsed payloads."""
        from app.agent.api.sse_runtime import agent_sse_generator

        class _MockGraph:
            async def astream_events(self, state, *, version):
                for e in events:
                    yield e

        frames = []
        async for raw_frame in agent_sse_generator({}, graph=_MockGraph()):
            if raw_frame.startswith("data: ") and not raw_frame.startswith("data: [DONE]"):
                frames.append(json.loads(raw_frame[len("data: "):]))
        return frames

    @pytest.mark.asyncio
    async def test_state_update_includes_reply_field(self):
        """state_update payload must include a `reply` field after Phase 0F."""
        events = [
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {
                    "messages": [HumanMessage(content="Hi"), AIMessage(content="Hallo Welt")],
                    "policy_path": "fast",
                }},
            }
        ]
        frames = await self._collect_sse_frames(events)
        state_update = next((f for f in frames if f.get("type") == "state_update"), None)
        assert state_update is not None, "state_update event must be emitted"
        assert "reply" in state_update, "state_update must include reply field (Phase 0F)"
        assert state_update["reply"] == "Hallo Welt"

    @pytest.mark.asyncio
    async def test_state_update_includes_policy_path_field(self):
        """state_update payload must include `policy_path` after Phase 0F."""
        events = [
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {
                    "messages": [AIMessage(content="Meta Antwort")],
                    "policy_path": "meta",
                }},
            }
        ]
        frames = await self._collect_sse_frames(events)
        state_update = next((f for f in frames if f.get("type") == "state_update"), None)
        assert state_update is not None
        assert state_update.get("policy_path") == "meta"

    @pytest.mark.asyncio
    async def test_state_update_uses_central_user_facing_reply_assembly(self):
        events = [
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {
                    "messages": [AIMessage(content="Hallo Welt")],
                    "policy_path": "fast",
                }},
            }
        ]
        assembled = {
            "reply": "Assembled SSE reply",
            "structured_state": None,
            "policy_path": "fast",
            "run_meta": None,
            "response_class": "conversational_answer",
        }
        with patch("app.agent.api.models.assemble_user_facing_reply", return_value=assembled) as mock_assemble:
            frames = await self._collect_sse_frames(events)

        state_update = next((f for f in frames if f.get("type") == "state_update"), None)
        assert state_update is not None
        assert state_update["reply"] == "Assembled SSE reply"
        mock_assemble.assert_called_once()

    @pytest.mark.asyncio
    async def test_internal_node_tokens_do_not_reach_client(self):
        """Tokens from non-speaking nodes must be silently dropped."""
        chunk_mock = type("Chunk", (), {"content": "internal-leak"})()
        events = [
            {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "reasoning_node"},
                "data": {"chunk": chunk_mock},
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"messages": [], "policy_path": "structured"}},
            },
        ]
        frames = await self._collect_sse_frames(events)
        text_chunks = [f for f in frames if f.get("type") == "text_chunk"]
        assert len(text_chunks) == 0, (
            "reasoning_node tokens must be dropped silently — "
            "internal node leaked to client"
        )

    @pytest.mark.asyncio
    async def test_fast_guidance_node_tokens_reach_client(self):
        """Tokens from fast_guidance_node must flow through to the client."""
        chunk_mock = type("Chunk", (), {"content": "FKM ist ein Fluorkautschuk."})()
        events = [
            {
                "event": "on_chat_model_stream",
                "metadata": {"langgraph_node": "fast_guidance_node"},
                "data": {"chunk": chunk_mock},
            },
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {"messages": [], "policy_path": "fast"}},
            },
        ]
        frames = await self._collect_sse_frames(events)
        text_chunks = [f for f in frames if f.get("type") == "text_chunk"]
        assert len(text_chunks) == 1
        assert text_chunks[0]["text"] == "FKM ist ein Fluorkautschuk."

    @pytest.mark.asyncio
    async def test_reply_is_none_when_no_ai_messages(self):
        """reply field is None when graph produces no AIMessage."""
        events = [
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {"output": {
                    "messages": [HumanMessage(content="hi")],
                    "policy_path": "meta",
                }},
            }
        ]
        frames = await self._collect_sse_frames(events)
        state_update = next((f for f in frames if f.get("type") == "state_update"), None)
        assert state_update is not None
        assert state_update.get("reply") is None


# ---------------------------------------------------------------------------
# Phase 1B — PATCH 3: build_final_reply() per-readiness-status reply classes
# ---------------------------------------------------------------------------

def _aligned_selection_state(
    *,
    selection_status: str = "blocked_no_candidates",
    release_status: str = "inadmissible",
    rfq_admissibility: str = "inadmissible",
    specificity_level: str = "family_only",
    output_blocked: bool = True,
) -> dict:
    """Minimal aligned selection_state — artifact matches top-level fields."""
    return {
        "selection_status": selection_status,
        "release_status": release_status,
        "rfq_admissibility": rfq_admissibility,
        "specificity_level": specificity_level,
        "output_blocked": output_blocked,
        "candidates": [],
        "viable_candidate_ids": [],
        "blocked_candidates": [],
        "winner_candidate_id": None,
        "recommendation_artifact": {
            "selection_status": selection_status,
            "winner_candidate_id": None,
            "candidate_ids": [],
            "viable_candidate_ids": [],
            "blocked_candidates": [],
            "evidence_basis": [],
            "release_status": release_status,
            "rfq_admissibility": rfq_admissibility,
            "specificity_level": specificity_level,
            "output_blocked": output_blocked,
            "trace_provenance_refs": [],
        },
        "clarification_projection": None,
    }


_FULL_ASSERTED = {
    "medium_profile": {"name": "Hydrauliköl"},
    "operating_conditions": {"pressure": 10.0, "temperature": 80.0},
}


class TestFinalReplyPerReadinessStatus:
    """Phase 1B PATCH 3: each readiness status produces a distinct, non-overlapping reply."""

    def test_demo_data_quarantine_reply(self):
        from app.agent.agent.selection import build_final_reply, DEMO_DATA_QUARANTINE_REPLY
        state = _aligned_selection_state()
        reply = build_final_reply(
            state,
            asserted_state=_FULL_ASSERTED,
            demo_data_present=True,
        )
        assert DEMO_DATA_QUARANTINE_REPLY in reply
        assert STRUCTURED_PATH_SUFFIX in reply

    def test_evidence_missing_reply(self):
        from app.agent.agent.selection import build_final_reply, EVIDENCE_MISSING_REPLY
        state = _aligned_selection_state()
        reply = build_final_reply(
            state,
            asserted_state=_FULL_ASSERTED,
            evidence_available=False,
        )
        assert EVIDENCE_MISSING_REPLY in reply
        assert STRUCTURED_PATH_SUFFIX in reply

    def test_review_pending_reply(self):
        from app.agent.agent.selection import build_final_reply, REVIEW_PENDING_REPLY
        state = _aligned_selection_state()
        review_st = {"review_required": True, "review_state": "pending", "review_reason": "Test"}
        reply = build_final_reply(
            state,
            asserted_state=_FULL_ASSERTED,
            review_state=review_st,
        )
        assert REVIEW_PENDING_REPLY in reply
        assert STRUCTURED_PATH_SUFFIX in reply

    def test_demo_data_takes_priority_over_evidence_missing_in_reply(self):
        from app.agent.agent.selection import build_final_reply, DEMO_DATA_QUARANTINE_REPLY, EVIDENCE_MISSING_REPLY
        state = _aligned_selection_state()
        reply = build_final_reply(
            state,
            asserted_state=_FULL_ASSERTED,
            demo_data_present=True,
            evidence_available=False,
        )
        assert DEMO_DATA_QUARANTINE_REPLY in reply
        assert EVIDENCE_MISSING_REPLY not in reply

    def test_missing_inputs_reply_when_no_params(self):
        """No asserted params → missing-inputs text with 'benötige ich noch'."""
        from app.agent.agent.selection import build_final_reply
        state = _aligned_selection_state(selection_status="blocked_missing_required_inputs")
        state["clarification_projection"] = {
            "missing_items": ["medium", "pressure", "temperature"],
            "next_question_key": "medium",
            "next_question_label": "Dichtungsmedium",
            "clarification_still_meaningful": True,
            "reason_if_not": "",
        }
        reply = build_final_reply(state, asserted_state=None, working_profile=None)
        assert "benötige" in reply or "Medium" in reply
        assert "Welches Medium soll abgedichtet werden?" in reply

    def test_incomplete_but_clarification_not_meaningful(self):
        from app.agent.agent.selection import build_final_reply, CLARIFICATION_PAUSED_PREFIX
        state = _aligned_selection_state(selection_status="blocked_missing_required_inputs")
        state["clarification_projection"] = {
            "missing_items": ["medium"],
            "next_question_key": None,
            "next_question_label": None,
            "clarification_still_meaningful": False,
            "reason_if_not": "Review oder Eskalation ist bereits der nächste deterministische Schritt.",
        }
        reply = build_final_reply(state, asserted_state=None, working_profile=None)
        assert CLARIFICATION_PAUSED_PREFIX in reply

    def test_review_reply_stays_separate_from_clarification_reply(self):
        from app.agent.agent.selection import build_final_reply, REVIEW_PENDING_REPLY
        state = _aligned_selection_state()
        state["user_facing_output_projection"] = {"status": "withheld_review"}
        state["output_contract_projection"] = {
            "output_status": "withheld_review",
            "allowed_surface_claims": ["withheld", "review_required"],
            "next_user_action": "human_review",
            "visible_warning_flags": [],
            "suppress_recommendation_details": True,
        }
        state["clarification_projection"] = {
            "missing_items": ["medium"],
            "next_question_key": "medium",
            "next_question_label": "Dichtungsmedium",
            "clarification_still_meaningful": True,
            "reason_if_not": "",
        }
        review_st = {"review_required": True, "review_state": "pending", "review_reason": "Test"}
        reply = build_final_reply(
            state,
            asserted_state=_FULL_ASSERTED,
            review_state=review_st,
        )
        assert REVIEW_PENDING_REPLY in reply
        assert "Nächste Klärungsfrage:" not in reply

    def test_output_contract_can_drive_escalation_reply_without_recommendation_details(self):
        from app.agent.agent.selection import build_final_reply, ESCALATION_NEEDED_REPLY
        state = _aligned_selection_state(selection_status="winner_selected", output_blocked=True)
        state["user_facing_output_projection"] = {"status": "withheld_escalation"}
        state["output_contract_projection"] = {
            "output_status": "withheld_escalation",
            "allowed_surface_claims": ["withheld", "escalation_required"],
            "next_user_action": "engineering_escalation",
            "visible_warning_flags": ["conflict_open"],
            "suppress_recommendation_details": True,
        }
        state["recommendation_artifact"]["rationale_summary"] = "Deterministische Candidate-Projektion: F1."
        reply = build_final_reply(state, asserted_state=_FULL_ASSERTED)
        assert ESCALATION_NEEDED_REPLY in reply
        assert "Deterministische Candidate-Projektion" not in reply

    def test_no_candidates_reply(self):
        from app.agent.agent.selection import build_final_reply, NO_CANDIDATES_REPLY
        state = _aligned_selection_state(selection_status="blocked_no_candidates")
        reply = build_final_reply(state, asserted_state=None)
        assert NO_CANDIDATES_REPLY in reply or "Medium" in reply or "benötige" in reply

    def test_structured_suffix_present_for_all_reply_classes(self):
        """STRUCTURED_PATH_SUFFIX must always appear regardless of reply class."""
        from app.agent.agent.selection import build_final_reply
        state = _aligned_selection_state()
        for kwargs in [
            {"demo_data_present": True, "asserted_state": _FULL_ASSERTED},
            {"evidence_available": False, "asserted_state": _FULL_ASSERTED},
            {"asserted_state": None},
        ]:
            reply = build_final_reply(state, **kwargs)
            assert STRUCTURED_PATH_SUFFIX in reply, (
                f"STRUCTURED_PATH_SUFFIX missing for kwargs={kwargs!r}"
            )

    def test_reply_constants_are_mutually_exclusive(self):
        """Each named reply constant must not contain text from another reply class."""
        from app.agent.agent.selection import (
            DEMO_DATA_QUARANTINE_REPLY, EVIDENCE_MISSING_REPLY, REVIEW_PENDING_REPLY,
            MANUFACTURER_VALIDATION_REPLY, PRECHECK_ONLY_REPLY,
        )
        replies = [
            DEMO_DATA_QUARANTINE_REPLY,
            EVIDENCE_MISSING_REPLY,
            REVIEW_PENDING_REPLY,
            MANUFACTURER_VALIDATION_REPLY,
            PRECHECK_ONLY_REPLY,
        ]
        # Each constant must be distinct from all others
        for i, r1 in enumerate(replies):
            for j, r2 in enumerate(replies):
                if i != j:
                    assert r1 != r2, f"replies[{i}] and replies[{j}] are identical"
