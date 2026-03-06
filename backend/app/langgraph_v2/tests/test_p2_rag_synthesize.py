from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from app.langgraph_v2.state import SealAIState
from app.services.rag.nodes.p2_rag_lookup import node_p2_rag_synthesize


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@patch("app.services.rag.nodes.p2_rag_lookup.run_llm_async", new_callable=AsyncMock)
async def test_node_p2_rag_synthesize_writes_summary_into_working_memory(mock_run_llm: AsyncMock) -> None:
    mock_run_llm.return_value = (
        "Kyrolon 79X ist fuer dynamische PTFE-Dichtanwendungen mit hoher Chemikalienbestaendigkeit geeignet. "
        "Die Dokumente nennen gute Medienvertraeglichkeit und stabile Werte bei erhoehter Temperatur. "
        "Prelon ist ebenfalls verfuegbar."
    )
    state = SealAIState(
        messages=[HumanMessage(content="Was kannst du mir zu Kyrolon sagen?")],
        context="[1] /docs/kyrolon.pdf page 2 (score 0.88)\nKyrolon 79X ist fuer dynamische Anwendungen geeignet.",
        working_memory={
            "panel_material": {
                "rag_context": "[1] /docs/kyrolon.pdf page 2 (score 0.88)\nKyrolon 79X ist fuer dynamische Anwendungen geeignet.",
                "technical_docs": [
                    {
                        "snippet": "Kyrolon 79X zeigt hohe Chemikalienbestaendigkeit und geringe Reibung.",
                        "source": "kyrolon_factcard.pdf",
                    }
                ],
            }
        },
    )

    patch_result = await node_p2_rag_synthesize(state)

    wm = patch_result["reasoning"]["working_memory"]
    summary = wm.response_text or ""
    assert "Kyrolon 79X" in summary
    assert "Prelon" not in summary
    assert wm.knowledge_material == summary
    assert wm.panel_material.get("rag_synthesized") == summary
    assert patch_result["reasoning"]["retrieval_meta"]["rag_synthesized"] is True


@pytest.mark.anyio
async def test_node_p2_rag_synthesize_noops_without_context_or_hits() -> None:
    state = SealAIState(messages=[HumanMessage(content="Was ist Kyrolon?")])

    patch_result = await node_p2_rag_synthesize(state)

    assert patch_result["reasoning"]["last_node"] == "node_p2_rag_synthesize"
    assert "working_memory" not in patch_result["reasoning"]
