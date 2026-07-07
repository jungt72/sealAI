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

from dataclasses import dataclass

from sealai_v2.core.contracts import Answer, LlmClient, ModelConfig
from sealai_v2.core.sourcing_guard import strip_sourcing
from sealai_v2.prompts.assembler import SmalltalkNavigationPromptAssembler


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
