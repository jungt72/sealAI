from __future__ import annotations

from sealai_v2.core.contracts import Flags
from sealai_v2.prompts.assembler import PromptAssembler


def test_flags_off_marks_allgemeinwissen_and_no_conditional_blocks():
    p = PromptAssembler().system_prompt(
        flags=Flags(compliance_hint=False, safety_critical=False)
    )
    assert "Allgemeinwissen" in p  # grounding else-branch fires (no grounding at M1)
    assert "Sicherheitskritischer Kontext" not in p
    assert "Compliance-Dimension beachten" not in p


def test_flags_on_lights_safety_and_compliance_blocks():
    p = PromptAssembler().system_prompt(
        flags=Flags(compliance_hint=True, safety_critical=True)
    )
    assert "Sicherheitskritischer Kontext" in p
    assert "explosive Dekompression" in p
    assert "Compliance-Dimension beachten" in p


def test_anrede_defaults_to_du():
    p = PromptAssembler().system_prompt()
    assert "in der Du-Form" in p
    assert "in der Sie-Form" not in p
