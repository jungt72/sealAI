"""Offline tests for Medium Intelligence (Phase 2) — fake client, no API. Locks the doctrine:
display-only string lists (never GroundingFacts), fail-safe on bad JSON, caching, sanitization."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.medium_research import MediumResearcher
from sealai_v2.prompts.assembler import MediumResearchPromptAssembler


class _FakeClient:
    """Records calls; returns a scripted text. Implements the .generate(...).text shape only."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    async def generate(self, *, system, user, model_config, **_kw):
        self.calls += 1
        return SimpleNamespace(text=self._text)


_CFG = ModelConfig(model="fake", temperature=0.0)
_GOOD = """{
  "eigenschaften": ["stark sauer/oxidierend", "korrosiv gegenüber Metallen"],
  "herausforderungen": ["Versprödung vieler Elastomere", "Spaltkorrosion an Metallteilen"],
  "werkstoff_tendenz": ["eher FFKM/PTFE, da hohe Chemikalienbeständigkeit"],
  "unsicher": false
}"""


def _researcher(text: str) -> tuple[MediumResearcher, _FakeClient]:
    c = _FakeClient(text)
    return MediumResearcher(c, MediumResearchPromptAssembler(), _CFG), c


def test_parses_grouped_string_lists():
    r, _c = _researcher(_GOOD)
    mi = asyncio.run(r.research("Salzsäure 30%", "Sonstiges"))
    assert mi.eigenschaften and mi.herausforderungen and mi.werkstoff_tendenz
    assert "stark sauer/oxidierend" in mi.eigenschaften
    assert mi.medium == "Salzsäure 30%" and mi.kategorie == "Sonstiges"
    assert not mi.empty


def test_caches_per_medium_no_second_llm_call():
    r, c = _researcher(_GOOD)
    asyncio.run(r.research("Salzsäure", "Sonstiges"))
    asyncio.run(r.research("salzsäure", "sonstiges"))  # case-insensitive key
    assert c.calls == 1


def test_fail_safe_on_bad_json_yields_empty():
    r, _c = _researcher("das ist kein JSON, nur Prosa")
    mi = asyncio.run(r.research("Wasser", "Wasser"))
    assert mi.empty and mi.eigenschaften == ()


def test_sanitizes_caps_and_dedupes():
    text = (
        '{"eigenschaften": ["a","a","b","c","d","e","f"], '
        '"herausforderungen": [123, "x"], "werkstoff_tendenz": [], "unsicher": true}'
    )
    r, _c = _researcher(text)
    mi = asyncio.run(r.research("Testmedium"))
    assert len(mi.eigenschaften) == 4  # capped
    assert mi.eigenschaften.count("a") == 1  # de-duped
    assert mi.herausforderungen == ("x",)  # non-str dropped
    assert mi.unsicher is True


def test_empty_medium_is_inert():
    r, c = _researcher(_GOOD)
    mi = asyncio.run(r.research("  "))
    assert mi.empty and c.calls == 0


def test_prompt_assembler_renders_doctrine():
    p = MediumResearchPromptAssembler().medium_research_prompt()
    assert "vorläufig" in p and "Erfinde keine präzisen Zahlen" in p and "JSON" in p
