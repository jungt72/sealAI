"""
Unit-Tests für Jinja2-Prompt-Templates – Best Practices

Testet Rendering, Validierung und Kontext-Normalisierung.
Verwendet pytest.
"""

import pytest
from prompt_renderer import PromptRenderer

@pytest.fixture
def renderer():
    return PromptRenderer()

def test_render_global_system_v2(renderer):
    context = {}
    result = renderer.render_with_validation("global_system_v2.jinja2", "Test", context)
    assert "SealAI" in result
    assert "2024-" in result  # Datum
    assert "{{" not in result  # Keine Platzhalter

def test_render_material_agent_v2(renderer):
    context = {}
    result = renderer.render_with_validation("material_agent_v2.jinja2", "Erkläre PTFE", context)
    assert "PTFE" in result or "Anfrage" in result
    assert "detailed_explanation" in result  # Normalisiert
    assert "Halluzinationen" in result  # Anti-Halluzination

def test_render_explain_v2(renderer):
    context = {"main": {"typ": "Dichtung", "werkstoff": "PTFE"}}
    result = renderer.render_with_validation("explain_v2.jinja2", "Empfehlung", context)
    assert "Dichtung" in result
    assert "PTFE" in result

def test_normalization(renderer):
    normalized = renderer.normalize_context("Gib mir details zu PTFE", {})
    assert normalized['request_type'] == 'detailed_explanation'
    assert normalized['query'] == "Gib mir details zu PTFE"

def test_validation_error(renderer):
    # Simuliere unvollständige Ersetzung
    with pytest.raises(ValueError):
        # Manuell einen Template-String mit Platzhalter erstellen
        template = renderer.env.from_string("Test {{ undefined }}")
        template.render()

# Lauf mit: pytest test_prompts.py