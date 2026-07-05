from __future__ import annotations

from sealai_v2.prompts.assembler import (
    DistillPromptAssembler,
    FachkarteExtractPromptAssembler,
    MediumResearchPromptAssembler,
    UnderstandPromptAssembler,
    VerifierPromptAssembler,
)


def test_structured_helper_prompts_state_json_discipline():
    prompts = [
        DistillPromptAssembler().distill_prompt(),
        FachkarteExtractPromptAssembler().fachkarte_extract_prompt(),
        MediumResearchPromptAssembler().medium_research_prompt(),
        UnderstandPromptAssembler().understand_prompt(),
        VerifierPromptAssembler().verifier_system_prompt(traps=[]),
    ]

    for prompt in prompts:
        assert "gültigen JSON-Objekt" in prompt
        assert "keine Prosa" in prompt
        assert "keine Code-Fences" in prompt
        assert "keine trailing commas" in prompt


def test_understand_prompt_keeps_optional_fields_conditional():
    base = UnderstandPromptAssembler().understand_prompt()
    assert "archetype" not in base
    assert "suggested_seal_type" not in base
    assert "medium_hint" not in base

    rich = UnderstandPromptAssembler().understand_prompt(
        archetype_keys=("getriebe",),
        known_seal_types=("rwdr",),
        medium_already_known=False,
    )
    assert "archetype" in rich
    assert "suggested_seal_type" in rich
    assert "medium_hint" in rich
    assert "höchstens 12 Wörtern" in rich


def test_verifier_prompt_avoids_pseudo_json_literals():
    prompt = VerifierPromptAssembler().verifier_system_prompt(traps=[])

    assert "true|false" not in prompt
    assert "clean|violation" not in prompt
    assert '{"findings":[],"verdict":"clean"}' in prompt
