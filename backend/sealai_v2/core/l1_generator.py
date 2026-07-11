"""L1 Generator — the trust-spine layer that covers the infinite answer space (build-spec §4).

Pure orchestration: assemble the system prompt (via an injected assembler), call the injected
LLM client, wrap the result. No I/O of its own — the client is the only I/O (``core`` stays
framework-/I/O-free, build-spec §3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from sealai_v2.core.contracts import (
    Answer,
    CalcResult,
    Flags,
    GroundingFact,
    LlmClient,
    ModelConfig,
    SystemPromptAssembler,
)
from sealai_v2.core.technical_answer import (
    TechnicalAnswer,
    TechnicalAnswerValidationError,
    calibrate_technical_answer,
    validate_technical_answer,
)
from sealai_v2.core.sourcing_guard import strip_sourcing
from sealai_v2.llm.structured import StructuredOutputError, generate_structured
from sealai_v2.render.technical_answer import render_technical_answer


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


@dataclass(frozen=True)
class L1StreamEvent:
    """One item from ``L1Generator.generate_stream`` (Phase 3B, draft-token streaming): EITHER a RAW
    text delta (``delta`` set, ``answer`` None) forwarded verbatim from the client stream, OR the
    terminal event (``answer`` set, ``delta`` None) carrying the finished, ``strip_sourcing``-cleaned
    Answer. Deltas stream RAW — never per-delta stripped (stripping a fragment mid-token would corrupt
    it); ``strip_sourcing`` is applied to the FULL accumulated final text ONCE, so the terminal
    ``answer`` is byte-identical to what the non-streaming ``generate`` returns for the same completion
    + the same inputs. Exactly one terminal event per SUCCESSFUL stream, always yielded LAST; a
    mid-stream exception propagates unchanged (a failed stream is a failed call — no partial/synthetic
    Answer is ever emitted, identical to ``generate``'s and ``LlmStreamEvent``'s failure contract).

    This mirrors ``pipeline.smalltalk_generator.SmalltalkStreamEvent`` exactly, but for the full L1
    engineering generator. It is a pure OBSERVABILITY channel: the terminal ``answer`` still goes
    through the UNCHANGED output_guard + L3 verify pipeline downstream — draft deltas are never
    treated as, or substituted for, the delivered/verified answer."""

    delta: str | None = None
    answer: Answer | None = None


class L1Generator:
    def __init__(
        self,
        client: LlmClient,
        assembler: SystemPromptAssembler,
        model_config: ModelConfig,
        *,
        structured_output_enabled: bool = False,
    ) -> None:
        self._client = client
        self._assembler = assembler
        self._model_config = model_config
        self._structured_output_enabled = structured_output_enabled

    @property
    def supports_token_streaming(self) -> bool:
        return not self._structured_output_enabled

    def with_reasoning_effort(self, effort: str | None) -> "L1Generator":
        """Return a turn-scoped generator without mutating the shared pipeline object."""
        return L1Generator(
            self._client,
            self._assembler,
            replace(self._model_config, reasoning_effort=effort),
            structured_output_enabled=self._structured_output_enabled,
        )

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

    def _assemble_system(
        self,
        *,
        flags: Flags,
        grounding_facts: tuple[GroundingFact, ...],
        case_context: list[dict] | None,
        durable_context: list[dict] | None,
        conversation_window: list[dict] | None,
        correction_note: str | None,
        calc: CalcResult | None,
        untrusted: list[dict] | None,
        archetype_context: dict | None,
        pack_suggestion_context: dict | None,
        medium_hint_context: dict | None,
        coverage: dict | None,
        contract: dict | None,
        baseline_hardening: bool,
        material_params: list | None,
        knowledge_answer_plan: dict | None,
        risk_flags: list[str] | None,
    ) -> str:
        """The SINGLE prompt-assembly path shared by ``generate`` and ``generate_stream`` so the two
        can never drift: streaming assembles a byte-identical system prompt to the non-streaming call
        for the same inputs, guaranteeing the streamed draft is generated from the exact same prompt
        as the delivered answer would be."""
        computed_values, not_computed, calc_notes = _calc_payload(calc)
        return self._assembler.system_prompt(
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
            pack_suggestion_context=pack_suggestion_context,
            medium_hint_context=medium_hint_context,
            coverage=coverage,
            contract=contract,
            baseline_hardening=baseline_hardening,
            material_params=material_params,
            knowledge_answer_plan=knowledge_answer_plan,
            risk_flags=risk_flags,
        )

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
        pack_suggestion_context: dict | None = None,
        medium_hint_context: dict | None = None,
        coverage: dict | None = None,
        contract: dict | None = None,
        baseline_hardening: bool = False,
        material_params: list | None = None,
        knowledge_answer_plan: dict | None = None,
        risk_flags: list[str] | None = None,
        case_revision: int = 0,
    ) -> Answer:
        system = self._assemble_system(
            flags=flags,
            grounding_facts=grounding_facts,
            case_context=case_context,
            durable_context=durable_context,
            conversation_window=conversation_window,
            correction_note=correction_note,
            calc=calc,
            untrusted=untrusted,
            archetype_context=archetype_context,
            pack_suggestion_context=pack_suggestion_context,
            medium_hint_context=medium_hint_context,
            coverage=coverage,
            contract=contract,
            baseline_hardening=baseline_hardening,
            material_params=material_params,
            knowledge_answer_plan=knowledge_answer_plan,
            risk_flags=risk_flags,
        )
        if self._structured_output_enabled:
            claim_level_evidence = knowledge_answer_plan is not None
            evidence_facts: dict[str, GroundingFact] = {}
            for fact in grounding_facts:
                evidence_id = (
                    (fact.claim_id or fact.card_id)
                    if claim_level_evidence
                    else fact.card_id
                )
                if evidence_id:
                    evidence_facts[evidence_id] = fact
            allowed_ids = frozenset(evidence_facts)
            required_knowledge_facets: set[str] = set()
            evidence_facets: dict[str, set[str]] = {}
            if knowledge_answer_plan is not None:
                from sealai_v2.core.knowledge_answer import facets_for_fact

                required_knowledge_facets = {
                    str(facet)
                    for section in knowledge_answer_plan.get("sections", ())
                    for facet in section.get("covered_facets", ())
                    if str(facet)
                }
                for evidence_id, fact in evidence_facts.items():
                    evidence_facets.setdefault(evidence_id, set()).update(
                        facets_for_fact(fact)
                    )
            structured_instruction = (
                "\n\nCreate the internal TechnicalAnswer object. Do not write user-facing "
                "Markdown. Use only these evidence_ids: "
                f"{', '.join(sorted(allowed_ids)) or '(none)'}. "
                f"case_revision must be {case_revision}. A decision_relevant claim must carry "
                "at least one allowed evidence_id. Never invent evidence IDs or tool results."
            )
            if knowledge_answer_plan is not None:
                structured_instruction += (
                    " This is a pure engineering knowledge answer: every technical claim must "
                    "carry at least one allowed evidence_id. Do not add named fillers, standards, "
                    "regulations, approvals, tests, products, values, or limits that are absent "
                    "from the supplied evidence/material parameters. Set recommendation.status "
                    "to none with an empty summary and no conditions; selection inputs belong in "
                    "the evidenced claims, not in a recommendation block."
                )
                if required_knowledge_facets:
                    facet_map = "; ".join(
                        f"{evidence_id}=>{','.join(sorted(facets)) or 'none'}"
                        for evidence_id, facets in evidence_facets.items()
                    )
                    structured_instruction += (
                        " Across all claims, the cited evidence_ids must collectively cover every "
                        "required engineering facet. Required facets: "
                        f"{', '.join(sorted(required_knowledge_facets))}. "
                        f"Evidence facet map: {facet_map}. Multiple evidence_ids may be attached "
                        "to one claim when that claim faithfully combines their content."
                    )

            async def _call(current_system: str):
                technical, result = await generate_structured(
                    self._client,
                    output_type=TechnicalAnswer,
                    schema_name="sealingai_technical_answer_v1",
                    system=current_system,
                    user=question,
                    model_config=self._model_config,
                    max_repairs=0,
                )
                technical = calibrate_technical_answer(technical)
                if knowledge_answer_plan is not None:
                    technical = technical.model_copy(
                        update={
                            "recommendation": technical.recommendation.model_copy(
                                update={
                                    "summary": "",
                                    "status": "none",
                                    "conditions": [],
                                }
                            )
                        }
                    )
                validate_technical_answer(
                    technical,
                    case_revision=case_revision,
                    allowed_evidence_ids=allowed_ids,
                    require_evidence_for_all_claims=knowledge_answer_plan is not None,
                )
                if required_knowledge_facets:
                    used_evidence = {
                        evidence_id
                        for claim in technical.claims
                        for evidence_id in claim.evidence_ids
                    }
                    covered_facets = {
                        facet
                        for evidence_id in used_evidence
                        for facet in evidence_facets.get(evidence_id, ())
                    }
                    missing_facets = required_knowledge_facets - covered_facets
                    if missing_facets:
                        raise TechnicalAnswerValidationError(
                            "knowledge_facet_coverage:"
                            + ",".join(sorted(missing_facets))
                        )
                return technical, result

            try:
                technical, result = await _call(system + structured_instruction)
            except (StructuredOutputError, TechnicalAnswerValidationError) as exc:
                repair = (
                    "\n\nThe previous object failed deterministic validation "
                    f"({exc}). Repair it once. Return exactly one schema-valid "
                    "TechnicalAnswer and obey the allowed evidence IDs and case revision."
                )
                technical, result = await _call(
                    system + structured_instruction + repair
                )
            return Answer(
                text=strip_sourcing(render_technical_answer(technical)),
                model=result.model,
                grounding_facts=grounding_facts,
                finish_reason=result.finish_reason,
                verification_claims=tuple(
                    claim.text
                    for claim in sorted(
                        technical.claims,
                        key=lambda claim: claim.criticality != "decision_relevant",
                    )
                ),
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

    async def generate_stream(
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
        pack_suggestion_context: dict | None = None,
        medium_hint_context: dict | None = None,
        coverage: dict | None = None,
        contract: dict | None = None,
        baseline_hardening: bool = False,
        material_params: list | None = None,
        knowledge_answer_plan: dict | None = None,
        risk_flags: list[str] | None = None,
        case_revision: int = 0,
    ) -> AsyncIterator[L1StreamEvent]:
        """Streaming variant of ``generate`` (Phase 3B, draft-token streaming). IDENTICAL keyword-arg
        signature and IDENTICAL prompt assembly (both go through ``_assemble_system``), but calls the
        client's ``generate_stream`` instead of ``generate``. Forwards each RAW content delta as an
        ``L1StreamEvent(delta=...)``, then yields exactly ONE terminal ``L1StreamEvent(answer=...)``
        whose Answer applies ``strip_sourcing`` to the FINAL accumulated text only — byte-identical to
        ``generate``'s Answer for the same completion + inputs (proven output-equivalent by the Phase
        3B tests). A mid-stream failure propagates unchanged (no partial Answer is ever emitted).

        This is a pure observability channel: the returned terminal Answer is fed into the SAME
        output_guard + L3 verify pipeline as the non-streaming path — draft deltas never bypass, skip,
        or weaken verification, and are never substituted for the delivered answer."""
        if self._structured_output_enabled:
            yield L1StreamEvent(
                answer=await self.generate(
                    question,
                    flags=flags,
                    grounding_facts=grounding_facts,
                    case_context=case_context,
                    durable_context=durable_context,
                    conversation_window=conversation_window,
                    correction_note=correction_note,
                    calc=calc,
                    untrusted=untrusted,
                    archetype_context=archetype_context,
                    pack_suggestion_context=pack_suggestion_context,
                    medium_hint_context=medium_hint_context,
                    coverage=coverage,
                    contract=contract,
                    baseline_hardening=baseline_hardening,
                    material_params=material_params,
                    knowledge_answer_plan=knowledge_answer_plan,
                    risk_flags=risk_flags,
                    case_revision=case_revision,
                )
            )
            return

        system = self._assemble_system(
            flags=flags,
            grounding_facts=grounding_facts,
            case_context=case_context,
            durable_context=durable_context,
            conversation_window=conversation_window,
            correction_note=correction_note,
            calc=calc,
            untrusted=untrusted,
            archetype_context=archetype_context,
            pack_suggestion_context=pack_suggestion_context,
            medium_hint_context=medium_hint_context,
            coverage=coverage,
            contract=contract,
            baseline_hardening=baseline_hardening,
            material_params=material_params,
            knowledge_answer_plan=knowledge_answer_plan,
            risk_flags=risk_flags,
        )
        async for event in self._client.generate_stream(
            system=system, user=question, model_config=self._model_config
        ):
            if event.delta is not None:
                yield L1StreamEvent(delta=event.delta)
            elif event.result is not None:
                yield L1StreamEvent(
                    answer=Answer(
                        text=strip_sourcing(event.result.text),
                        model=event.result.model,
                        grounding_facts=grounding_facts,
                        finish_reason=event.result.finish_reason,
                    )
                )
