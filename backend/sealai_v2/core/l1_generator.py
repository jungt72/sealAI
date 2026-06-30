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
from sealai_v2.core.sourcing_guard import strip_sourcing


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
            "inputs_used": list(c.inputs_used),
            "input_origins": list(c.input_origins),  # M8-A: provenance visible to L1
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

    def doctrine_system_prompt(self, *, flags: Flags) -> str:
        """P1.4: the STATIC doctrine system prompt (flags only — NO grounding, calc, memory or
        correction_note), exposed so the SERVE-path deterministic exfiltration gate can use the
        confidential doctrine as its leak reference. This MIRRORS the eval's reference
        (``eval/harness`` builds ``PromptAssembler().system_prompt(flags=...)``), so the SERVE gate
        and the eval gate score against the byte-identical doctrine surface. Using the doctrine-only
        prompt (not the per-turn assembly) is also what AVOIDS a false-positive: the live prompt
        legitimately embeds reviewed correction facts that a deterministic L3 hedge is allowed to
        state verbatim. KB-claim dumps are covered by the gate's separate ``kb_claims`` channel.
        Pure: the assembler is injected (``core`` stays I/O-free)."""
        return self._assembler.system_prompt(flags=flags)

    async def generate(
        self,
        question: str,
        *,
        flags: Flags,
        grounding_facts: tuple[GroundingFact, ...] = (),
        case_context: list[dict] | None = None,
        durable_context: list[dict] | None = None,
        conversation_window: list[dict] | None = None,
        correction_note: str | None = None,
        calc: CalcResult | None = None,
        untrusted: list[dict] | None = None,
        archetype_context: dict | None = None,
        coverage: dict | None = None,
        contract: dict | None = None,
        baseline_hardening: bool = False,
    ) -> Answer:
        computed_values, not_computed, calc_notes = _calc_payload(calc)
        system = self._assembler.system_prompt(
            anrede="du",
            grounding_facts=list(grounding_facts),
            case_context=case_context,
            durable_context=durable_context,
            conversation_window=conversation_window,
            flags=flags,
            correction_note=correction_note,
            computed_values=computed_values,
            not_computed=not_computed,
            calc_notes=calc_notes,
            untrusted=untrusted,
            archetype_context=archetype_context,
            coverage=coverage,
            contract=contract,
            baseline_hardening=baseline_hardening,
        )
        result = await self._client.generate(
            system=system, user=question, model_config=self._model_config
        )
        return Answer(
            text=strip_sourcing(result.text),
            model=result.model,
            grounding_facts=grounding_facts,
            finish_reason=result.finish_reason,
        )
