"""L1 Generator — the trust-spine layer that covers the infinite answer space (build-spec §4).

Pure orchestration: assemble the system prompt (via an injected assembler), call the injected
LLM client, wrap the result. No I/O of its own — the client is the only I/O (``core`` stays
framework-/I/O-free, build-spec §3).
"""

from __future__ import annotations

from sealai_v2.core.contracts import (
    Answer,
    Flags,
    GroundingFact,
    LlmClient,
    ModelConfig,
    SystemPromptAssembler,
)


class L1Generator:
    def __init__(
        self,
        client: LlmClient,
        assembler: SystemPromptAssembler,
        model_config: ModelConfig,
    ) -> None:
        self._client = client
        self._assembler = assembler
        self._model_config = model_config

    async def generate(
        self,
        question: str,
        *,
        flags: Flags,
        grounding_facts: tuple[GroundingFact, ...] = (),
        case_context: list[dict] | None = None,
        correction_note: str | None = None,
    ) -> Answer:
        system = self._assembler.system_prompt(
            anrede="du",
            grounding_facts=list(grounding_facts),
            case_context=case_context,
            flags=flags,
            correction_note=correction_note,
        )
        result = await self._client.generate(
            system=system, user=question, model_config=self._model_config
        )
        return Answer(
            text=result.text,
            model=result.model,
            grounding_facts=grounding_facts,
            finish_reason=result.finish_reason,
        )
