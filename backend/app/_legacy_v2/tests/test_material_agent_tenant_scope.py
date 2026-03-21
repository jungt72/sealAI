from langchain_core.messages import HumanMessage

import app._legacy_v2.nodes.nodes_flows as nf
from app._legacy_v2.nodes.nodes_flows import material_agent_node
from app._legacy_v2.state.sealai_state import SealAIState


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
        conversation={
            "user_id": "tenant-user",
            "messages": [HumanMessage(content="Please find PTFE datasheet for trade_name 'Kyrolon 79X'.")],
        },
    )
    patch = material_agent_node(state)

    assert search_calls == ["tenant-user", "sealai"]
    assert (patch.get("reasoning", {}).get("retrieval_meta") or {}).get("allowed_tenants") == ["tenant-user", "sealai"]
    assert patch.get("reasoning", {}).get("working_memory").panel_material.get("technical_docs")
    assert patch.get("reasoning", {}).get("context") == "PTFE datasheet context"
    assert patch.get("working_profile", {}).get("material_choice", {}).get("specificity") == "family_only"
    assert patch.get("working_profile", {}).get("material_choice", {}).get("governed") is False


def test_build_allowed_tenants_always_contains_shared_tenant():
    assert nf._build_allowed_tenants(None) == ["sealai"]
    assert nf._build_allowed_tenants("tenant-user") == ["tenant-user", "sealai"]
    assert nf._build_allowed_tenants("sealai") == ["sealai"]


def test_material_agent_node_sets_low_quality_flag_when_all_scores_below_threshold(monkeypatch):
    def _fake_get_available_filters(*, tenant_id=None, max_points=2000, collection_name=None):  # noqa: ARG001
        return {"filters": ["additional_metadata.trade_name"]}

    def _fake_search_technical_docs(query, material_code=None, *, tenant_id=None, k=5, metadata_filters=None):  # noqa: ARG001
        return {
            "hits": [
                {
                    "source": "fkm.pdf",
                    "document_id": "doc-fkm",
                    "score": 0.03,
                    "snippet": "Low confidence snippet",
                },
                {
                    "source": "ptfe.pdf",
                    "document_id": "doc-ptfe",
                    "score": 0.05,
                    "snippet": "Also low confidence",
                },
            ],
            "context": "Low confidence context",
            "retrieval_meta": {"collection": "technical_docs", "k_returned": 2, "top_scores": [0.04, 0.03]},
        }

    monkeypatch.setattr(nf, "get_available_filters", _fake_get_available_filters)
    monkeypatch.setattr(nf, "search_technical_docs", _fake_search_technical_docs)

    state = SealAIState(
        conversation={
            "user_id": "tenant-user",
            "messages": [HumanMessage(content="Please find PTFE datasheet for trade_name 'Kyrolon 79X'.")],
        },
    )
    patch = material_agent_node(state)

    assert patch.get("reasoning", {}).get("working_memory").panel_material.get("technical_docs")
    assert patch.get("reasoning", {}).get("flags", {}).get("rag_low_quality_results") is False


def test_material_agent_node_treats_ptfe_factcards_as_high_quality(monkeypatch):
    def _fake_get_available_filters(*, tenant_id=None, max_points=2000, collection_name=None):  # noqa: ARG001
        return {"filters": []}

    def _fake_search_technical_docs(query, material_code=None, *, tenant_id=None, k=5, metadata_filters=None):  # noqa: ARG001
        return {
            "hits": [
                {
                    "source": "ptfe_master.json",
                    "document_id": "PTFE-F-062",
                    "score": 0.001,
                    "snippet": "Validated PTFE master factcard",
                }
            ],
            "context": "Validated PTFE master factcard",
            "retrieval_meta": {
                "collection": "technical_docs",
                "k_returned": 1,
                "top_scores": [0.001],
                "rag_low_quality_results": True,
            },
        }

    monkeypatch.setattr(nf, "get_available_filters", _fake_get_available_filters)
    monkeypatch.setattr(nf, "search_technical_docs", _fake_search_technical_docs)

    state = SealAIState(
        conversation={
            "user_id": "tenant-user",
            "messages": [HumanMessage(content="Ich benötige eine Dichtungslösung für mein Rührwerk.")],
        },
    )
    patch = material_agent_node(state)

    assert patch.get("reasoning", {}).get("working_memory").panel_material.get("technical_docs")
    assert patch.get("reasoning", {}).get("flags", {}).get("rag_low_quality_results") is False


def test_material_agent_node_detects_german_technical_terms(monkeypatch):
    def _fake_get_available_filters(*, tenant_id=None, max_points=2000, collection_name=None):  # noqa: ARG001
        return {"filters": []}

    def _fake_search_technical_docs(query, material_code=None, *, tenant_id=None, k=5, metadata_filters=None):  # noqa: ARG001
        return {
            "hits": [{"source": "prelonring.pdf", "document_id": "doc-prelonring", "score": 0.71, "snippet": "Prelonring"}],
            "context": "Prelonring",
            "retrieval_meta": {"collection": "technical_docs", "k_returned": 1, "top_scores": [0.71]},
        }

    monkeypatch.setattr(nf, "get_available_filters", _fake_get_available_filters)
    monkeypatch.setattr(nf, "search_technical_docs", _fake_search_technical_docs)

    state = SealAIState(
        conversation={
            "user_id": "tenant-user",
            "messages": [HumanMessage(content="Ich benötige eine Dichtungslösung für mein Rührwerk.")],
        },
    )
    patch = material_agent_node(state)

    assert patch.get("reasoning", {}).get("working_memory").panel_material.get("technical_docs")
    assert patch.get("reasoning", {}).get("context") == "Prelonring"
    assert patch.get("working_profile", {}).get("material_choice", {}).get("specificity") == "family_only"
