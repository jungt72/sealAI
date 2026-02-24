import os
import sys
import types

from langchain_core.messages import HumanMessage
from langgraph.types import Command, Send

os.environ.setdefault("POSTGRES_USER", "sealai")
os.environ.setdefault("POSTGRES_PASSWORD", "secret")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "sealai")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sealai:secret@localhost:5432/sealai")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://sealai:secret@localhost:5432/sealai")
os.environ.setdefault("POSTGRES_DSN", "postgresql://sealai:secret@localhost:5432/sealai")
os.environ.setdefault("postgres_dsn", "postgresql://sealai:secret@localhost:5432/sealai")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_COLLECTION", "sealai")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEXTAUTH_URL", "http://localhost:3000")
os.environ.setdefault("NEXTAUTH_SECRET", "dummy-secret")
os.environ.setdefault("KEYCLOAK_ISSUER", "http://localhost:8080/realms/test")
os.environ.setdefault("KEYCLOAK_JWKS_URL", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "sealai-backend")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "client-secret")
os.environ.setdefault("KEYCLOAK_EXPECTED_AZP", "sealai-frontend")

if "psycopg_pool" not in sys.modules:
    psycopg_pool_stub = types.ModuleType("psycopg_pool")

    class _StubAsyncConnectionPool:
        def __init__(self, *args, **kwargs):
            pass

    psycopg_pool_stub.AsyncConnectionPool = _StubAsyncConnectionPool
    sys.modules["psycopg_pool"] = psycopg_pool_stub

from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node
from app.langgraph_v2.nodes.reducer import reducer_node
from app.langgraph_v2.sealai_graph_v2 import discover_mcp_tools_for_state
from app.langgraph_v2.state import Intent, SealAIState, WorkingMemory
import app.langgraph_v2.nodes.nodes_flows as nodes_flows


def test_graph_discovers_mcp_knowledge_tool_from_scopes() -> None:
    scoped_state = SealAIState(user_context={"auth_scopes": ["openid", "mcp:knowledge:read"]})
    tools = discover_mcp_tools_for_state(scoped_state)
    assert any(tool.get("name") == "search_technical_docs" for tool in tools)
    assert any(tool.get("name") == "get_available_filters" for tool in tools)

    unscoped_state = SealAIState(user_context={"auth_scopes": ["openid"]})
    assert discover_mcp_tools_for_state(unscoped_state) == []


def test_supervisor_routes_material_doc_queries_via_send_to_material_agent() -> None:
    state = SealAIState(
        intent=Intent(goal="design_recommendation"),
        messages=[HumanMessage(content="Please fetch the NBR-90 data sheet.")],
    )
    command = supervisor_policy_node(state)
    assert isinstance(command, Command)
    assert isinstance(command.goto, list)
    assert any(isinstance(target, Send) and target.node == "material_agent" for target in command.goto)


def test_supervisor_routes_explicit_knowledge_lookup_even_for_smalltalk_goal() -> None:
    state = SealAIState(
        intent=Intent(goal="smalltalk"),
        messages=[
            HumanMessage(
                content="Nutze get_available_filters und suche dann mit trade_name 'Kyrolon 79X' in Qdrant."
            )
        ],
    )
    command = supervisor_policy_node(state)
    assert isinstance(command, Command)
    assert isinstance(command.goto, list)
    assert any(isinstance(target, Send) and target.node == "material_agent" for target in command.goto)


def test_reducer_merges_rag_context_from_parallel_results() -> None:
    state = SealAIState(
        working_memory=WorkingMemory(panel_material={"reducer_context": "existing context"}),
    )
    results = [
        {
            "retrieval_meta": {"k_returned": 2, "collection": "sealai-docs"},
            "working_memory": {
                "panel_material": {
                    "rag_context": "[1] NBR-90 datasheet snippet",
                }
            },
        }
    ]

    patch = reducer_node(state, results=results)
    wm = patch["working_memory"]
    assert isinstance(wm, WorkingMemory)
    merged_context = str(wm.panel_material.get("reducer_context") or "")
    assert "existing context" in merged_context
    assert "NBR-90 datasheet snippet" in merged_context
    assert patch["retrieval_meta"]["reducer"]["count"] == 1
    assert "existing context" in str(patch.get("context") or "")
    assert "NBR-90 datasheet snippet" in str(patch.get("context") or "")


def test_panel_material_node_preserves_rag_context(monkeypatch) -> None:
    from app.langgraph_v2.nodes.nodes_supervisor import panel_material_node

    def _fake_material_agent_node(state, *_args, **_kwargs):  # noqa: ANN001, ARG001
        return {
            "material_choice": {"material": "PTFE"},
            "working_memory": WorkingMemory(
                material_candidates=[{"name": "PTFE"}],
                panel_material={
                    "rag_context": "Kyrolon facts from RAG",
                    "technical_docs": [{"source": "kyrolon.pdf"}],
                },
            ),
            "context": "Kyrolon facts from RAG",
        }

    monkeypatch.setattr(nodes_flows, "material_agent_node", _fake_material_agent_node)
    patch = panel_material_node(SealAIState())
    panel_material = patch["working_memory"].panel_material
    assert panel_material.get("rag_context") == "Kyrolon facts from RAG"
    assert panel_material.get("technical_docs")
    assert patch.get("context") == "Kyrolon facts from RAG"
