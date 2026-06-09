"""L1 Generator — the trust-spine layer that covers the infinite answer space (build-spec §4).

Pure orchestration: assemble the system prompt (via an injected assembler), call the injected
LLM client, wrap the result. No I/O of its own — the client is the only I/O (``core`` stays
framework-/I/O-free, build-spec §3).
"""

from __future__ import annotations

from sealai_v2.core.contracts import (
    Answer,
    CalcResult,
    Flags,
    GroundingFact,
    LlmClient,
    ModelConfig,
    SystemPromptAssembler,
)


def _calc_payload(calc: CalcResult | None) -> tuple[list[dict], list[dict], list[str]]:
    """Flatten a CalcResult into template data: computed values, not-computed reasons, notes."""
    if calc is None:
        return [], [], []
    computed = [
        {
            "name": c.name,
            "value": c.value,
            "unit": c.unit,
            "formula": c.formula,
            "stage": c.stage,
            "estimate": c.estimate,
            "assumptions": list(c.assumptions),
            "warnings": list(c.warnings),
        }
        for c in calc.computed
    ]
    not_computed = [
        {"calc_id": n.calc_id, "reason": n.reason} for n in calc.not_computed
    ]
    return computed, not_computed, list(calc.notes)


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
        conversation_window: list[dict] | None = None,
        correction_note: str | None = None,
        calc: CalcResult | None = None,
    ) -> Answer:
        computed_values, not_computed, calc_notes = _calc_payload(calc)
        system = self._assembler.system_prompt(
            anrede="du",
            grounding_facts=list(grounding_facts),
            case_context=case_context,
            conversation_window=conversation_window,
            flags=flags,
            correction_note=correction_note,
            computed_values=computed_values,
            not_computed=not_computed,
            calc_notes=calc_notes,
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
