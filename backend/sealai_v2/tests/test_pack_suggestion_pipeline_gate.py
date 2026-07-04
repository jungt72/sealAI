"""2026-07-04 routing/extraction audit — Pipeline._pack_suggestion_context /
_medium_hint_context gate correctly on the flag AND on the Understanding annotation, mirroring
_archetype_context's own None-safety precisely (flag off / no understanding / no annotation -> None,
so the byte-identical no-suggestion path is never accidentally perturbed)."""

from __future__ import annotations

from sealai_v2.core.contracts import Intent, ModelConfig, Understanding
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.tests._fakes import FakeLlmClient


def _pipeline(*, pack_suggestion_enabled: bool) -> Pipeline:
    client = FakeLlmClient("ANTWORT")
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        pack_suggestion_enabled=pack_suggestion_enabled,
    )


_UNDERSTANDING_WITH_BOTH = Understanding(
    intent=Intent.FALLARBEIT,
    rationale="x",
    suggested_seal_type="hydraulik",
    medium_hint="Teig",
)


def test_pack_suggestion_context_none_when_flag_off():
    p = _pipeline(pack_suggestion_enabled=False)
    assert p._pack_suggestion_context(_UNDERSTANDING_WITH_BOTH) is None


def test_medium_hint_context_none_when_flag_off():
    p = _pipeline(pack_suggestion_enabled=False)
    assert p._medium_hint_context(_UNDERSTANDING_WITH_BOTH) is None


def test_pack_suggestion_context_none_when_understanding_is_none():
    p = _pipeline(pack_suggestion_enabled=True)
    assert p._pack_suggestion_context(None) is None


def test_medium_hint_context_none_when_understanding_is_none():
    p = _pipeline(pack_suggestion_enabled=True)
    assert p._medium_hint_context(None) is None


def test_pack_suggestion_context_none_when_no_suggestion_annotated():
    p = _pipeline(pack_suggestion_enabled=True)
    u = Understanding(intent=Intent.FALLARBEIT, rationale="x")
    assert p._pack_suggestion_context(u) is None


def test_medium_hint_context_none_when_no_hint_annotated():
    p = _pipeline(pack_suggestion_enabled=True)
    u = Understanding(intent=Intent.FALLARBEIT, rationale="x")
    assert p._medium_hint_context(u) is None


def test_pack_suggestion_context_populated_when_flag_on_and_suggestion_present():
    p = _pipeline(pack_suggestion_enabled=True)
    assert p._pack_suggestion_context(_UNDERSTANDING_WITH_BOTH) == {
        "seal_type": "hydraulik"
    }


def test_medium_hint_context_populated_when_flag_on_and_hint_present():
    p = _pipeline(pack_suggestion_enabled=True)
    assert p._medium_hint_context(_UNDERSTANDING_WITH_BOTH) == {"medium_hint": "Teig"}
