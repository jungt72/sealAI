from __future__ import annotations

import pytest
from jinja2 import UndefinedError

from app.agent.prompts import (
    FAST_GUIDANCE_PROMPT_HASH,
    FAST_GUIDANCE_PROMPT_TEMPLATE_ID,
    build_fast_guidance_prompt,
    prompts,
)
from app.agent.v92.prompt_audit import build_prompt_trace


def test_fast_guidance_prompt_is_rendered_from_registry_template() -> None:
    rendered = build_fast_guidance_prompt(
        "FactCard: EPDM ist nur eine Materialfamilie.",
        "guided_recommendation",
        history="User fragt nach Hydrauliköl.",
        current_params="medium=HLP46",
    )

    assert FAST_GUIDANCE_PROMPT_TEMPLATE_ID == "fast/guidance.j2"
    assert FAST_GUIDANCE_PROMPT_TEMPLATE_ID in prompts.list_templates()
    assert FAST_GUIDANCE_PROMPT_HASH
    assert "FactCard: EPDM" in rendered
    assert "medium=HLP46" in rendered
    assert "Orientierende Einschätzung" in rendered
    assert "{context}" not in rendered


def test_fast_guidance_prompt_uses_strict_undefined() -> None:
    with pytest.raises(UndefinedError):
        prompts.render(
            FAST_GUIDANCE_PROMPT_TEMPLATE_ID,
            {
                "context": "ctx",
                "answer_mode": "mode",
                "history": "history",
            },
        )


def test_v92_governed_prompt_templates_are_registered() -> None:
    templates = set(prompts.list_templates())

    assert "governed/adversarial_reviewer.j2" in templates
    assert "governed/revision_composer.j2" in templates
    assert "knowledge/answer_composer.j2" in templates
    assert "medium/answer_composer.j2" in templates
    assert "communication/human_layer.j2" in templates


def test_prompt_trace_contains_hash_metadata_without_raw_prompt() -> None:
    trace = build_prompt_trace(
        prompt_template_id="governed/answer_composer.j2",
        prompt_template_version="sealai_governed_answer_composer_v2",
        messages=[
            {"role": "system", "content": "system with sensitive customer facts"},
            {"role": "user", "content": "user payload"},
        ],
        input_schema_version="Input.v1",
        output_schema_version="Output.v1",
        model_role="governed_answer_composer",
        case_revision=3,
        trace_id="trace_123",
    )

    payload = trace.model_dump(mode="json")
    assert payload["rendered_prompt_hash"]
    assert "sensitive customer facts" not in str(payload)
    assert payload["case_revision"] == 3
