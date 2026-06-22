"""§4 matrix threaded through ``pipeline.run`` (Gap #2, Step A): a compatibility question grounds the
L1 prompt with the matrix verdict + its source; a non-compatibility turn is BYTE-IDENTICAL to a
pipeline with no matrix wired (the matrix only touches the cases it actually grounds — so the eval
delta is confined to compatibility cases). ``understand``/L3 off → the scripted call is generate-only.
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


def _pipeline(client, *, with_matrix: bool) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,  # isolate the matrix from the card retriever
        matrix=InProcessCompatibilityMatrix() if with_matrix else None,
    )


def test_compatibility_question_grounds_with_matrix_verdict_and_source():
    client = FakeLlmClient("Antwort")
    p = _pipeline(client, with_matrix=True)
    res = asyncio.run(
        p.run(
            "Dichtung mit FKM für Heißdampf-Sterilisation bei 140 °C",
            tenant=TenantContext("t1"),
        )
    )
    system = client.calls[0]["system"]
    assert "# Belegte Fakten" in system
    assert "hydrolysiert" in system  # the reviewed verdict text
    assert "Verträglichkeitsmatrix · MX-FKM-DAMPF" in system  # provenance visible
    assert res.grounded
    assert [(f.card_id, f.kind) for f in res.grounding_facts] == [
        ("MX-FKM-DAMPF", "matrix")
    ]


def test_non_compatibility_turn_is_byte_identical_without_matrix():
    """A greeting (no werkstoff×medium) surfaces no cell → the L1 prompt is byte-for-byte identical
    to a pipeline with NO matrix wired. The matrix is inert outside the cases it grounds."""
    c_with = FakeLlmClient("Antwort")
    c_without = FakeLlmClient("Antwort")
    asyncio.run(
        _pipeline(c_with, with_matrix=True).run(
            "Hallo, wer bist du?", tenant=TenantContext("t1")
        )
    )
    asyncio.run(
        _pipeline(c_without, with_matrix=False).run(
            "Hallo, wer bist du?", tenant=TenantContext("t1")
        )
    )
    assert c_with.calls[0]["system"] == c_without.calls[0]["system"]
    assert (
        c_with.calls[0]["user"] == c_without.calls[0]["user"] == "Hallo, wer bist du?"
    )
