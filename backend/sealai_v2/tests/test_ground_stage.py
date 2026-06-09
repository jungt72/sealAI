"""ground() stage — real retrieval via the injected Retriever; None retriever → vorläufig."""

from __future__ import annotations

import asyncio

from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.pipeline.stages import ground


def test_ground_without_retriever_is_empty():
    res = asyncio.run(ground(None, "EPDM in Hydrauliköl", tenant_id="t"))
    assert res.grounding_facts == () and not res.grounded


def test_ground_with_retriever_returns_reviewed_facts():
    res = asyncio.run(
        ground(
            InProcessRetriever(), "EPDM-O-Ringe quellen in Hydrauliköl", tenant_id="t"
        )
    )
    assert res.grounded
    assert any(f.card_id == "FK-EPDM-MINERALOEL" for f in res.grounding_facts)
