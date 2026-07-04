"""2026-07-04 routing/extraction audit — the recognised pack suggestion / medium hint are injected
into the L1 prompt as new OPTIONAL blocks, advisory only (mirrors G4's archetype_context pattern
exactly). With neither present the prompt is byte-identical to before (no block) — the no-suggestion
no-regression guard (the eval is unperturbed on every turn without a suggestion/hint).
"""

from __future__ import annotations

from sealai_v2.core.contracts import Flags
from sealai_v2.prompts.assembler import PromptAssembler

_PACK_CTX = {"seal_type": "hydraulik"}
_MEDIUM_CTX = {"medium_hint": "Teig"}


def test_pack_suggestion_block_present_when_context_given():
    out = PromptAssembler().system_prompt(
        flags=Flags(False, False), pack_suggestion_context=_PACK_CTX
    )
    assert "hydraulik" in out
    assert "Vermutung" in out


def test_no_pack_suggestion_heading_on_the_no_suggestion_path():
    out = PromptAssembler().system_prompt(flags=Flags(False, False))
    assert "Möglicher Fall-Typ" not in out


def test_absent_pack_suggestion_is_byte_identical_to_none():
    a = PromptAssembler()
    assert a.system_prompt(flags=Flags(False, False)) == a.system_prompt(
        flags=Flags(False, False), pack_suggestion_context=None
    )


def test_empty_pack_suggestion_context_renders_no_block():
    a = PromptAssembler()
    base = a.system_prompt(flags=Flags(False, False))
    assert (
        a.system_prompt(flags=Flags(False, False), pack_suggestion_context={}) == base
    )


def test_medium_hint_block_present_when_context_given():
    out = PromptAssembler().system_prompt(
        flags=Flags(False, False), medium_hint_context=_MEDIUM_CTX
    )
    assert "Teig" in out
    assert "unbestätigt" in out


def test_no_medium_hint_heading_on_the_no_hint_path():
    out = PromptAssembler().system_prompt(flags=Flags(False, False))
    assert "nicht erkanntes Medium" not in out


def test_absent_medium_hint_is_byte_identical_to_none():
    a = PromptAssembler()
    assert a.system_prompt(flags=Flags(False, False)) == a.system_prompt(
        flags=Flags(False, False), medium_hint_context=None
    )


def test_empty_medium_hint_context_renders_no_block():
    a = PromptAssembler()
    base = a.system_prompt(flags=Flags(False, False))
    assert a.system_prompt(flags=Flags(False, False), medium_hint_context={}) == base


def test_both_blocks_can_coexist_with_archetype():
    # sanity: three independent optional blocks don't clobber each other
    out = PromptAssembler().system_prompt(
        flags=Flags(False, False),
        archetype_context={
            "archetyp": "getriebe",
            "interview_fragen": [],
            "blinde_flecken": [],
        },
        pack_suggestion_context=_PACK_CTX,
        medium_hint_context=_MEDIUM_CTX,
    )
    assert "getriebe" in out
    assert "hydraulik" in out
    assert "Teig" in out
