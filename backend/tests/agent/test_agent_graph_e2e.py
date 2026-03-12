import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.agent.graph import app, final_response_node, reasoning_node, router, selection_node
from app.agent.cli import create_initial_state


def test_graph_can_end_only_after_final_response_node():
    graph = app.get_graph()
    edge_pairs = {(edge.source, edge.target) for edge in graph.edges}

    assert ("selection_node", "final_response_node") in edge_pairs
    assert ("final_response_node", "__end__") in edge_pairs
    assert ("reasoning_node", "__end__") not in edge_pairs


def test_selection_node_writes_artifact_before_final_response():
    state = {
        "sealing_state": create_initial_state(),
        "relevant_fact_cards": [
            {
                "evidence_id": "fc-1",
                "source_ref": "doc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "retrieval_score": 0.95,
                "metadata": {},
            }
        ],
    }
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["governance"]["specificity_level"] = "compound_required"
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0}

    selection_result = selection_node(state)
    assert selection_result["sealing_state"]["selection"]["recommendation_artifact"] is not None

    response_result = final_response_node(selection_result)
    assert response_result["messages"][0].content == (
        "Technischer Eignungsraum vorbereitet. Freigabe bleibt an Governance, "
        "Scope-of-validity und dokumentierte Open Points gebunden."
    )


def test_selection_node_withholds_release_when_critical_conflict_exists():
    state = {
        "sealing_state": create_initial_state(),
        "relevant_fact_cards": [
            {
                "evidence_id": "fc-1",
                "source_ref": "doc-1",
                "topic": "PTFE",
                "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
                "retrieval_rank": 1,
                "retrieval_score": 0.95,
                "metadata": {},
            }
        ],
    }
    state["sealing_state"]["governance"]["conflicts"] = [{"severity": "CRITICAL"}]
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0}
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0}

    selection_result = selection_node(state)
    selection = selection_result["sealing_state"]["selection"]
    assert selection["winner_candidate_id"] == "ptfe"
    assert selection["release_status"] == "inadmissible"

    response_result = final_response_node(selection_result)
    assert response_result["messages"][0].content == "No governed recommendation can be released."


def test_runtime_node_flow_routes_through_selection_and_final_response():
    state = {
        "messages": [HumanMessage(content="Ich brauche PTFE fuer eine Dichtung")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
        "tenant_id": "tenant-test",
    }
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["governance"]["specificity_level"] = "compound_required"
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0}

    class StubLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return AIMessage(content="Intake complete.", tool_calls=[])

    mock_cards = [
        SimpleNamespace(
            id="fc-1",
            evidence_id="fc-1",
            source_ref="doc-1",
            topic="PTFE",
            content="PTFE hat ein Temperaturlimit von max. 260 C.",
            tags=["ptfe"],
            retrieval_rank=1,
            retrieval_score=0.95,
            metadata={},
        )
    ]

    async def run_flow():
        with patch("app.agent.agent.graph.get_llm", return_value=StubLLM()), patch(
            "app.agent.agent.graph.retrieve_rag_context",
            new=AsyncMock(return_value=mock_cards),
        ):
            reasoning_output = await reasoning_node(state)
            merged_state = dict(state)
            merged_state["messages"] = state["messages"] + reasoning_output["messages"]
            merged_state["relevant_fact_cards"] = reasoning_output["relevant_fact_cards"]
            merged_state["working_profile"] = reasoning_output["working_profile"]
            assert router(merged_state) == "selection_node"
            selection_output = selection_node(merged_state)
            merged_state["sealing_state"] = selection_output["sealing_state"]
            final_output = final_response_node(merged_state)
            merged_state["messages"] = merged_state["messages"] + final_output["messages"]
            return merged_state

    output = asyncio.run(run_flow())

    assert len(output["messages"]) == 3
    assert output["messages"][1].content == "Intake complete."
    assert output["messages"][2].content == (
        "Technischer Eignungsraum vorbereitet. Freigabe bleibt an Governance, "
        "Scope-of-validity und dokumentierte Open Points gebunden."
    )
    selection = output["sealing_state"]["selection"]
    assert selection["winner_candidate_id"] == "ptfe"
    assert selection["release_status"] == "rfq_ready"
    assert selection["recommendation_artifact"]["release_status"] == "rfq_ready"


def test_runtime_node_flow_withholds_when_governance_blocks():
    state = {
        "messages": [HumanMessage(content="Ich brauche PTFE fuer eine Dichtung")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
        "tenant_id": "tenant-test",
    }
    state["sealing_state"]["governance"]["conflicts"] = [{"severity": "CRITICAL"}]
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0}

    class StubLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return AIMessage(content="Intake complete.", tool_calls=[])

    mock_cards = [
        SimpleNamespace(
            id="fc-1",
            evidence_id="fc-1",
            source_ref="doc-1",
            topic="PTFE",
            content="PTFE hat ein Temperaturlimit von max. 260 C.",
            tags=["ptfe"],
            retrieval_rank=1,
            retrieval_score=0.95,
            metadata={},
        )
    ]

    async def run_flow():
        with patch("app.agent.agent.graph.get_llm", return_value=StubLLM()), patch(
            "app.agent.agent.graph.retrieve_rag_context",
            new=AsyncMock(return_value=mock_cards),
        ):
            reasoning_output = await reasoning_node(state)
            merged_state = dict(state)
            merged_state["messages"] = state["messages"] + reasoning_output["messages"]
            merged_state["relevant_fact_cards"] = reasoning_output["relevant_fact_cards"]
            merged_state["working_profile"] = reasoning_output["working_profile"]
            assert router(merged_state) == "selection_node"
            selection_output = selection_node(merged_state)
            merged_state["sealing_state"] = selection_output["sealing_state"]
            final_output = final_response_node(merged_state)
            merged_state["messages"] = merged_state["messages"] + final_output["messages"]
            return merged_state

    output = asyncio.run(run_flow())

    assert len(output["messages"]) == 3
    assert output["messages"][1].content == "Intake complete."
    assert output["messages"][2].content == "No governed recommendation can be released."
    selection = output["sealing_state"]["selection"]
    assert selection["winner_candidate_id"] == "ptfe"
    assert selection["release_status"] == "inadmissible"


def test_runtime_node_flow_keeps_contract_evidence_visible_for_ready_path():
    state = {
        "messages": [HumanMessage(content="Ich brauche PTFE Grade G461 fuer Wasser bei 120 C")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
        "tenant_id": "tenant-test",
    }

    class StubLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return AIMessage(
                content="Intake complete.",
                tool_calls=[
                    {
                        "name": "submit_claim",
                            "args": {
                                "claim_type": "fact_observed",
                                "statement": "Material ist PTFE, Grade G461, Hersteller Acme. Medium ist Wasser. Temperatur ist 120 C.",
                                "confidence": 1.0,
                                "source_fact_ids": ["fc-ready"],
                            },
                        "id": "call-ready",
                    }
                ],
            )

    mock_cards = [
        SimpleNamespace(
            id="fc-ready",
            evidence_id="fc-ready",
            source_ref="SRC-G461",
            source="SRC-G461",
            source_type="manufacturer_datasheet",
            source_rank=1,
            topic="Acme G461",
            content="PTFE grade G461 fuer Acme.",
            tags=["ptfe", "g461"],
            retrieval_rank=1,
            retrieval_score=0.99,
            metadata={
                "material_family": "PTFE",
                "grade_name": "G461",
                "manufacturer_name": "Acme",
                "product_line": "G-Series",
                "revision_date": "2024-01-15",
                "document_revision": "Rev. 3",
                "temperature_max_c": 260,
                "evidence_scope": ["grade_identity", "temperature_limit"],
            },
            normalized_evidence=None,
        )
    ]

    async def run_flow():
        with patch("app.agent.agent.graph.get_llm", return_value=StubLLM()), patch(
            "app.agent.agent.graph.retrieve_rag_context",
            new=AsyncMock(return_value=mock_cards),
        ):
            reasoning_output = await reasoning_node(state)
            merged_state = dict(state)
            merged_state["messages"] = state["messages"] + reasoning_output["messages"]
            merged_state["relevant_fact_cards"] = reasoning_output["relevant_fact_cards"]
            merged_state["working_profile"] = reasoning_output["working_profile"]
            assert router(merged_state) == "evidence_tool_node"
            from app.agent.agent.graph import evidence_tool_node

            tool_output = evidence_tool_node(merged_state)
            merged_state["messages"] = merged_state["messages"] + tool_output["messages"]
            merged_state["sealing_state"] = tool_output["sealing_state"]
            selection_output = selection_node(merged_state)
            merged_state["sealing_state"] = selection_output["sealing_state"]
            final_output = final_response_node(merged_state)
            merged_state["messages"] = merged_state["messages"] + final_output["messages"]
            return merged_state

    output = asyncio.run(run_flow())

    assert output["sealing_state"]["governance"]["release_status"] == "rfq_ready"
    assert output["sealing_state"]["relevant_evidence"][0]["normalized_evidence"]["datasheet_contract"]["selection_readiness"]["rfq_ready_eligible"] is True
    assert output["messages"][-1].content == (
        "Technischer Eignungsraum vorbereitet. Freigabe bleibt an Governance, "
        "Scope-of-validity und dokumentierte Open Points gebunden."
    )


def test_runtime_node_flow_withholds_when_required_inputs_missing():
    state = {
        "messages": [HumanMessage(content="Ich brauche PTFE fuer eine Dichtung")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
        "tenant_id": "tenant-test",
    }
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"

    class StubLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return AIMessage(content="Intake complete.", tool_calls=[])

    mock_cards = [
        SimpleNamespace(
            id="fc-1",
            evidence_id="fc-1",
            source_ref="doc-1",
            topic="PTFE",
            content="PTFE hat ein Temperaturlimit von max. 260 C.",
            tags=["ptfe"],
            retrieval_rank=1,
            retrieval_score=0.95,
            metadata={},
        )
    ]

    async def run_flow():
        with patch("app.agent.agent.graph.get_llm", return_value=StubLLM()), patch(
            "app.agent.agent.graph.retrieve_rag_context",
            new=AsyncMock(return_value=mock_cards),
        ):
            reasoning_output = await reasoning_node(state)
            merged_state = dict(state)
            merged_state["messages"] = state["messages"] + reasoning_output["messages"]
            merged_state["relevant_fact_cards"] = reasoning_output["relevant_fact_cards"]
            merged_state["working_profile"] = reasoning_output["working_profile"]
            assert router(merged_state) == "selection_node"
            selection_output = selection_node(merged_state)
            merged_state["sealing_state"] = selection_output["sealing_state"]
            final_output = final_response_node(merged_state)
            merged_state["messages"] = merged_state["messages"] + final_output["messages"]
            return merged_state

    output = asyncio.run(run_flow())

    assert output["messages"][2].content == "No governed recommendation can be released because required engineering inputs are missing."
    selection = output["sealing_state"]["selection"]
    assert selection["selection_status"] == "blocked_missing_required_inputs"
    assert selection["release_status"] == "rfq_ready"


def test_runtime_node_flow_withholds_when_no_viable_candidates_remain():
    state = {
        "messages": [HumanMessage(content="Ich brauche PTFE fuer eine Dichtung")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
        "tenant_id": "tenant-test",
    }
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 300.0}

    class StubLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return AIMessage(content="Intake complete.", tool_calls=[])

    mock_cards = [
        SimpleNamespace(
            id="fc-1",
            evidence_id="fc-1",
            source_ref="doc-1",
            topic="PTFE",
            content="PTFE hat ein Temperaturlimit von max. 260 C.",
            tags=["ptfe"],
            retrieval_rank=1,
            retrieval_score=0.95,
            metadata={},
        )
    ]

    async def run_flow():
        with patch("app.agent.agent.graph.get_llm", return_value=StubLLM()), patch(
            "app.agent.agent.graph.retrieve_rag_context",
            new=AsyncMock(return_value=mock_cards),
        ):
            reasoning_output = await reasoning_node(state)
            merged_state = dict(state)
            merged_state["messages"] = state["messages"] + reasoning_output["messages"]
            merged_state["relevant_fact_cards"] = reasoning_output["relevant_fact_cards"]
            merged_state["working_profile"] = reasoning_output["working_profile"]
            assert router(merged_state) == "selection_node"
            selection_output = selection_node(merged_state)
            merged_state["sealing_state"] = selection_output["sealing_state"]
            final_output = final_response_node(merged_state)
            merged_state["messages"] = merged_state["messages"] + final_output["messages"]
            return merged_state

    output = asyncio.run(run_flow())

    assert output["messages"][2].content == "No governed recommendation can be released because no viable candidate remains after deterministic checks."
    selection = output["sealing_state"]["selection"]
    assert selection["selection_status"] == "blocked_no_viable_candidates"
    assert selection["winner_candidate_id"] is None
    assert selection["release_status"] == "rfq_ready"


def test_runtime_node_flow_withholds_when_pressure_conflict_blocks_candidate():
    state = {
        "messages": [HumanMessage(content="Ich brauche PTFE fuer eine Dichtung")],
        "sealing_state": create_initial_state(),
        "working_profile": {},
        "tenant_id": "tenant-test",
    }
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["asserted"]["operating_conditions"] = {"temperature": 200.0, "pressure": 80.0}

    class StubLLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages):
            return AIMessage(content="Intake complete.", tool_calls=[])

    mock_cards = [
        SimpleNamespace(
            id="fc-1",
            evidence_id="fc-1",
            source_ref="doc-1",
            topic="PTFE",
            content="PTFE hat ein Temperaturlimit von max. 260 C und einen maximalen Druck von 50 bar.",
            tags=["ptfe"],
            retrieval_rank=1,
            retrieval_score=0.95,
            metadata={},
        )
    ]

    async def run_flow():
        with patch("app.agent.agent.graph.get_llm", return_value=StubLLM()), patch(
            "app.agent.agent.graph.retrieve_rag_context",
            new=AsyncMock(return_value=mock_cards),
        ):
            reasoning_output = await reasoning_node(state)
            merged_state = dict(state)
            merged_state["messages"] = state["messages"] + reasoning_output["messages"]
            merged_state["relevant_fact_cards"] = reasoning_output["relevant_fact_cards"]
            merged_state["working_profile"] = reasoning_output["working_profile"]
            assert router(merged_state) == "selection_node"
            selection_output = selection_node(merged_state)
            merged_state["sealing_state"] = selection_output["sealing_state"]
            final_output = final_response_node(merged_state)
            merged_state["messages"] = merged_state["messages"] + final_output["messages"]
            return merged_state

    output = asyncio.run(run_flow())

    assert output["messages"][2].content == "No governed recommendation can be released because no viable candidate remains after deterministic checks."
    selection = output["sealing_state"]["selection"]
    assert selection["selection_status"] == "blocked_no_viable_candidates"
    assert selection["winner_candidate_id"] is None
    assert selection["blocked_candidates"][0]["block_reason"] == "blocked_pressure_conflict"
