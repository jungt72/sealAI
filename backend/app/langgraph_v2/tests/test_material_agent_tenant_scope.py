from langchain_core.messages import HumanMessage

import app.langgraph_v2.nodes.nodes_flows as nf
from app.langgraph_v2.nodes.nodes_flows import material_agent_node
from app.langgraph_v2.state.sealai_state import SealAIState


def test_material_agent_node_tries_user_then_shared_tenant(monkeypatch):
    search_calls: list[str | None] = []

    def _fake_get_available_filters(*, tenant_id=None, max_points=2000, collection_name=None):  # noqa: ARG001
        return {"filters": ["additional_metadata.trade_name"]}

    def _fake_search_technical_docs(query, material_code=None, *, tenant_id=None, k=5, metadata_filters=None):  # noqa: ARG001
        search_calls.append(tenant_id)
        if tenant_id == "sealai":
            return {
                "hits": [
                    {
                        "source": "ptfe.pdf",
                        "document_id": "doc-ptfe",
                        "score": 0.91,
                        "snippet": "PTFE datasheet context",
                    }
                ],
                "context": "PTFE datasheet context",
                "retrieval_meta": {"k_returned": 1},
            }
        return {"hits": [], "context": "", "retrieval_meta": {"k_returned": 0}}

    monkeypatch.setattr(nf, "get_available_filters", _fake_get_available_filters)
    monkeypatch.setattr(nf, "search_technical_docs", _fake_search_technical_docs)

    state = SealAIState(
        user_id="tenant-user",
        messages=[HumanMessage(content="Please find PTFE datasheet for trade_name 'Kyrolon 79X'.")],
    )
    patch = material_agent_node(state)

    assert search_calls == ["tenant-user", "sealai"]
    assert (patch.get("retrieval_meta") or {}).get("allowed_tenants") == ["tenant-user", "sealai"]
    assert patch.get("working_memory").panel_material.get("technical_docs")
    assert patch.get("context") == "PTFE datasheet context"


def test_build_allowed_tenants_always_contains_shared_tenant():
    assert nf._build_allowed_tenants(None) == ["sealai"]
    assert nf._build_allowed_tenants("tenant-user") == ["tenant-user", "sealai"]
    assert nf._build_allowed_tenants("sealai") == ["sealai"]
