# MIGRATION: Phase-2 – Prompt existence and binding test
"""Test that all prompts exist and can be rendered with their variable contracts."""
from __future__ import annotations

import os
import pytest
from pathlib import Path

from app.langgraph.utils.jinja_renderer import JinjaRenderer


@pytest.fixture
def jinja_renderer():
    return JinjaRenderer()


@pytest.fixture
def prompts_dir():
    return Path(__file__).parent.parent / "prompts"


def test_all_configured_prompts_exist(prompts_dir):
    """Test that all prompts referenced in agents.yaml exist."""
    import yaml

    config_path = Path(__file__).parent.parent / "config" / "agents.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    missing_prompts = []

    for domain, settings in config.items():
        if "prompt" in settings:
            for prompt_type, prompt_path in settings["prompt"].items():
                if prompt_type == "variant":
                    continue
                full_path = prompts_dir / prompt_path
                if not full_path.exists():
                    missing_prompts.append(f"{domain}.{prompt_type}: {prompt_path}")

    assert not missing_prompts, f"Missing prompts: {missing_prompts}"


def test_prompt_variable_binding(jinja_renderer, prompts_dir):
    """Test that prompts can be rendered with their defined variable contracts."""
    # Test material agent prompt
    material_agent_path = prompts_dir / "material" / "material_agent.md"

    variables = {
        "user_query": "Test query for material selection",
        "messages_window": [{"role": "user", "content": "Test"}],
        "slots": {"pressure": "high", "temperature": "200C"}
    }

    try:
        result = jinja_renderer.render(str(material_agent_path), variables)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Test query for material selection" in result
    except Exception as e:
        pytest.fail(f"Failed to render material agent prompt: {e}")


def test_synthesis_prompt_binding(jinja_renderer, prompts_dir):
    """Test synthesis prompt variable binding."""
    synthesis_path = prompts_dir / "material" / "synthesis.md"

    variables = {
        "user_query": "Synthesis test query",
        "slots": {"material_type": "steel"},
        "context_refs": [
            {"kind": "rag", "id": "doc1", "meta": {"score": 0.9}}
        ],
        "tool_results_brief": [{"tool": "calculator", "result": "42"}]
    }

    try:
        result = jinja_renderer.render(str(synthesis_path), variables)
        assert isinstance(result, str)
        assert len(result) > 0
    except Exception as e:
        pytest.fail(f"Failed to render synthesis prompt: {e}")


def test_intent_projector_binding(jinja_renderer, prompts_dir):
    """Test intent projector prompt binding."""
    intent_path = prompts_dir / "intent_projector.md"

    variables = {
        "user_query": "What material for seals?",
        "messages_window": [{"role": "user", "content": "Query"}],
        "slots": {}
    }

    try:
        result = jinja_renderer.render(str(intent_path), variables)
        assert isinstance(result, str)
        assert len(result) > 0
    except Exception as e:
        pytest.fail(f"Failed to render intent projector prompt: {e}")


def test_missing_variables_raise_errors(jinja_renderer, prompts_dir):
    """Test that missing required variables raise clear errors."""
    material_agent_path = prompts_dir / "material" / "material_agent.md"

    incomplete_variables = {
        "user_query": "Test query",
        # Missing messages_window and slots
    }

    with pytest.raises(Exception):  # Should raise due to missing variables
        jinja_renderer.render(str(material_agent_path), incomplete_variables)


__all__ = []