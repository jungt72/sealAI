"""L1 Generator — the trust-spine layer that covers the infinite answer space (build-spec §4).

Pure orchestration: assemble the system prompt (via an injected assembler), call the injected
LLM client, wrap the result. No I/O of its own — the client is the only I/O (``core`` stays
framework-/I/O-free, build-spec §3).
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from sealai_v2.core.contracts import (
    Answer,
    CalcResult,
    Flags,
    GroundingFact,
    LlmClient,
    LlmResult,
    ModelConfig,
    SystemPromptAssembler,
)
from sealai_v2.core.engineering_answer import (
    EngineeringAnswerValidationError,
    EngineeringClaim,
    EngineeringKnowledgeAnswer,
    validate_engineering_answer,
)
from sealai_v2.core.technical_answer import (
    TechnicalAnswer,
    TechnicalClaim,
    TechnicalAnswerValidationError,
    calibrate_technical_answer,
    validate_technical_answer,
)
from sealai_v2.core.sourcing_guard import strip_sourcing
from sealai_v2.llm.structured import StructuredOutputError, generate_structured
from sealai_v2.render.engineering_answer import render_engineering_answer
from sealai_v2.render.technical_answer import render_technical_answer


logger = logging.getLogger(__name__)


def _engineering_conclusion(plan: dict) -> str:
    subjects = tuple(
        str(subject) for subject in plan.get("subjects", ()) if str(subject)
    )
    profile = str(plan.get("profile") or "engineering_knowledge")
    if plan.get("comparison") and len(subjects) >= 2:
        return (
            f"{subjects[0]} und {subjects[1]} sind entlang identischer Prüf- und Betriebsbedingungen "
            "zu vergleichen; ein einzelner Kennwert ergibt noch keine belastbare Werkstoffentscheidung."
        )
    subject = subjects[0] if subjects else "Der technische Gegenstand"
    if profile.startswith("material_"):
        return (
            f"Bei {subject} sind Werkstofffamilie, konkreter Compound, Prüfwert und "
            "anwendungsbezogene Einsatzgrenze strikt zu trennen."
        )
    if profile.startswith("seal_"):
        return (
            f"Die technische Funktion von {subject} ergibt sich aus Dichtprinzip, Bauform, "
            "Werkstoff, Gegenpartner und Betriebsbedingungen."
        )
    if profile.startswith("medium_"):
        return (
            f"Die Wirkung von {subject} auf ein Dichtsystem hängt von Zusammensetzung, "
            "Konzentration, Temperatur, Dauer und konkretem Compound ab."
        )
    return "Die technische Einordnung folgt den geprüften Quellen und den benannten Randbedingungen."


def _engineering_missing_information(plan: dict) -> list[str]:
    missing = [
        f"{entry['subject']}: nicht belegt sind {', '.join(entry.get('missing_facets', ()))}"
        for entry in plan.get("subject_coverage", ())
        if entry.get("missing_facets")
    ]
    if plan.get("comparison"):
        missing.append(
            "Für eine Auswahlentscheidung: konkrete Compounds beziehungsweise Grades, Medium mit "
            "Additiven, Temperaturprofil, Druck, Bewegungsart, Geschwindigkeit, Bauform und Nachweisbasis."
        )
    return missing[:10]


def _fact_subjects(fact: GroundingFact, subjects: tuple[str, ...]) -> frozenset[str]:
    """Bind evidence to its primary comparison subject, preferring the stable card identity.

    Broad scope tags may mention alternatives, so they are unsuitable as primary-subject ownership.
    Reviewed profile card IDs are the current authoritative discriminator.  A single-subject overview
    may safely bind its retrieved evidence to that one subject; comparison evidence must identify its
    side explicitly and otherwise remains unusable for a subject cell.
    """
    card_tokens = {
        re.sub(r"[^a-z0-9]+", "", token.casefold())
        for token in re.split(r"[-_:/.]+", fact.card_id)
        if token
    }
    matched = {
        subject
        for subject in subjects
        if re.sub(r"[^a-z0-9]+", "", subject.casefold()) in card_tokens
    }
    if matched:
        return frozenset(matched)
    if len(subjects) == 1:
        return frozenset(subjects)
    return frozenset()


def _fallback_engineering_answer(
    *,
    plan: dict,
    evidence_facts: dict[str, GroundingFact],
    evidence_subjects: dict[str, frozenset[str]],
    case_revision: int,
) -> EngineeringKnowledgeAnswer:
    """Fail closed to exact reviewed statements, preserving subject and facet identity."""
    claims: list[EngineeringClaim] = []
    subjects = tuple(plan.get("subjects", ())) or ("Dichtungstechnik",)
    evidence_metadata = {
        evidence_id: (
            fact,
            tuple(fact.answer_facets) or ("properties",),
            evidence_subjects.get(evidence_id)
            or (frozenset(subjects) if len(subjects) == 1 else frozenset()),
        )
        for evidence_id, fact in evidence_facts.items()
    }
    used: set[tuple[str, str]] = set()

    # First fill every render cell from one exact reviewed statement. This keeps the fallback useful
    # and symmetric even when the provider returns invalid JSON or incomplete coverage.
    for subject in subjects:
        for section in plan.get("sections", ()):
            section_facets = tuple(section.get("facets", ()))
            selected = next(
                (
                    (evidence_id, fact, facets)
                    for evidence_id, (
                        fact,
                        facets,
                        bound_subjects,
                    ) in evidence_metadata.items()
                    if subject in bound_subjects
                    and any(facet in facets for facet in section_facets)
                ),
                None,
            )
            if selected is None:
                continue
            evidence_id, fact, facets = selected
            facet = next(facet for facet in section_facets if facet in facets)
            claims.append(
                EngineeringClaim(
                    subject=subject,
                    facet=facet,
                    statement=fact.text,
                    evidence_ids=[evidence_id],
                    criticality=(
                        "limit" if facet in {"limits", "failure_modes"} else "context"
                    ),
                )
            )
            used.add((subject, evidence_id))

    # Then retain additional reviewed facts while respecting the bounded chat contract.
    for evidence_id, (fact, facets, bound_subjects) in evidence_metadata.items():
        for subject in sorted(bound_subjects):
            if len(claims) >= 20 or (subject, evidence_id) in used:
                continue
            claims.append(
                EngineeringClaim(
                    subject=subject,
                    facet=facets[0],
                    statement=fact.text,
                    evidence_ids=[evidence_id],
                    criticality=(
                        "limit"
                        if "limits" in facets or "failure_modes" in facets
                        else "context"
                    ),
                )
            )
        if len(claims) >= 20:
            break
    return EngineeringKnowledgeAnswer(
        schema_version=2,
        profile=str(plan.get("profile") or "engineering_knowledge"),
        case_revision=case_revision,
        conclusion=_engineering_conclusion(plan),
        claims=claims,
        assumptions=[],
        missing_information=_engineering_missing_information(plan),
    )


def _knowledge_evidence_context(
    grounding_facts: tuple[GroundingFact, ...],
) -> tuple[tuple[GroundingFact, ...], dict[str, GroundingFact]]:
    """Give the model compact local aliases while retaining canonical evidence internally."""
    canonical_aliases: dict[str, str] = {}
    prompt_facts: list[GroundingFact] = []
    evidence_facts: dict[str, GroundingFact] = {}
    for fact in grounding_facts:
        canonical_id = fact.claim_id or fact.card_id
        if not canonical_id:
            prompt_facts.append(fact)
            continue
        alias = canonical_aliases.setdefault(
            canonical_id, f"E{len(canonical_aliases) + 1}"
        )
        evidence_facts[alias] = fact
        prompt_facts.append(replace(fact, claim_id=alias))
    return tuple(prompt_facts), evidence_facts


def _deterministic_knowledge_answer(
    *,
    knowledge_answer_plan: dict,
    evidence_facts: dict[str, GroundingFact],
    case_revision: int,
) -> TechnicalAnswer:
    """Fail closed to reviewed claim text when provider output violates the contract."""
    profile = str(knowledge_answer_plan.get("profile") or "engineering_knowledge")
    return TechnicalAnswer(
        schema_version=1,
        intent=profile,
        case_revision=case_revision,
        conclusion="Technische Übersicht auf Basis der geprüften Fachquellen.",
        assumptions=[],
        missing_information=[],
        claims=[
            TechnicalClaim(
                text=fact.text,
                evidence_ids=[evidence_id],
                criticality="supporting",
            )
            for evidence_id, fact in list(evidence_facts.items())[:8]
        ],
        recommendation={"summary": "", "status": "none", "conditions": []},
        needs_human_review=False,
    )


def _deterministic_evidence_answer(
    *, evidence_facts: dict[str, GroundingFact], case_revision: int
) -> TechnicalAnswer:
    """Technical fallback that can only restate reviewed evidence and makes no recommendation."""
    return TechnicalAnswer(
        schema_version=1,
        intent="evidence_bound_technical_answer",
        case_revision=case_revision,
        conclusion="Belastbar festhalten lässt sich auf Basis der geprüften Fachquellen:",
        assumptions=[],
        missing_information=[
            "Die konkrete Auswahl und Freigabe erfordert die vollständigen Betriebsbedingungen."
        ],
        claims=[
            TechnicalClaim(
                text=fact.text,
                evidence_ids=[evidence_id],
                criticality="supporting",
            )
            for evidence_id, fact in list(evidence_facts.items())[:8]
        ],
        recommendation={"summary": "", "status": "none", "conditions": []},
        needs_human_review=True,
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
        require_evidence_for_all_claims: bool = False,
        compact_technical_answer: bool = False,
        work_solution_candidate: bool = False,
        risk_flags: list[str] | None = None,
        case_revision: int = 0,
    ) -> Answer:
        prompt_grounding_facts = grounding_facts
        knowledge_evidence_facts: dict[str, GroundingFact] = {}
        if self._structured_output_enabled and knowledge_answer_plan is not None:
            prompt_grounding_facts, knowledge_evidence_facts = (
                _knowledge_evidence_context(grounding_facts)
            )
        system = self._assemble_system(
            flags=flags,
            grounding_facts=prompt_grounding_facts,
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
            evidence_facts = dict(knowledge_evidence_facts)
            if knowledge_answer_plan is None:
                for fact in grounding_facts:
                    if fact.card_id:
                        evidence_facts[fact.card_id] = fact
            allowed_ids = frozenset(evidence_facts)
            if knowledge_answer_plan is not None:
                from sealai_v2.core.knowledge_answer import facets_for_fact
                from sealai_v2.knowledge.material_parameters import parameter_text

                subjects = tuple(
                    str(subject)
                    for subject in knowledge_answer_plan.get("subjects", ())
                    if str(subject)
                )
                evidence_facets_v2 = {
                    evidence_id: frozenset(facets_for_fact(fact))
                    for evidence_id, fact in evidence_facts.items()
                }
                evidence_subjects_v2 = {
                    evidence_id: _fact_subjects(fact, subjects)
                    for evidence_id, fact in evidence_facts.items()
                }
                evidence_texts_v2 = {
                    evidence_id: fact.text
                    for evidence_id, fact in evidence_facts.items()
                }
                coverage_by_subject = {
                    str(entry.get("subject")): set(entry.get("covered_facets", ()))
                    for entry in knowledge_answer_plan.get("subject_coverage", ())
                }
                required_cells = {
                    subject: tuple(
                        frozenset(
                            set(section.get("facets", ()))
                            & coverage_by_subject.get(subject, set())
                        )
                        for section in knowledge_answer_plan.get("sections", ())
                        if set(section.get("facets", ()))
                        & coverage_by_subject.get(subject, set())
                    )
                    for subject in subjects
                }
                evidence_map = "; ".join(
                    f"{evidence_id}=>subject[{','.join(sorted(evidence_subjects_v2[evidence_id])) or 'unbound'}]"
                    f";facets[{','.join(sorted(evidence_facets_v2[evidence_id])) or 'none'}]"
                    for evidence_id in sorted(evidence_facts)
                )
                instruction = (
                    "\n\nCreate exactly one internal EngineeringKnowledgeAnswer object. "
                    "Do not write Markdown and do not create tables. The deterministic renderer owns "
                    "all tables and parameter values. Copy each claim statement exactly from one "
                    "cited evidence item; do not paraphrase, merge or extend it. Each claim must "
                    "address exactly one declared "
                    "subject and one facet supported by every cited evidence ID. Never transfer a "
                    "property, limit or failure mechanism from one comparison subject to another. "
                    "Do not introduce a number, standard, product, filler, approval or limit absent "
                    "from the supplied reviewed evidence or material-parameter registry. Distinguish "
                    "family tendencies, compound-specific values, test values and application limits. "
                    "State mechanisms and consequences where the evidence supports them. Use concise "
                    "senior-engineer language, preserve uncertainty, and identify the minimum missing "
                    "inputs that would change a selection. "
                    f"profile must be {knowledge_answer_plan.get('profile')}; case_revision must be "
                    f"{case_revision}; allowed subjects: {', '.join(subjects) or 'Dichtungstechnik'}. "
                    f"Evidence ownership: {evidence_map or '(none)'}."
                )
                try:
                    engineering, result = await generate_structured(
                        self._client,
                        output_type=EngineeringKnowledgeAnswer,
                        schema_name="sealingai_engineering_knowledge_answer_v2",
                        system=system + instruction,
                        user=question,
                        model_config=self._model_config,
                        max_repairs=0,
                    )
                    engineering = engineering.model_copy(
                        update={
                            "conclusion": _engineering_conclusion(
                                knowledge_answer_plan
                            ),
                            "assumptions": [],
                            "missing_information": _engineering_missing_information(
                                knowledge_answer_plan
                            ),
                        }
                    )
                    validate_engineering_answer(
                        engineering,
                        profile=str(knowledge_answer_plan.get("profile")),
                        case_revision=case_revision,
                        allowed_subjects=subjects,
                        evidence_facets=evidence_facets_v2,
                        evidence_subjects=evidence_subjects_v2,
                        evidence_texts=evidence_texts_v2,
                        required_cells=required_cells,
                        parameter_text=parameter_text(material_params),
                    )
                except (StructuredOutputError, EngineeringAnswerValidationError) as exc:
                    logger.warning(
                        "engineering knowledge answer failed validation; using exact-evidence "
                        "fallback (%s)",
                        exc,
                    )
                    engineering = _fallback_engineering_answer(
                        plan=knowledge_answer_plan,
                        evidence_facts=evidence_facts,
                        evidence_subjects=evidence_subjects_v2,
                        case_revision=case_revision,
                    )
                    result = LlmResult(
                        text="",
                        model=self._model_config.model,
                        finish_reason="deterministic_engineering_fallback",
                    )
                return Answer(
                    text=strip_sourcing(
                        render_engineering_answer(
                            engineering,
                            knowledge_answer_plan=knowledge_answer_plan,
                            material_params=material_params,
                        )
                    ),
                    model=result.model,
                    grounding_facts=grounding_facts,
                    finish_reason=result.finish_reason,
                    verification_claims=tuple(
                        claim.statement for claim in engineering.claims
                    ),
                )
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
            elif require_evidence_for_all_claims:
                structured_instruction += (
                    " This is an evidence-bound technical answer: every technical claim must "
                    "carry at least one allowed evidence_id. User-provided case facts belong in "
                    "assumptions or missing_information, not as unsupported technical claims. "
                    "Do not add values, limits, materials, standards, products or suitability "
                    "statements that are absent from the supplied evidence or calculations. "
                    "If the user's compatibility, temperature, cost, lifetime or geometry goals "
                    "cannot all be evidenced at once, state that unresolved target conflict "
                    "explicitly instead of presenting a candidate list as a solution."
                )
                if work_solution_candidate:
                    structured_instruction += (
                        " The evidence supports engineering a seal-type solution candidate: name "
                        "one primary provisional candidate, explain its sealing mechanism and "
                        "conditions, and identify the next-best architecture alternative. Do not "
                        "replace this solution work with a generic manufacturer referral."
                    )
                if compact_technical_answer:
                    structured_instruction += (
                        " This is a compact first-turn response: put the decisive risk or result "
                        "first, use at most three technical claims and three discriminating "
                        "missing-information items, do not restate the user's inputs as assumptions, "
                        "and keep recommendation conditions to at most two."
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
                if compact_technical_answer:
                    priority = {
                        "decision_relevant": 0,
                        "supporting": 1,
                        "context": 2,
                    }
                    technical = technical.model_copy(
                        update={
                            "assumptions": [],
                            "missing_information": technical.missing_information[:3],
                            "claims": sorted(
                                technical.claims,
                                key=lambda claim: priority[claim.criticality],
                            )[:3],
                            "recommendation": technical.recommendation.model_copy(
                                update={
                                    "conditions": technical.recommendation.conditions[
                                        :2
                                    ]
                                }
                            ),
                        }
                    )
                if knowledge_answer_plan is not None:
                    technical = technical.model_copy(
                        update={
                            "recommendation": technical.recommendation.model_copy(
                                update={
                                    "summary": "",
                                    "status": "none",
                                    "conditions": [],
                                }
                            ),
                            "needs_human_review": False,
                        }
                    )
                validate_technical_answer(
                    technical,
                    case_revision=case_revision,
                    allowed_evidence_ids=allowed_ids,
                    require_evidence_for_all_claims=(
                        knowledge_answer_plan is not None
                        or require_evidence_for_all_claims
                    ),
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
                        supplemented = list(technical.claims)
                        unused_ids = [
                            evidence_id
                            for evidence_id in evidence_facts
                            if evidence_id not in used_evidence
                        ]
                        while missing_facets:
                            best_id = max(
                                unused_ids,
                                key=lambda evidence_id: len(
                                    evidence_facets.get(evidence_id, set())
                                    & missing_facets
                                ),
                                default="",
                            )
                            covered_now = (
                                evidence_facets.get(best_id, set()) & missing_facets
                            )
                            if not best_id or not covered_now:
                                raise TechnicalAnswerValidationError(
                                    "knowledge_facet_coverage:"
                                    + ",".join(sorted(missing_facets))
                                )
                            supplemented.append(
                                TechnicalClaim(
                                    text=evidence_facts[best_id].text,
                                    evidence_ids=[best_id],
                                    criticality="supporting",
                                )
                            )
                            unused_ids.remove(best_id)
                            missing_facets -= covered_now
                        technical = technical.model_copy(
                            update={"claims": supplemented}
                        )
                return technical, result

            try:
                technical, result = await _call(system + structured_instruction)
            except (StructuredOutputError, TechnicalAnswerValidationError) as exc:
                if knowledge_answer_plan is not None and evidence_facts:
                    logger.warning(
                        "structured knowledge answer failed validation; using reviewed-evidence "
                        "fallback (%s)",
                        exc,
                    )
                    technical = _deterministic_knowledge_answer(
                        knowledge_answer_plan=knowledge_answer_plan,
                        evidence_facts=evidence_facts,
                        case_revision=case_revision,
                    )
                    result = LlmResult(
                        text="",
                        model=self._model_config.model,
                        finish_reason="deterministic_knowledge_fallback",
                    )
                elif require_evidence_for_all_claims and evidence_facts:
                    logger.warning(
                        "structured technical answer failed evidence validation; using "
                        "reviewed-evidence fallback (%s)",
                        exc,
                    )
                    technical = _deterministic_evidence_answer(
                        evidence_facts=evidence_facts,
                        case_revision=case_revision,
                    )
                    result = LlmResult(
                        text="",
                        model=self._model_config.model,
                        finish_reason="deterministic_evidence_fallback",
                    )
                else:
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
        require_evidence_for_all_claims: bool = False,
        compact_technical_answer: bool = False,
        work_solution_candidate: bool = False,
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
                    require_evidence_for_all_claims=require_evidence_for_all_claims,
                    compact_technical_answer=compact_technical_answer,
                    work_solution_candidate=work_solution_candidate,
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
