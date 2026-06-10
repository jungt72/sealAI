"""Offline wiring smoke for the M6a multi-turn harness path — the live REPLAY is the only place
``harness._run_multiturn`` runs, so this proves the plumbing (run → summary → results.json +
report.md section) with a fake client, before any live spend.
"""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.eval import report
from sealai_v2.eval.harness import _run_edge, _run_multiturn
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.tests._fakes import FakeLlmClient


def _pipeline() -> Pipeline:
    # fixed response: a traceable, number-free distilled fact → memory stays clean, drop-rate 0.
    client = FakeLlmClient('{"facts": [{"feld": "medium", "wert": "Hydrauliköl"}]}')
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
        distiller=Distiller(client, DistillPromptAssembler(), ModelConfig("fake-helper")),
    )


_JUDGE_JSON = (
    '{"must_contain":[{"point":"redirect","status":"met"}],"must_catch":{"named":true},'
    '"must_avoid":[{"point":"spurious","violated":false}],'
    '"axes":{"7":"pass","5":"pass","3":"pass"},"notes":"ok"}'
)


def _edge_pipeline() -> Pipeline:
    client = FakeLlmClient(_JUDGE_JSON)  # judge sees no must_avoid violation → edge_overreach clean
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
    )


def test_run_edge_runs_all_cases_gate_clean():
    # offline wiring smoke for harness._run_edge — the live REPLAY is the only other place it runs
    records, errors = asyncio.run(_run_edge(_edge_pipeline(), ModelConfig("fake-judge")))
    assert errors == []
    assert len(records) >= 4
    assert all(r.column == "edge" for r in records)
    # no must_avoid violation → edge_overreach provisionally clean on every gate-relevant edge case
    assert all(r.score.provisional_gate_clean is True for r in records)


def test_run_multiturn_produces_a_wellformed_block():
    mt = asyncio.run(_run_multiturn(_pipeline(), ModelConfig("fake-judge")))
    assert mt is not None
    s = mt["summary"]
    # the seed file has 3 cases; every turn's memory is clean (no fabricated number) → quota 1.0
    assert len(mt["cases"]) == 3
    assert mt["errors"] == []
    assert s["memory_schranken_quota"] == 1.0
    assert s["n_memory_violations"] == 0
    assert s["drop"]["dropped"] == 0  # no numeric facts proposed → nothing to drop


def test_run_multiturn_records_a_failing_case_and_keeps_going():
    # a client that always raises (e.g. the live 429) must NOT crash the whole run / lose artifacts
    class _Boom:
        async def generate(self, *, system, user, model_config):
            raise RuntimeError("boom")

    p = _pipeline()
    p.client = _Boom()
    p.generator = L1Generator(_Boom(), PromptAssembler(), ModelConfig("fake-l1"))
    p.distiller = Distiller(_Boom(), DistillPromptAssembler(), ModelConfig("fake-helper"))
    mt = asyncio.run(_run_multiturn(p, ModelConfig("fake-judge")))
    assert mt is not None
    assert len(mt["errors"]) == 3  # all 3 seed cases errored, recorded
    assert mt["cases"] == []  # none completed
    assert mt["summary"]["memory_schranken_quota"] is None  # no turns → n/a, not a crash


def test_run_multiturn_none_when_memory_disabled():
    p = _pipeline()
    p.memory = None
    assert asyncio.run(_run_multiturn(p, ModelConfig("fake-judge"))) is None


def test_write_all_renders_the_multiturn_section(tmp_path):
    mt = asyncio.run(_run_multiturn(_pipeline(), ModelConfig("fake-judge")))
    manifest = {
        "run_label": "wiring",
        "milestone": "M4",
        "subject": "x",
        "l1_model_resolved": "fake",
        "l1_model_configured": "fake",
        "judge_model": "fake",
        "helper_model": "fake",
        "git_sha": "abc",
        "timestamp": "now",
        "columns": ["flags_on"],
        "n_cases": 0,
    }
    report.write_all(tmp_path, manifest, [], {}, multiturn=mt)
    rep = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "## M6a Multi-turn / Memory" in rep
    assert "AGENT-FINAL" in rep
    assert "drop-rate" in rep
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data["multiturn"]["summary"]["memory_schranken_quota"] == 1.0
