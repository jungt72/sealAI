"""LLM-as-judge — re-ask judge-half (``judge_no_reask``). The judge confirms the answer HONORED the
remembered facts (didn't re-ask Bekanntes); behavioral rubric-adherence, fail-safe on parse error.
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.eval.judge import judge_no_reask
from sealai_v2.tests._fakes import FakeLlmClient

_CFG = ModelConfig("fake-judge")


def _judge(text: str, answer: str, known: tuple[str, ...]) -> dict[str, bool]:
    return asyncio.run(judge_no_reask(FakeLlmClient(text), _CFG, answer, known))


def test_flags_a_reasked_topic():
    out = _judge(
        '{"reasked": [{"topic": "medium", "violated": true}, '
        '{"topic": "temperatur", "violated": false}]}',
        "Welches Medium liegt denn vor?",
        ("medium", "temperatur"),
    )
    assert out == {"medium": True, "temperatur": False}


def test_clean_answer_no_violation():
    out = _judge('{"reasked": [{"topic": "medium", "violated": false}]}', "Bei 150°C verspröde…", ("medium",))
    assert out == {"medium": False}


def test_parse_failure_is_failsafe_no_violation():
    out = _judge("nur Prosa, kein JSON", "irgendeine Antwort", ("medium", "druck"))
    assert out == {"medium": False, "druck": False}


def test_empty_known_topics_returns_empty_and_makes_no_assertion():
    out = _judge("(unused)", "antwort", ())
    assert out == {}
