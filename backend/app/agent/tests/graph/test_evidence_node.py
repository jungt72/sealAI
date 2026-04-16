"""
Tests for graph/nodes/evidence_node.py — Phase F-C.1

Key invariants under test:
    1. RAG is NEVER called on raw user text — query is from AssertedState.
    2. No LLM call under any input.
    3. Skip retrieval when AssertedState is empty.
    4. Skip retrieval when tenant_id is missing.
    5. rag_evidence populated on successful retrieval.
    6. Fail-open: rag_evidence stays [] when retrieval raises.
    7. ObservedState, NormalizedState, AssertedState, GovernanceState unchanged.
    8. analysis_cycle unchanged.

Coverage:
    1.  Empty assertions → no retrieval, rag_evidence stays []
    2.  Missing tenant_id → no retrieval, rag_evidence stays []
    3.  Successful retrieval → rag_evidence populated
    4.  Retrieval exception → fail-open, rag_evidence stays []
    5.  Query contains medium value
    6.  Query contains pressure with unit "bar"
    7.  Query contains temperature with unit "°C"
    8.  Query ends with "Dichtung"
    9.  ObservedState unchanged after retrieval
    10. AssertedState unchanged after retrieval
    11. GovernanceState unchanged after retrieval
    12. analysis_cycle unchanged after retrieval
    13. No LLM call (openai never invoked)
    14. Single assertion still triggers retrieval
    15. Cards returned by RAG are stored unchanged in rag_evidence
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.evidence.evidence_query import EvidenceQuery
from app.agent.graph import GraphState
from app.agent.graph.nodes.evidence_node import _build_evidence_query, evidence_node
from app.agent.state.models import AssertedClaim, AssertedState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(
        field_name=field,
        asserted_value=value,
        confidence=confidence,
    )


def _state_with_assertions(tenant_id: str = "tenant_abc", **kwargs) -> GraphState:
    """Build a GraphState with AssertedState populated from kwargs.

    kwargs: field_name → (value, confidence)
    """
    assertions = {
        field: _claim(field, val, conf)
        for field, (val, conf) in kwargs.items()
    }
    asserted = AssertedState(assertions=assertions)
    return GraphState(asserted=asserted, tenant_id=tenant_id)


def _state_with_normalized_and_asserted(tenant_id: str = "tenant_abc", **kwargs) -> GraphState:
    assertions = {
        field: _claim(field, val, conf)
        for field, (val, conf) in kwargs.items()
    }
    return GraphState(
        asserted=AssertedState(assertions=assertions),
        normalized={
            "parameters": {
                field: {
                    "field_name": field,
                    "value": val,
                    "confidence": conf,
                    "source": "llm",
                }
                for field, (val, conf) in kwargs.items()
            }
        },
        tenant_id=tenant_id,
    )


_MOCK_CARDS = [
    {
        "id": "card_1",
        "content": "PTFE eignet sich für Dampf bis 260°C.",
        "retrieval_rank": 0,
        "metadata": {"checksum": "chk-1"},
    },
    {
        "id": "card_2",
        "content": "FKM-Dichtung für Drücke bis 20 bar.",
        "retrieval_rank": 1,
        "metadata": {"doc_version": "v2"},
    },
]


# ---------------------------------------------------------------------------
# 1. Empty assertions → skip retrieval
# ---------------------------------------------------------------------------

class TestEmptyAssertions:
    @pytest.mark.asyncio
    async def test_no_retrieval_called(self):
        state = GraphState(tenant_id="tenant_abc")  # no assertions
        with patch("app.agent.graph.nodes.evidence_node.retrieve_evidence") as mock_rag:
            result = await evidence_node(state)
        mock_rag.assert_not_called()

    @pytest.mark.asyncio
    async def test_rag_evidence_stays_empty(self):
        state = GraphState(tenant_id="tenant_abc")
        result = await evidence_node(state)
        assert result.rag_evidence == []

    @pytest.mark.asyncio
    async def test_state_returned_unchanged(self):
        state = GraphState(tenant_id="tenant_abc")
        result = await evidence_node(state)
        assert result is state


# ---------------------------------------------------------------------------
# 2. Missing tenant_id → skip retrieval
# ---------------------------------------------------------------------------

class TestMissingTenantId:
    @pytest.mark.asyncio
    async def test_no_retrieval_called_when_tenant_missing(self):
        state = _state_with_assertions(
            tenant_id="",  # empty
            medium=("Dampf", "confirmed"),
        )
        with patch("app.agent.graph.nodes.evidence_node.retrieve_evidence") as mock_rag:
            result = await evidence_node(state)
        mock_rag.assert_not_called()

    @pytest.mark.asyncio
    async def test_rag_evidence_stays_empty_without_tenant(self):
        state = _state_with_assertions(
            tenant_id="",
            medium=("Dampf", "confirmed"),
        )
        result = await evidence_node(state)
        assert result.rag_evidence == []


# ---------------------------------------------------------------------------
# 3. Successful retrieval → rag_evidence populated
# ---------------------------------------------------------------------------

class TestSuccessfulRetrieval:
    @pytest.mark.asyncio
    async def test_rag_evidence_populated(self):
        state = _state_with_assertions(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=(
                _MOCK_CARDS,
                {
                    "tier": "tier1_hybrid",
                    "k_requested": 5,
                    "k_returned": 2,
                    "threshold": 0.05,
                    "configured_threshold": 0.05,
                    "threshold_applied": True,
                    "top_scores": [0.91, 0.73],
                },
            ),
        ):
            result = await evidence_node(state)

        assert result.rag_evidence == _MOCK_CARDS
        assert result.evidence.evidence_results == _MOCK_CARDS
        assert result.evidence.source_versions == {"card_1": "chk-1", "card_2": "v2"}
        assert result.evidence.retrieval_query == "Dampf 12.0 bar 180.0 °C Dichtung"
        assert result.rag_evidence_audit["tier"] == "tier1_hybrid"
        assert result.rag_evidence_audit["top_scores"] == [0.91, 0.73]
        assert result.rag_evidence_audit["top_documents"][0]["id"] == "card_1"
        assert result.rag_evidence_audit["event"] == {
            "event_type": "evidence_retrieved",
            "sources_count": 2,
        }

    @pytest.mark.asyncio
    async def test_retrieved_evidence_updates_asserted_refs_when_normalized_available(self):
        state = _state_with_normalized_and_asserted(
            medium=("Dampf", "inferred"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=(
                [{"id": "card-dampf", "content": "Dampf Dichtung", "source_ref": "datasheet:1"}],
                {},
            ),
        ):
            result = await evidence_node(state)

        assert result.asserted.assertions["medium"].confidence == "confirmed"
        assert result.asserted.assertions["medium"].evidence_refs == ["card-dampf"]
        assert result.evidence.source_backed_findings == ["medium"]
        assert result.evidence.evidence_gaps == []

    @pytest.mark.asyncio
    async def test_evidence_gap_keeps_saltwater_medium_unverified(self):
        state = _state_with_normalized_and_asserted(
            medium=("Salzwasser", "confirmed"),
            pressure_bar=(10.0, "confirmed"),
            temperature_c=(80.0, "confirmed"),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=(
                [{"id": "card-other", "content": "RWDR fuer Oel", "source_ref": "datasheet:2"}],
                {},
            ),
        ):
            result = await evidence_node(state)

        assert "missing_source_for_medium" in result.evidence.evidence_gaps
        assert "missing_source_for_medium" in result.evidence.unresolved_open_points

    @pytest.mark.asyncio
    async def test_retrieve_called_with_tenant_id(self):
        state = _state_with_assertions(
            tenant_id="t42",
            medium=("Dampf", "confirmed"),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=([], {"tier": "tier3_empty", "k_requested": 5, "k_returned": 0}),
        ) as mock_rag:
            await evidence_node(state)

        mock_rag.assert_called_once()
        args, kwargs = mock_rag.call_args
        assert isinstance(args[0], EvidenceQuery)
        assert args[0].topic == "Dampf Dichtung"
        assert kwargs.get("tenant_id") == "t42"

    @pytest.mark.asyncio
    async def test_retrieve_called_once(self):
        state = _state_with_assertions(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=(_MOCK_CARDS, {}),
        ) as mock_rag:
            await evidence_node(state)

        assert mock_rag.call_count == 1


# ---------------------------------------------------------------------------
# 4. Retrieval exception → fail-open
# ---------------------------------------------------------------------------

class TestRetrievalFailOpen:
    @pytest.mark.asyncio
    async def test_rag_evidence_stays_empty_on_exception(self):
        state = _state_with_assertions(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Qdrant unavailable"),
        ):
            result = await evidence_node(state)

        assert result.rag_evidence == []
        assert result.evidence.evidence_results == []
        assert result.evidence.source_versions == {}
        assert result.rag_evidence_audit["k_returned"] == 0
        assert "RuntimeError" in result.rag_evidence_audit["error"]
        assert result.rag_evidence_audit["event"] == {
            "event_type": "evidence_retrieved",
            "sources_count": 0,
        }

    @pytest.mark.asyncio
    async def test_state_still_returned_on_exception(self):
        state = _state_with_assertions(
            medium=("Dampf", "confirmed"),
        )
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            side_effect=ConnectionError("network timeout"),
        ):
            result = await evidence_node(state)

        # Node must not raise — result is a valid GraphState
        assert isinstance(result, GraphState)


# ---------------------------------------------------------------------------
# 5–8. Query construction (unit-tested directly)
# ---------------------------------------------------------------------------

class TestQueryConstruction:
    def _asserted(self, **kwargs) -> GraphState:
        return _state_with_assertions(**kwargs)

    def test_query_contains_medium(self):
        state = _state_with_assertions(medium=("Dampf", "confirmed"))
        query = _build_evidence_query(state)
        assert isinstance(query, EvidenceQuery)
        assert "Dampf" in query.topic

    def test_query_contains_pressure_with_unit(self):
        state = _state_with_assertions(pressure_bar=(12.0, "confirmed"))
        query = _build_evidence_query(state)
        assert "12.0" in query.topic
        assert "bar" in query.topic

    def test_query_contains_temperature_with_unit(self):
        state = _state_with_assertions(temperature_c=(180.0, "confirmed"))
        query = _build_evidence_query(state)
        assert "180.0" in query.topic
        assert "°C" in query.topic

    def test_query_ends_with_dichtung(self):
        state = _state_with_assertions(medium=("Wasser", "confirmed"))
        query = _build_evidence_query(state)
        assert query.topic.endswith("Dichtung")

    def test_empty_assertions_returns_none(self):
        state = GraphState(tenant_id="t1")
        query = _build_evidence_query(state)
        assert query is None

    def test_query_is_deterministic(self):
        state = _state_with_assertions(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
        )
        q1 = _build_evidence_query(state)
        q2 = _build_evidence_query(state)
        assert q1 == q2
        assert q1.topic == q2.topic


# ---------------------------------------------------------------------------
# 9–12. Immutability — other state layers unchanged
# ---------------------------------------------------------------------------

class TestImmutability:
    @pytest.mark.asyncio
    async def test_observed_unchanged(self):
        state = _state_with_assertions(medium=("Dampf", "confirmed"))
        original_extractions = list(state.observed.raw_extractions)
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=(_MOCK_CARDS, {}),
        ):
            result = await evidence_node(state)
        assert list(result.observed.raw_extractions) == original_extractions

    @pytest.mark.asyncio
    async def test_asserted_unchanged(self):
        state = _state_with_assertions(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        original_keys = set(state.asserted.assertions.keys())
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=(_MOCK_CARDS, {}),
        ):
            result = await evidence_node(state)
        assert set(result.asserted.assertions.keys()) == original_keys

    @pytest.mark.asyncio
    async def test_governance_unchanged(self):
        state = _state_with_assertions(medium=("Dampf", "confirmed"))
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=([], {}),
        ):
            result = await evidence_node(state)
        assert result.governance.gov_class is None
        assert result.governance.rfq_admissible is False

    @pytest.mark.asyncio
    async def test_analysis_cycle_unchanged(self):
        state = _state_with_assertions(medium=("Dampf", "confirmed"))
        state = state.model_copy(update={"analysis_cycle": 2})
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=([], {}),
        ):
            result = await evidence_node(state)
        assert result.analysis_cycle == 2


# ---------------------------------------------------------------------------
# 13. No LLM call
# ---------------------------------------------------------------------------

class TestNoLLM:
    @pytest.mark.asyncio
    async def test_openai_never_called(self):
        state = _state_with_assertions(
            medium=("Dampf", "confirmed"),
            pressure_bar=(12.0, "confirmed"),
            temperature_c=(180.0, "confirmed"),
        )
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(
                side_effect=AssertionError("LLM must not be called in evidence_node")
            )
            with patch(
                "app.agent.graph.nodes.evidence_node.retrieve_evidence",
                new_callable=AsyncMock,
                return_value=(_MOCK_CARDS, {}),
            ):
                await evidence_node(state)

        mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# 14. Single assertion still triggers retrieval
# ---------------------------------------------------------------------------

class TestSingleAssertion:
    @pytest.mark.asyncio
    async def test_single_assertion_triggers_retrieval(self):
        state = _state_with_assertions(medium=("Öl", "confirmed"))
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=(_MOCK_CARDS, {}),
        ) as mock_rag:
            result = await evidence_node(state)
        mock_rag.assert_called_once()
        assert result.rag_evidence == _MOCK_CARDS


# ---------------------------------------------------------------------------
# 15. Cards stored unchanged
# ---------------------------------------------------------------------------

class TestCardsStoredUnchanged:
    @pytest.mark.asyncio
    async def test_cards_not_modified(self):
        cards = [
            {"id": "x1", "content": "PTFE card", "custom_field": 42},
            {"id": "x2", "content": "FKM card",  "custom_field": 99},
        ]
        state = _state_with_assertions(medium=("Dampf", "confirmed"))
        with patch(
            "app.agent.graph.nodes.evidence_node.retrieve_evidence",
            new_callable=AsyncMock,
            return_value=(cards, {}),
        ):
            result = await evidence_node(state)
        assert result.rag_evidence == cards
        assert result.rag_evidence[0]["custom_field"] == 42
