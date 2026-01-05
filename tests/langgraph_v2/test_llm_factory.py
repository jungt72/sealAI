# tests/langgraph_v2/test_llm_factory.py
from __future__ import annotations

import os

import pytest

from app.langgraph_v2.utils import llm_factory


def test_get_model_tier_pro_uses_constant_or_env(monkeypatch):
    # Sicherstellen, dass PRO-Fallback nicht von zufälligen Umgebungen abhängt
    monkeypatch.delenv("OPENAI_MODEL_PRO", raising=False)

    model = llm_factory.get_model_tier("pro")
    # Wir erwarten irgendein nicht-leeres Modell; konkrete Namen können sich ändern,
    # daher nur Grund-Assertion:
    assert isinstance(model, str)
    assert model.strip() != ""


def test_get_model_tier_mini_and_fast_share_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_MINI", "gpt-4.1-mini-test")

    mini_model = llm_factory.get_model_tier("mini")
    fast_model = llm_factory.get_model_tier("fast")

    assert mini_model == "gpt-4.1-mini-test"
    assert fast_model == "gpt-4.1-mini-test"


def test_get_model_tier_nano_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_NANO", "gpt-4.1-nano-test")

    nano_model = llm_factory.get_model_tier("nano")

    assert nano_model == "gpt-4.1-nano-test"


def test_get_model_tier_default_is_mini_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_MINI", "gpt-4.1-mini-default")

    model = llm_factory.get_model_tier(None)

    assert model == "gpt-4.1-mini-default"


def test_run_llm_uses_fake_llm_for_json_prompts(monkeypatch):
    """
    Wenn LANGGRAPH_USE_FAKE_LLM=1 gesetzt ist, soll run_llm keinen echten
    OpenAI-Call machen, sondern das Fake-JSON zurückgeben.
    """
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "1")

    text = llm_factory.run_llm(
        model="gpt-4.1-mini",
        prompt="Temperatur: 120°C, Druck: 10 bar",
        system="Bitte Coverage als kompaktes JSON berechnen.",
        temperature=0.2,
        max_tokens=200,
    )

    # Erwartetes Format: JSON-String mit summary/coverage/missing
    import json

    data = json.loads(text)
    assert "summary" in data
    assert "coverage" in data
    assert "missing" in data
    assert isinstance(data["coverage"], (int, float))


def test_run_llm_fake_mode_for_generic_prompts(monkeypatch):
    """
    Im Fake-Modus sollen generische Prompts mit einem klar erkennbaren Prefix
    zurückkommen, um CI-Tests deterministisch zu halten.
    """
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "1")

    text = llm_factory.run_llm(
        model="gpt-4.1-mini",
        prompt="Beschreibe kurz PTFE.",
        system="Allgemeiner Werkstoff-Prompt.",
        temperature=0.7,
        max_tokens=100,
    )

    assert "[FAKE_LLM_RESPONSE]" in text
    assert "Beschreibe kurz PTFE" in text


@pytest.mark.parametrize(
    "content, expected",
    [
        ("Hallo Welt", "Hallo Welt"),
        ([{"type": "text", "text": "Hallo"}, {"type": "text", "text": " Welt"}], "Hallo Welt"),
        ([{"foo": "bar"}, "Baz"], "{'foo': 'bar'}Baz"),
        (42, "42"),
    ],
)
def test_normalize_lc_content(content, expected):
    """
    _normalize_lc_content ist zwar intern, aber für die Robustheit der LLM-Antwort
    zentral. Wir testen die wichtigsten Fälle direkt.
    """
    # Zugriff auf die interne Helper-Funktion über das Modul
    normalize = llm_factory._normalize_lc_content  # type: ignore[attr-defined]

    result = normalize(content)
    assert result == expected


def test_run_llm_handles_exceptions_gracefully(monkeypatch):
    """
    Wenn der ChatOpenAI-Call eine Exception wirft, soll run_llm NICHT crashen,
    sondern eine kurze, ehrliche Fehlermeldung zurückgeben.
    """

    class DummyError(Exception):
        pass

    # Wir patchen das interne _get_chat_model, um eine Exception beim invoke zu erzwingen.
    class DummyModel:
        def invoke(self, *_, **__):
            raise DummyError("Boom")

    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")

    def fake_get_chat_model(model: str, temperature: float | None):
        return DummyModel()

    monkeypatch.setattr(llm_factory, "_get_chat_model", fake_get_chat_model)

    text = llm_factory.run_llm(
        model="gpt-4.1-mini",
        prompt="Irgendein Prompt",
        system="System prompt",
        temperature=0.3,
        max_tokens=50,
    )

    # Die Fallback-Nachricht aus run_llm sollte lesbar und stabil sein.
    assert "Entschuldigung" in text
    assert "Fehler" in text
