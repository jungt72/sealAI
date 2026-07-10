"""Medium Intelligence (Phase 2, build-spec §3 owner feature) — light LLM research of ANY stated
medium → its sealing-relevant properties + the challenges it poses, so the MEDIUM tab (and, later, the
optimal-solution evaluation) sees medium-specific context even for media ABSENT from the reviewed
knowledge (most media).

DOCTRINE GUARDRAIL (keine Halluzinationen): the research is LLM knowledge, so it is DISPLAY DATA that is
**vorläufig** by construction — never a ``GroundingFact`` (the quarantine keystone reserves that type for
the reviewed grounding lanes), never authoritative, never fed into the L1/L3 prompt. Reviewed §4 matrix
cells + reviewed Fachkarten remain the sole authority. Mirrors the conservative Distiller: an LLM step is
a fact-corruption vector, so a parse failure or empty result yields NOTHING (never a guessed fact). Pure
orchestration over the injected helper client; cached per (medium, kategorie) so a multi-turn case pays
the helper call once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sealai_v2.core.contracts import LlmClient, ModelConfig
from sealai_v2.llm.structured import StructuredOutputError, generate_structured

_MAX = {"eigenschaften": 4, "herausforderungen": 4, "werkstoff_tendenz": 3}
_MAX_LEN = 240  # a sealing-relevant bullet, not an essay


class MediumResearchPrompt(Protocol):
    def medium_research_prompt(self) -> str: ...


@dataclass(frozen=True)
class MediumIntelligence:
    """Display payload for the MEDIUM tab — plain string lists, intrinsically ``vorläufig`` (helper-LLM
    knowledge). Deliberately NOT ``GroundingFact``s: this never enters the grounding/L1/L3 lanes."""

    medium: str
    kategorie: str
    eigenschaften: tuple[str, ...] = ()
    herausforderungen: tuple[str, ...] = ()
    werkstoff_tendenz: tuple[str, ...] = ()
    unsicher: bool = False

    @property
    def empty(self) -> bool:
        return not (
            self.eigenschaften or self.herausforderungen or self.werkstoff_tendenz
        )


class _MediumResearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eigenschaften: list[str] = Field(default_factory=list, max_length=4)
    herausforderungen: list[str] = Field(default_factory=list, max_length=4)
    werkstoff_tendenz: list[str] = Field(default_factory=list, max_length=3)
    unsicher: bool = False

    @field_validator(
        "eigenschaften", "herausforderungen", "werkstoff_tendenz", mode="before"
    )
    @classmethod
    def _sanitize_provider_list(cls, value, info):
        limits = {
            "eigenschaften": 4,
            "herausforderungen": 4,
            "werkstoff_tendenz": 3,
        }
        if not isinstance(value, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str) or item.lower() in seen:
                continue
            seen.add(item.lower())
            result.append(item)
            if len(result) >= limits[info.field_name]:
                break
        return result


def _clean_list(value, limit: int) -> tuple[str, ...]:
    """Sanitize one LLM list field: strings only, stripped, length-capped, de-duped, count-capped."""
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        t = " ".join(item.split())[:_MAX_LEN].strip()
        key = t.lower()
        if t and key not in seen:
            seen.add(key)
            out.append(t)
        if len(out) >= limit:
            break
    return tuple(out)


class MediumResearcher:
    """Researches a stated medium via the helper LLM → a ``MediumIntelligence`` display payload.
    Fails safe (empty on any parse/LLM error). Caches per (medium, kategorie) for the case lifetime."""

    def __init__(
        self,
        client: LlmClient,
        assembler: MediumResearchPrompt,
        model_config: ModelConfig,
    ) -> None:
        self._client = client
        self._assembler = assembler
        self._model_config = model_config
        self._cache: dict[tuple[str, str], MediumIntelligence] = {}

    async def research(self, medium: str, kategorie: str = "") -> MediumIntelligence:
        medium = (medium or "").strip()
        kategorie = (kategorie or "").strip()
        if not medium:
            return MediumIntelligence(medium="", kategorie=kategorie)
        key = (medium.lower(), kategorie.lower())
        if key in self._cache:
            return self._cache[key]
        result = await self._research_uncached(medium, kategorie)
        self._cache[key] = result
        return result

    async def _research_uncached(
        self, medium: str, kategorie: str
    ) -> MediumIntelligence:
        user = f"Medium: {medium}" + (f" (Kategorie: {kategorie})" if kategorie else "")
        try:
            data, _ = await generate_structured(
                self._client,
                output_type=_MediumResearchOutput,
                schema_name="sealingai_medium_research",
                system=self._assembler.medium_research_prompt(),
                user=user,
                model_config=self._model_config,
            )
        except StructuredOutputError:
            return MediumIntelligence(medium=medium, kategorie=kategorie)  # fail safe

        return MediumIntelligence(
            medium=medium,
            kategorie=kategorie,
            eigenschaften=_clean_list(data.eigenschaften, _MAX["eigenschaften"]),
            herausforderungen=_clean_list(
                data.herausforderungen, _MAX["herausforderungen"]
            ),
            werkstoff_tendenz=_clean_list(
                data.werkstoff_tendenz, _MAX["werkstoff_tendenz"]
            ),
            unsicher=data.unsicher,
        )
