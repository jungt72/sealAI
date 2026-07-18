from __future__ import annotations

import asyncio

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import SessionContext
from sealai_v2.pipeline.pipeline import ProductModeUnavailable, build_pipeline
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._apiutil import auth, make_client, make_pipeline
from sealai_v2.tests._fakes import FakeLlmClient


def _pipeline(*, enabled: bool, conversational_routes: bool = False):
    client = FakeLlmClient("Belegte Antwort")
    settings = Settings(
        knowledge_mode_enabled=enabled,
        execution_policy_enabled=True,
        route_optimization_enabled=conversational_routes,
        route_prompt_families_enabled=conversational_routes,
        structured_answer_enabled=False,
        verify_enabled=False,
        compute_enabled=False,
        memory_enabled=False,
        understand_enabled=False,
    )
    return build_pipeline(settings, client=client), client


def test_production_greeting_uses_conversational_path_not_evidence_gap() -> None:
    pipeline, client = _pipeline(enabled=True, conversational_routes=True)

    result = asyncio.run(
        pipeline.run(
            "Hallo und guten abend",
            tenant=TenantContext("tenant-a"),
            session=SessionContext("case-a"),
        )
    )

    assert result.route_name == "smalltalk_navigation"
    assert result.turn_state.execution_class == "S0"
    assert result.answer.text == "Belegte Antwort"
    assert "kein unabhängig geprüfter Beleg" not in result.answer.text
    assert len(client.calls) == 1


def test_signal_free_ambiguity_is_clarified_without_model_or_technical_demands() -> (
    None
):
    pipeline, client = _pipeline(enabled=True, conversational_routes=True)

    result = asyncio.run(
        pipeline.run(
            "Erzähl mir etwas",
            tenant=TenantContext("tenant-a"),
            session=SessionContext("case-a"),
        )
    )

    assert result.route_name == "unsupported_or_ambiguous"
    assert result.turn_state.execution_class == "D1"
    assert result.answer.model == "deterministic-policy"
    assert "fachliche Frage zur Dichtungstechnik" in result.answer.text
    assert "Herstellerdatenblatt" not in result.answer.text
    assert client.calls == []


def test_inactive_knowledge_mode_fails_before_any_model_call() -> None:
    pipeline, client = _pipeline(enabled=False)

    with pytest.raises(ProductModeUnavailable) as raised:
        asyncio.run(
            pipeline.run(
                "Bitte gib mir Details zu PTFE.",
                tenant=TenantContext("tenant-a"),
                session=SessionContext("case-a"),
            )
        )

    assert raised.value.mode == "knowledge"
    assert raised.value.maturity == "pilot_not_activated"
    assert client.calls == []


def test_enabled_knowledge_mode_uses_the_owner_approved_evidence() -> None:
    pipeline, client = _pipeline(enabled=True)

    result = asyncio.run(
        pipeline.run(
            "Bitte gib mir Details zu PTFE.",
            tenant=TenantContext("tenant-a"),
            session=SessionContext("case-a"),
        )
    )

    assert result.grounded is True
    assert result.grounding_facts
    assert client.calls


def test_enabled_knowledge_mode_returns_evidence_gap_without_model_call() -> None:
    pipeline, client = _pipeline(enabled=True)

    result = asyncio.run(
        pipeline.run(
            "Ist FKM gegen Essigsäure beständig?",
            tenant=TenantContext("tenant-a"),
            session=SessionContext("case-a"),
        )
    )

    assert result.grounded is False
    assert result.answer.model == "deterministic-policy"
    assert "kein unabhängig geprüfter Beleg" in result.answer.text
    assert result.turn_state.execution_class == "D1"
    assert client.calls == []


def test_chat_api_exposes_structured_mode_unavailable_contract() -> None:
    pipeline = make_pipeline()
    pipeline.knowledge_mode_enabled = False
    client, _ = make_client(pipeline)

    response = client.post(
        "/api/v2/chat",
        json={"message": "Details zu PTFE"},
        headers=auth("tok-A"),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "product_mode_unavailable",
        "mode": "knowledge",
        "maturity": "pilot_not_activated",
        "message": (
            "Dieser Produktmodus befindet sich noch in der fachlichen Freigabe und ist "
            "derzeit nicht aktiviert."
        ),
    }


def test_manufacturer_mode_dependencies_fail_closed_at_configuration_load() -> None:
    with pytest.raises(ValueError, match="requires capability_profiles_enabled"):
        Settings(manufacturer_fit_enabled=True)
    with pytest.raises(ValueError, match="requires capability profiles and fit"):
        Settings(manufacturer_handoff_enabled=True)
