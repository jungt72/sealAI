"""Gegencheck verdict threaded through ``pipeline.run`` (Modus E end-to-end, offline).

A "wir verwenden X, passt das?" turn attaches the deterministic verdict to
``PipelineResult.gegencheck``; a knowledge turn or a matrix-off pipeline attaches
None (byte-identical no-Gegencheck path). Generate-only fake client (no understand,
no L3) — the verdict is pure/deterministic, independent of the narration.
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


def _pipeline(client, *, with_matrix: bool = True) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        matrix=InProcessCompatibilityMatrix() if with_matrix else None,
    )


def _run(p, q):
    return asyncio.run(p.run(q, tenant=TenantContext("t1")))


def test_verdict_flows_for_incompatible_gegencheck():
    res = _run(_pipeline(FakeLlmClient("Antwort")), "Wir verwenden FKM in Heißdampf, passt das?")
    assert res.gegencheck is not None
    assert res.gegencheck["disqualified"] is True
    assert res.gegencheck["reason"] and res.gegencheck["source"]


def test_no_verdict_on_knowledge_turn():
    res = _run(_pipeline(FakeLlmClient("Antwort")), "Was kann FKM?")
    assert res.gegencheck is None


def test_no_verdict_when_matrix_off():
    res = _run(
        _pipeline(FakeLlmClient("Antwort"), with_matrix=False),
        "Wir verwenden FKM in Heißdampf, passt das?",
    )
    assert res.gegencheck is None
