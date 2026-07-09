"""Phase 2D (LangGraph-suitability audit) — the compact smalltalk_navigation generator.

Deliberately a SEPARATE, minimal class from ``core.l1_generator.L1Generator`` — not a variant of
it, not an inheritance of it. ``L1Generator`` (the engineering trust-spine generator) is untouched
by Phase 2D; nothing here can change its behavior. This class only ever takes a bare ``question``
(no grounding/case/calc/coverage/contract/memory context) because the compact
``smalltalk_navigation.jinja`` system prompt is fully static and the route precondition
(``pipeline.routing.classify_route`` finding zero deterministic engineering signals AND a
``gespraech`` intent) already guarantees there is nothing case-relevant to pass through — passing
dynamic context here would contradict the very precondition that made this route safe to use in
the first place.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from sealai_v2.core.contracts import Answer, LlmClient, ModelConfig
from sealai_v2.core.sourcing_guard import strip_sourcing
from sealai_v2.prompts.assembler import SmalltalkNavigationPromptAssembler


@dataclass(frozen=True)
class SmalltalkStreamEvent:
    """One item from ``SmalltalkGenerator.generate_stream``: a RAW text delta (``delta`` set,
    ``answer`` None) forwarded verbatim from the LLM stream, or the terminal event (``answer`` set,
    ``delta`` None) carrying the finished, ``strip_sourcing``-cleaned authoritative Answer. Deltas
    stream RAW -- never per-delta stripped (stripping a fragment mid-token would corrupt it); the
    terminal ``answer`` is the single stripped, authoritative text, byte-identical to what the
    non-streaming ``generate`` returns for the same completion. Exactly one terminal event per
    successful stream, always last. Phase 3A (live token streaming)."""

    delta: str | None = None
    answer: Answer | None = None


@dataclass
class SmalltalkGenerator:
    client: LlmClient
    assembler: SmalltalkNavigationPromptAssembler
    model_config: ModelConfig

    async def generate(self, question: str) -> Answer:
        system = self.assembler.system_prompt()
        result = await self.client.generate(
            system=system, user=question, model_config=self.model_config
        )
        return Answer(
            text=strip_sourcing(result.text),
            model=result.model,
            grounding_facts=(),
            finish_reason=result.finish_reason,
        )

    async def generate_stream(
        self, question: str
    ) -> AsyncIterator[SmalltalkStreamEvent]:
        """Streaming variant of ``generate`` (Phase 3A): the SAME static system prompt + bare
        question + model_config, but via the client's ``generate_stream``. Forwards each RAW content
        delta as a ``SmalltalkStreamEvent(delta=...)``, then yields exactly ONE terminal
        ``SmalltalkStreamEvent(answer=...)`` whose Answer applies ``strip_sourcing`` to the FINAL
        accumulated text only -- byte-identical to ``generate``'s Answer for the same completion. A
        mid-stream failure propagates unchanged (no partial Answer is ever emitted)."""
        system = self.assembler.system_prompt()
        async for event in self.client.generate_stream(
            system=system, user=question, model_config=self.model_config
        ):
            if event.delta is not None:
                yield SmalltalkStreamEvent(delta=event.delta)
            elif event.result is not None:
                yield SmalltalkStreamEvent(
                    answer=Answer(
                        text=strip_sourcing(event.result.text),
                        model=event.result.model,
                        grounding_facts=(),
                        finish_reason=event.result.finish_reason,
                    )
                )
