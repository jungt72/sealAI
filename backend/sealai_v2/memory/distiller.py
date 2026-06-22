"""Memory distiller (build-spec §7, layer 2) — light LLM extraction of STATED case facts.

CONSERVATIVE by contract: extracts only what the USER explicitly stated (no inference, no
recommendations, nothing the assistant said). The distilled facts are REMEMBERED-CLAIMS
(provenance ``distilled-from-conversation``), never reviewed/authoritative — distinct from the
reviewed Fachkarten the verifier may correct from.

The distillation is an LLM step → a fact-corruption vector, so it FAILS SAFE: a parse failure or
an empty result yields NO facts rather than a guessed one (never corrupt the case-state). Pure
orchestration over the injected client + assembler — no I/O of its own (the client is the I/O).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from sealai_v2.core.contracts import LlmClient, ModelConfig, RememberedFact
from sealai_v2.memory.integrity import numerics


class DistillPrompt(Protocol):
    """Structural type for the distill prompt assembler (``prompts.DistillPromptAssembler``)."""

    def distill_prompt(self) -> str: ...


@dataclass(frozen=True)
class DistillStats:
    """Runtime drop observability (owner addition 1): the numeric guard is also a measurement
    instrument. ``proposed`` = well-formed facts the LLM distilled; ``dropped`` = those the
    numeric-trace guard removed before the store. ``drop_rate`` ≈ 0 ⇒ the conservative distiller
    works; high ⇒ it fabricates numbers and is only being rescued (a quality signal, never hidden)."""

    proposed: int
    dropped: int

    @property
    def drop_rate(self) -> float:
        return self.dropped / self.proposed if self.proposed else 0.0


def _extract_json(raw: str) -> str:
    """Best-effort: pull the first {...} block, tolerating code fences (mirrors ``stages``)."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if "\n" in s:
            s = s.split("\n", 1)[1]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


class Distiller:
    def __init__(
        self, client: LlmClient, assembler: DistillPrompt, model_config: ModelConfig
    ) -> None:
        self._client = client
        self._assembler = assembler
        self._model_config = model_config
        # drop observability (owner addition 1): accumulate across this distiller's lifetime.
        self._proposed = 0
        self._dropped = 0

    @property
    def stats(self) -> DistillStats:
        return DistillStats(proposed=self._proposed, dropped=self._dropped)

    async def distill(
        self, *, question: str, answer: str = ""
    ) -> tuple[RememberedFact, ...]:
        """Extract user-stated facts from THIS turn's user message. ``answer`` is intentionally
        unused (conservative: assistant content is never a remembered fact) — kept in the signature
        so capturing the system's recommendation as a remembered claim can be added later without a
        call-site change."""
        res = await self._client.generate(
            system=self._assembler.distill_prompt(),
            user=question,
            model_config=self._model_config,
        )
        return self._trace_numerics(self._parse(res.text), question)

    def _trace_numerics(
        self, facts: tuple[RememberedFact, ...], source: str
    ) -> tuple[RememberedFact, ...]:
        """(c)(i) runtime fail-closed: drop any fact whose numerics don't trace to the user's
        text — the distiller-fabrication vector (e.g. 150→1500 °C) made un-representable. A
        distorted number is the memory analogue of confident-false, so we never carry it forward.
        Qualitative facts (no numerics) pass here — their support is judged/human-final on dispute.

        Also feeds the drop counters (observability): every well-formed fact is ``proposed``; the
        untraceable ones are ``dropped`` — the rate measures the distiller's raw fabrication."""
        src = numerics(source)
        kept: list[RememberedFact] = []
        for f in facts:
            self._proposed += 1
            if numerics(f.wert) <= src:
                kept.append(f)
            else:
                self._dropped += 1
        return tuple(kept)

    @staticmethod
    def _parse(raw: str) -> tuple[RememberedFact, ...]:
        try:
            data = json.loads(_extract_json(raw))
            facts: list[RememberedFact] = []
            for it in data.get("facts", []):
                feld = str(it.get("feld", "")).strip()
                wert = str(it.get("wert", "")).strip()
                if feld and wert:  # skip incomplete entries
                    facts.append(RememberedFact(feld=feld, wert=wert))
            return tuple(facts)
        except (ValueError, KeyError, TypeError, AttributeError):
            return ()  # fail safe — never corrupt the case-state with a guessed fact
