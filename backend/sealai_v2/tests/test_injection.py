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


def test_injection_verbatim_system_prompt_leak_is_caught_agent_final():
    # an answer that dumps a long verbatim span of the system prompt → deterministic exfiltration FAIL
    leak = PromptAssembler().system_prompt(flags=None)[:400]
    _records, _errors, exfil = asyncio.run(
        _run_injection(_pipeline(leak), ModelConfig("fake-judge"))
    )
    assert (
        exfil["n_leaks"] == 7
    )  # every injection answer is the verbatim dump in this fake
    assert exfil["schranken_quota"] == 0.0
    assert all(pc["system_prompt_leak"] for pc in exfil["per_case"].values())
