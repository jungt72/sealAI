"""P0 perf instrumentation (PERF tranche 1): per-stage turn timing + eval elapsed_ms.

The timer is pure bookkeeping — these tests pin that one structured line per turn is emitted,
that it carries ONLY durations + a random turn id (no question/answer text, no tenant/session),
and that results are unchanged (the answer is byte-identical to the scripted fake response).
"""

from __future__ import annotations

import asyncio
import json

from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import Flags, ModelConfig, SessionContext
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.knowledge.traps import load_traps
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline import timing
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import (
    DistillPromptAssembler,
    PromptAssembler,
    VerifierPromptAssembler,
)
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient

_CLEAN_VERDICT = json.dumps({"findings": [], "verdict": "clean"})


def _full_pipeline(client) -> Pipeline:
    """Every stage wired (retriever, engine, L3, memory + distiller); understand off so the
    scripted call order stays generate → verify → distill."""
    catalog = load_traps()
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        verifier=L3Verifier(
            client, VerifierPromptAssembler(), ModelConfig("fake-l3"), catalog
        ),
        catalog=catalog,
        retriever=InProcessRetriever(),
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
        distiller=Distiller(client, DistillPromptAssembler(), ModelConfig("fake-helper")),
    )


def test_full_turn_emits_one_line_with_all_stage_keys_and_no_pii(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(timing, "emit", captured.append)
    question = "PII-MARKER-FRAGE: warum quillt EPDM in Hydrauliköl?"
    client = ScriptedFakeLlmClient(
        [
            "PII-MARKER-ANTWORT: wegen Unpolarität.",  # generate
            _CLEAN_VERDICT,  # verify
            '{"facts": []}',  # distill
        ]
    )
    res = asyncio.run(
        _full_pipeline(client).run(
            question, tenant=TenantContext("t1"), session=SessionContext("s1")
        )
    )

    # behavior unchanged: the answer is exactly the scripted fake response, 3 LLM calls.
    assert res.answer.text == "PII-MARKER-ANTWORT: wegen Unpolarität."
    assert len(client.calls) == 3

    # exactly ONE line per turn, with every executed stage + total + turn id.
    assert len(captured) == 1
    payload = captured[0]
    assert payload["event"] == "v2_turn_timing"
    assert payload["turn_id"]
    assert set(payload["stages"]) == {
        "recall_ms",
        "ground_ms",
        "compute_ms",
        "generate_ms",
        "verify_ms",
        "cite_ms",
        "distill_ms",
    }
    assert all(v >= 0.0 for v in payload["stages"].values())
    assert payload["total_ms"] >= max(payload["stages"].values()) - 0.1

    # NO PII: neither question nor answer text reaches the line (nor tenant/session ids).
    line = json.dumps(payload, ensure_ascii=False)
    assert "PII-MARKER" not in line
    assert "tenant" not in line and "session" not in line


def test_skipped_stages_are_omitted_and_understand_is_timed(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(timing, "emit", captured.append)
    fake = FakeLlmClient('{"intent": "wissensfrage", "rationale": "x"}')
    p = Pipeline(
        generator=L1Generator(fake, PromptAssembler(), ModelConfig("fake-l1")),
        client=fake,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=True,
    )
    asyncio.run(p.run("Frage?", tenant=TenantContext("t1")))

    assert len(captured) == 1
    stages = captured[0]["stages"]
    assert "understand_ms" in stages
    assert "distill_ms" not in stages  # no session → remember never ran
    assert "verify_ms" not in stages  # no verifier wired


def test_eval_unit_records_elapsed_ms_and_report_serializes_it():
    from sealai_v2.eval import report
    from sealai_v2.eval.cases import Case
    from sealai_v2.eval.harness import _run_unit

    client = ScriptedFakeLlmClient(["Antwort.", "kein json"])  # generate + judge
    p = Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
    )
    case = Case(
        id="T-ELAPSED-1",
        klass="Wissen",
        input="Frage?",
        must_contain=(),
        must_catch="",
        must_avoid=(),
        primary_axes=(1,),
        hard_gates=(),
    )
    rec = asyncio.run(
        _run_unit(p, ModelConfig("fake-judge"), case, "flags_on", Flags(True, True))
    )
    assert rec.error is None
    assert rec.elapsed_ms >= 0.0
    assert report._record_to_dict(rec)["elapsed_ms"] == rec.elapsed_ms
