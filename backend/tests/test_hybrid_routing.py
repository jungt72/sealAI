from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

pytestmark = pytest.mark.skip("Legacy hybrid routing module removed; awaiting v2 implementation")

# Legacy imports retained for documentation purposes; tests are skipped.
# from app.services.langgraph.config.routing import load_routing_config
# from app.services.langgraph.hybrid_routing import (
#     BUTTON_INTENTS,
#     extract_button_payload,
#     find_intent_from_text,
#     last_agent_suggestion,
#     suggestions_from_alternatives,
# )


@pytest.fixture(autouse=True)
def _reset_routing_cache(monkeypatch: pytest.MonkeyPatch):
    # Ensure routing config is reloaded for each test to honour env overrides.
    from app.services.langgraph.config import routing as routing_module

    routing_module.load_routing_config.cache_clear()
    monkeypatch.delenv("ROUTING_CONF_PATH", raising=False)
    monkeypatch.setenv("HYBRID_ROUTING_ENABLED", "1")
    yield
    routing_module.load_routing_config.cache_clear()


def test_extract_button_payload_defaults_to_ui_button():
    payload = extract_button_payload({"intent": "Werkstoff"})
    assert payload["intent_seed"] == "werkstoff"
    assert payload["source"] is None  # source added later when dispatching

    payload = extract_button_payload({"intent": "werkstoff", "source": "UI_Button"})
    assert payload["source"] == "ui_button"


def test_find_intent_from_text_scores_above_threshold_for_synonym():
    message = HumanMessage(content="Ich brauche einen Werkstoff für 200 °C")
    decision = find_intent_from_text([message])
    assert decision.candidate is not None
    cfg = load_routing_config()
    assert decision.candidate.intent in BUTTON_INTENTS
    assert decision.candidate.score >= cfg.confidence_threshold


def test_find_intent_from_text_flags_fallback_for_unknown_request():
    message = HumanMessage(content="Wie ist das Wetter heute?")
    decision = find_intent_from_text([message])
    assert decision.candidate is None or decision.candidate.score < load_routing_config().confidence_threshold
    assert decision.reason in {"no_match", "low_delta"}


def test_last_agent_suggestion_uses_config_labels():
    cfg = load_routing_config()
    alt = suggestions_from_alternatives([])
    assert isinstance(alt, list)

    suggestion = last_agent_suggestion("werkstoff")
    assert suggestion is not None
    assert suggestion["intent"] == "werkstoff"
    assert suggestion["label"] == (cfg.intents["werkstoff"].button_label or "Werkstoff")
