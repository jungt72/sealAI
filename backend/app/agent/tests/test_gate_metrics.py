from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agent.runtime.gate import (
    GateDecision,
    LLMGateResult,
    decide_route,
    decide_route_async,
)


CONV = SimpleNamespace(session_zone="conversation")
GOV = SimpleNamespace(session_zone="governed")


def test_decide_route_observes_conversation_metric_on_deterministic_light_path() -> None:
    with patch("app.agent.runtime.gate._observe_gate_decision", side_effect=lambda decision, _started_at: decision) as observe:
        decision = decide_route("Hallo", CONV)

    assert decision.route == "CONVERSATION"
    assert observe.call_count == 1
    observed_decision = observe.call_args.args[0]
    assert observed_decision.route == "CONVERSATION"


@pytest.mark.anyio
async def test_decide_route_async_observes_governed_metric_on_hard_override() -> None:
    with patch("app.agent.runtime.gate._observe_gate_decision", side_effect=lambda decision, _started_at: decision) as observe:
        decision = await decide_route_async("PTFE-Dichtung fuer 180°C Dampf", CONV)

    assert decision.route == "GOVERNED"
    assert observe.call_count == 1
    observed_decision = observe.call_args.args[0]
    assert observed_decision.route == "GOVERNED"


def test_decide_route_observes_exploration_metric_on_llm_path() -> None:
    llm_result = LLMGateResult(routing="EXPLORATION", confidence=0.91)
    with patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result), \
         patch("app.agent.runtime.gate._observe_gate_decision", side_effect=lambda decision, _started_at: decision) as observe:
        decision = decide_route("Ich suche etwas fuer meine Pumpe.", GOV)

    assert decision.route == "EXPLORATION"
    assert observe.call_count == 1
    observed_decision = observe.call_args.args[0]
    assert isinstance(observed_decision, GateDecision)
    assert observed_decision.route == "EXPLORATION"
