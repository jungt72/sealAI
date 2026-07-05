"""G4 (V2.1 Inc 1) — the recognised archetype profile is injected into the L1 prompt as a new
OPTIONAL block (interview questions + blind spots), advisory only. With NO archetype the prompt is
byte-identical to before (no block) — the no-archetype no-regression guard (the eval is unperturbed
on every non-archetype turn). RED before the assembler/template accept ``archetype_context``.
"""

from __future__ import annotations

from sealai_v2.core.contracts import Flags
from sealai_v2.prompts.assembler import PromptAssembler

_CTX = {
    "archetyp": "getriebe",
    "interview_fragen": [
        "Welches Öl und welche Additivierung?",
        "Wellendurchmesser und Drehzahl?",
    ],
    "blinde_flecken": ["Öl-Additive werden unterschätzt"],
}


def test_archetype_block_present_when_context_given():
    out = PromptAssembler().system_prompt(
        flags=Flags(False, False), archetype_context=_CTX
    )
    assert "getriebe" in out
    assert "Welches Öl und welche Additivierung?" in out
    assert "Wellendurchmesser und Drehzahl?" in out
    assert "Öl-Additive werden unterschätzt" in out


def test_no_archetype_heading_on_the_no_archetype_path():
    out = PromptAssembler().system_prompt(flags=Flags(False, False))
    assert "# Erkannte Maschinen-Art" not in out


def test_absent_archetype_is_byte_identical_to_none():
    a = PromptAssembler()
    assert a.system_prompt(flags=Flags(False, False)) == a.system_prompt(
        flags=Flags(False, False), archetype_context=None
    )


def test_empty_archetype_context_renders_no_block():
    a = PromptAssembler()
    base = a.system_prompt(flags=Flags(False, False))
    assert a.system_prompt(flags=Flags(False, False), archetype_context={}) == base
