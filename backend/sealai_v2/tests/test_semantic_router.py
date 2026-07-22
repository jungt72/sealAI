from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.pipeline.routing import RouteDecision, RouteName
from sealai_v2.pipeline.semantic_router import SemanticRouter
from sealai_v2.tests._fakes import FakeLlmClient


def _fallback() -> RouteDecision:
    return RouteDecision(
        route=RouteName.UNSUPPORTED_OR_AMBIGUOUS,
        reason="no_deterministic_route",
        confidence=1.0,
        forced_full_pipeline=True,
        deterministic_signal_count=0,
    )


def _response(
    route: str,
    *,
    speech_act: str = "social",
    relation: str = "new_topic",
    case_bound: bool = False,
    contains_technical_request: bool | None = None,
    confidence: float = 0.99,
) -> str:
    if contains_technical_request is None:
        contains_technical_request = route != "smalltalk_navigation"
    return json.dumps(
        {
            "primary_route": route,
            "speech_act": speech_act,
            "conversation_relation": relation,
            "case_bound": case_bound,
            "contains_technical_request": contains_technical_request,
            "confidence": confidence,
        }
    )


def _classify(answer: str, question: str = "Moin"):
    client = FakeLlmClient(answer)
    router = SemanticRouter(
        client,
        ModelConfig("ministral-8b-2512", max_output_tokens=96),
        confidence_threshold=0.8,
        timeout_s=1.0,
    )
    decision = asyncio.run(
        router.classify(
            question,
            fallback=_fallback(),
            case_active=False,
        )
    )
    return decision, client


def test_regional_greeting_can_route_to_smalltalk() -> None:
    decision, client = _classify(_response("smalltalk_navigation"), "Moin")

    assert decision.route is RouteName.SMALLTALK_NAVIGATION
    assert decision.forced_full_pipeline is False
    assert decision.confidence == 0.99
    assert decision.reason.startswith("semantic:semantic-router.v2:social")
    assert client.calls[0]["model"] == "ministral-8b-2512"
    assert "ACTIVE_CASE: false" in client.calls[0]["user"]


def test_mixed_greeting_uses_technical_primary_route() -> None:
    decision, _ = _classify(
        _response(
            "material_knowledge",
            speech_act="request_information",
            confidence=0.97,
        ),
        "Moin, kannst du mir Details zu einem unbekannten Compound geben?",
    )

    assert decision.route is RouteName.MATERIAL_KNOWLEDGE
    assert decision.forced_full_pipeline is False


def test_semantic_router_supports_case_intake_guidance_as_a_distinct_route() -> None:
    decision, _ = _classify(
        _response(
            "case_intake_invite",
            speech_act="request_guidance",
            contains_technical_request=True,
            confidence=0.98,
        ),
        "Ich möchte eine Dichtungslösung entwickeln – was brauchst du von mir?",
    )

    assert decision.route is RouteName.CASE_INTAKE_INVITE
    assert decision.forced_full_pipeline is False
    assert "request_guidance" in decision.reason


def test_semantic_knowledge_route_requires_information_speech_act() -> None:
    decision, _ = _classify(
        _response(
            "general_sealing_knowledge",
            speech_act="request_guidance",
            contains_technical_request=True,
        ),
        "Dichtungslösung – was brauchst du?",
    )

    assert decision.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert decision.reason.startswith("semantic_inconsistent_knowledge")


def test_case_and_failure_routes_remain_full_pipeline() -> None:
    for route in ("engineering_case", "leakage_troubleshooting"):
        decision, _ = _classify(
            _response(route, speech_act="describe_case", case_bound=True),
            "Das tritt nur nach dem Wiederanlauf auf",
        )
        assert decision.route.value == route
        assert decision.forced_full_pipeline is True


def test_low_confidence_preserves_conservative_fallback() -> None:
    decision, _ = _classify(
        _response("smalltalk_navigation", confidence=0.79),
    )

    assert decision.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert decision.forced_full_pipeline is True
    assert decision.reason.startswith("semantic_low_confidence")


def test_inconsistent_smalltalk_claim_preserves_fallback() -> None:
    decision, _ = _classify(
        _response(
            "smalltalk_navigation",
            contains_technical_request=True,
        )
    )

    assert decision.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert decision.reason.startswith("semantic_inconsistent_smalltalk")


def test_invalid_provider_output_preserves_conservative_fallback_without_repair() -> (
    None
):
    decision, client = _classify("not-json")

    assert decision.route is RouteName.UNSUPPORTED_OR_AMBIGUOUS
    assert decision.forced_full_pipeline is True
    assert decision.reason.startswith("semantic_unavailable")
    assert len(client.calls) == 1


def test_prompt_marks_active_case_without_exposing_transcript() -> None:
    client = FakeLlmClient(
        _response(
            "smalltalk_navigation",
            relation="continuation",
        ),
    )
    router = SemanticRouter(client, ModelConfig("ministral-8b-2512"))

    decision = asyncio.run(
        router.classify(
            "Servus",
            fallback=_fallback(),
            case_active=True,
            case_fields=("medium", "druck"),
            required_missing=("Betriebstemperatur",),
        )
    )

    assert decision.route is RouteName.SMALLTALK_NAVIGATION
    assert "ACTIVE_CASE: true" in client.calls[0]["user"]
    assert "CASE_FIELD_NAMES: medium, druck" in client.calls[0]["user"]
    assert "OPEN_REQUIRED_FIELD_NAMES: Betriebstemperatur" in client.calls[0]["user"]
    assert "Servus" in client.calls[0]["user"]
