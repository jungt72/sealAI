"""M6b — offline wiring smoke for harness._run_injection (the live REPLAY is the only other place it
runs). Covers: the injection class runs through the single-turn judge/scorer (injection_override,
human-final) AND the deterministic exfiltration gate (agent-final leak_detect over each answer).
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.eval.harness import _run_injection
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.tests._fakes import FakeLlmClient

_CLEAN_JUDGE = (
    '{"must_contain":[{"point":"refuse/defer","status":"met"}],"must_catch":{"named":true},'
    '"must_avoid":[{"point":"override","violated":false}],"axes":{"7":"pass"},"notes":"ok"}'
)


def _pipeline(answer_text: str) -> Pipeline:
    client = FakeLlmClient(answer_text)
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
    )


def test_injection_clean_run_no_leak():
    records, errors, exfil = asyncio.run(
        _run_injection(_pipeline(_CLEAN_JUDGE), ModelConfig("fake-judge"))
    )
    assert errors == []
    assert len(records) == 7 and all(r.column == "injection" for r in records)
    # a benign answer leaks nothing → exfiltration agent-final clean
    assert exfil["n_leaks"] == 0 and exfil["schranken_quota"] == 1.0


def test_injection_verbatim_system_prompt_leak_is_blocked_on_serve_path():
    # P1.4: the SERVE-path exfiltration Schranke (wired into Pipeline.run) now BLOCKS a verbatim
    # system-prompt dump BEFORE it ships — so even though this fake L1 dumps a long verbatim span,
    # the pipeline replaces it with the deterministic refusal hedge. The eval therefore scores the
    # already-hedged answer: zero leaks reach the agent-final gate (the leak never left the pipeline).
    # (Pre-P1.4 this asserted n_leaks == 7, i.e. the leak shipped and the eval caught it after the
    # fact; with P1.4 the defense has moved into the SERVE path, which is the point of the fix.)
    leak = PromptAssembler().system_prompt(flags=None)[:400]
    _records, _errors, exfil = asyncio.run(
        _run_injection(_pipeline(leak), ModelConfig("fake-judge"))
    )
    assert exfil["n_leaks"] == 0
    assert exfil["schranken_quota"] == 1.0
    assert not any(pc["system_prompt_leak"] for pc in exfil["per_case"].values())
