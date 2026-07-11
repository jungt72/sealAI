"""ground() stage — real retrieval via the injected Retriever + the §4 matrix query (Gap #2);
None sources → vorläufig."""

from __future__ import annotations

import asyncio

from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.pipeline.stages import ground
from sealai_v2.tests.reviewed_catalog import independently_reviewed_test_catalog


def test_ground_without_sources_is_empty():
    res = asyncio.run(ground(None, None, "EPDM in Hydrauliköl", tenant_id="t"))
    assert res.grounding_facts == () and res.matrix_facts == () and not res.grounded


def test_ground_with_retriever_returns_reviewed_facts():
    res = asyncio.run(
        ground(
            InProcessRetriever(independently_reviewed_test_catalog()),
            None,
            "Bitte gib mir Details zu PTFE.",
            tenant_id="t",
        )
    )
    assert res.grounded
    assert any(f.card_id.startswith("FK-PTFE") for f in res.grounding_facts)


def test_ground_with_matrix_returns_compatibility_verdict():
    res = asyncio.run(
        ground(
            None,
            InProcessCompatibilityMatrix(),
            "FKM für Heißdampf-Sterilisation bei 140 °C",
            tenant_id="t",
        )
    )
    assert res.grounded  # matrix_facts present → grounded
    assert any(
        f.card_id == "MX-FKM-DAMPF" and f.kind == "matrix" for f in res.matrix_facts
    )
    assert res.grounding_facts == ()  # no card retriever wired here
