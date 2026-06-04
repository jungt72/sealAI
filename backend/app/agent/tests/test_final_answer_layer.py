from __future__ import annotations

from app.agent.runtime.final_answer_layer import (
    FinalAnswerEnvelope,
    apply_final_answer_layer,
)


def test_final_answer_layer_disabled_is_passthrough(monkeypatch):
    monkeypatch.setenv("SEALAI_ENABLE_FINAL_ANSWER_LAYER", "false")
    payload = {
        "reply": "Fallback",
        "answer_markdown": "Prepared answer",
        "run_meta": {"answer_trace": {"answer_markdown_source": "knowledge_composer"}},
    }

    result = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="knowledge",
            answer_mode="knowledge",
            deterministic_fallback_reply="Fallback",
        ),
    )

    assert result == payload


def test_final_answer_layer_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv("SEALAI_ENABLE_FINAL_ANSWER_LAYER", raising=False)
    payload = {"reply": "Fallback", "run_meta": {"answer_trace": {}}}

    result = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="governed",
            answer_mode="structured_clarification",
            deterministic_fallback_reply="Fallback",
        ),
    )

    assert result["answer_markdown"] == "Fallback"
    assert result["run_meta"]["final_answer_layer"]["enabled"] is True


def test_final_answer_layer_enabled_falls_back_to_deterministic_reply(monkeypatch):
    monkeypatch.setenv("SEALAI_ENABLE_FINAL_ANSWER_LAYER", "true")
    payload = {"reply": "Deterministische Antwort", "run_meta": {"answer_trace": {}}}

    result = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="governed",
            answer_mode="structured_clarification",
            deterministic_fallback_reply="Deterministische Antwort",
        ),
    )

    assert result["reply"] == "Deterministische Antwort"
    assert result["answer_markdown"] == "Deterministische Antwort"
    assert result["run_meta"]["final_answer_layer"]["fallback_used"] is True
    assert result["run_meta"]["final_answer_layer"]["route"] == "governed"
    assert (
        result["run_meta"]["answer_trace"]["answer_mode"] == "structured_clarification"
    )


def test_final_answer_layer_enabled_preserves_prepared_answer(monkeypatch):
    monkeypatch.setenv("SEALAI_ENABLE_FINAL_ANSWER_LAYER", "true")
    payload = {
        "reply": "Deterministische Antwort",
        "answer_markdown": "Natuerliche Antwort",
        "run_meta": {"answer_trace": {"answer_markdown_source": "governed_composer"}},
    }

    result = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="governed",
            answer_mode="structured_clarification",
            deterministic_fallback_reply="Deterministische Antwort",
            existing_answer_markdown="Natuerliche Antwort",
            existing_answer_markdown_source="governed_composer",
            composer_tier="tier_b",
        ),
    )

    assert result["reply"] == "Deterministische Antwort"
    assert result["answer_markdown"] == "Natuerliche Antwort"
    assert result["run_meta"]["final_answer_layer"]["fallback_used"] is False
    assert (
        result["run_meta"]["final_answer_layer"]["selected_source"]
        == "governed_composer"
    )
    assert result["run_meta"]["answer_trace"]["composer_tier"] == "tier_b"


def test_final_answer_layer_metadata_is_bounded(monkeypatch):
    monkeypatch.setenv("SEALAI_ENABLE_FINAL_ANSWER_LAYER", "true")
    payload = {
        "reply": "Antwort",
        "run_meta": {"answer_trace": {"answer_markdown_source": "knowledge_service"}},
    }

    result = apply_final_answer_layer(
        payload,
        FinalAnswerEnvelope(
            route="knowledge",
            answer_mode="knowledge",
            deterministic_fallback_reply="Antwort",
            latest_user_message="Was bedeutet PFAS fuer Dichtungen?",
        ),
    )

    final_meta = result["run_meta"]["final_answer_layer"]
    assert "Was bedeutet" not in str(final_meta)
    assert set(final_meta) == {
        "enabled",
        "route",
        "answer_mode",
        "selected_source",
        "composer_tier",
        "fallback_used",
        "fallback_reason",
    }
