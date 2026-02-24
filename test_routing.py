"""Phase 4 routing smoke-test for frontdoor -> route_after_frontdoor topology."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.nodes_frontdoor import (
    FrontdoorRouteAxesOutput,
    frontdoor_discovery_node,
)
from app.langgraph_v2.nodes.route_after_frontdoor import route_after_frontdoor_node
from app.langgraph_v2.state import SealAIState


@dataclass
class RoutingCase:
    query: str
    fake_frontdoor: FrontdoorRouteAxesOutput
    expected_hop: str
    expected_path: str


def _run_with_fake_structured(case: RoutingCase) -> str:
    import app.langgraph_v2.nodes.nodes_frontdoor as nodes_frontdoor

    def _fake_structured(_state: SealAIState, _user_text: str) -> FrontdoorRouteAxesOutput:
        return case.fake_frontdoor

    original = nodes_frontdoor._invoke_frontdoor_structured
    nodes_frontdoor._invoke_frontdoor_structured = _fake_structured
    try:
        state = SealAIState(messages=[HumanMessage(content=case.query)])
        frontdoor_patch = frontdoor_discovery_node(state)
        routed_state = state.model_copy(update=frontdoor_patch)
        command = route_after_frontdoor_node(routed_state)
        return str(command.goto)
    finally:
        nodes_frontdoor._invoke_frontdoor_structured = original


def _build_cases() -> List[RoutingCase]:
    return [
        RoutingCase(
            query="Was ist max Temp für PTFE?",
            fake_frontdoor=FrontdoorRouteAxesOutput(
                social_opening=False,
                task_intents=["material_research"],
                is_safety_critical=False,
                requires_rag=True,
                needs_pricing=False,
                reasoning="Material lookup request.",
            ),
            expected_hop="frontdoor_parallel_fanout_node",
            expected_path="frontdoor -> deterministic-kb -> response/supervisor",
        ),
        RoutingCase(
            query="Material für 150°C, HF-Säure, Alu-Welle",
            fake_frontdoor=FrontdoorRouteAxesOutput(
                social_opening=False,
                task_intents=["material_research"],
                is_safety_critical=True,
                requires_rag=True,
                needs_pricing=False,
                reasoning="Hard-screening material request.",
            ),
            expected_hop="frontdoor_parallel_fanout_node",
            expected_path="frontdoor -> deterministic-kb -> response/supervisor",
        ),
        RoutingCase(
            query="Wir haben Leckage an PTFE-Dichtung",
            fake_frontdoor=FrontdoorRouteAxesOutput(
                social_opening=False,
                task_intents=["troubleshooting_leakage"],
                is_safety_critical=True,
                requires_rag=False,
                needs_pricing=False,
                reasoning="Leakage troubleshooting intent.",
            ),
            expected_hop="supervisor_policy_node",
            expected_path="frontdoor -> supervisor -> troubleshooting",
        ),
        RoutingCase(
            query="Pumpe für 200°C, 80 bar",
            fake_frontdoor=FrontdoorRouteAxesOutput(
                social_opening=False,
                task_intents=["engineering_calculation"],
                is_safety_critical=False,
                requires_rag=False,
                needs_pricing=False,
                reasoning="Engineering design request.",
            ),
            expected_hop="node_p1_context",
            expected_path="frontdoor -> p1 -> p2/p3/p4",
        ),
        RoutingCase(
            query="PTFE vs FFKM für 150°C",
            fake_frontdoor=FrontdoorRouteAxesOutput(
                social_opening=False,
                task_intents=["general_knowledge"],
                is_safety_critical=False,
                requires_rag=False,
                needs_pricing=False,
                reasoning="Comparison request.",
            ),
            expected_hop="supervisor_policy_node",
            expected_path="frontdoor -> supervisor -> comparison",
        ),
        RoutingCase(
            query="Was ist der Unterschied zwischen FKM und FFKM?",
            fake_frontdoor=FrontdoorRouteAxesOutput(
                social_opening=True,
                task_intents=[],
                is_safety_critical=False,
                requires_rag=False,
                needs_pricing=False,
                reasoning="Social opener classification.",
            ),
            expected_hop="smalltalk_node",
            expected_path="frontdoor -> smalltalk -> response",
        ),
    ]


def main() -> int:
    print("=== PHASE 4 ROUTING TEST ===")
    failed = 0
    for idx, case in enumerate(_build_cases(), start=1):
        actual = _run_with_fake_structured(case)
        ok = actual == case.expected_hop
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"{idx}. {status}")
        print(f"   Query:    {case.query}")
        print(f"   Expected: {case.expected_path} [{case.expected_hop}]")
        print(f"   Actual:   frontdoor -> {actual}")
    print(f"Summary: {len(_build_cases()) - failed}/{len(_build_cases())} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
