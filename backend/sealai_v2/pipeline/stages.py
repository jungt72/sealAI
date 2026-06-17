"""Pipeline stages. M1 implements `understand` (soft, annotate-only) and the L1 `answer`
(in ``pipeline.py``); `ground`/`verify`/`cite` are inert stubs (M2/M3) so the
verstehen→grounden→antworten→verifizieren→zitieren chain is visible but does nothing yet.
"""

from __future__ import annotations

import json

from sealai_v2.core.contracts import (
    Answer,
    CalcEngine,
    CalcResult,
    ConversationMemory,
    CrossSessionMemory,
    Flags,
    GroundingFact,
    Intent,
    LlmClient,
    MemoryView,
    ModelConfig,
    RetrievalResult,
    Retriever,
    SessionContext,
    Understanding,
)

_UNDERSTAND_SYSTEM = (
    "Du klassifizierst eine Nutzer-Nachricht an einen Dichtungstechnik-Assistenten GROB nach "
    'Absicht. Antworte NUR mit einem JSON-Objekt {"intent": <label>, "rationale": <kurz>}. '
    "labels: wissensfrage (allgemeine Erklärung/Eigenschaften), fallarbeit (konkrete "
    "Dichtungssituation/Auswahl), faktfrage (kurze Einzelfrage), gespraech "
    "(Begrüßung/Smalltalk/Off-Topic), unklar. Dies ist eine WEICHE Annotation; sie steuert nichts."
)


def _extract_json(raw: str) -> str:
    """Best-effort: pull the first {...} block, tolerating code fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if "\n" in s:
            s = s.split("\n", 1)[1]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


async def understand(
    client: LlmClient, model_config: ModelConfig, question: str
) -> Understanding:
    """Stage 1 — soft LLM intent. Annotation only; NEVER gates or routes (build-spec §5.1)."""
    res = await client.generate(
        system=_UNDERSTAND_SYSTEM, user=question, model_config=model_config
    )
    raw = res.text.strip()
    try:
        data = json.loads(_extract_json(raw))
        intent = Intent(str(data.get("intent", "unklar")).strip().lower())
        rationale = str(data.get("rationale", ""))[:300]
    except (ValueError, KeyError, TypeError):
        intent, rationale = Intent.UNKLAR, ""
    return Understanding(intent=intent, rationale=rationale, raw=raw[:500])


# --- inert stubs (M2/M3) ---


async def ground(
    retriever: Retriever | None, question: str, *, tenant_id: str, k: int = 5
) -> RetrievalResult:
    """Stage 2 — L2 grounding (M3). Retrieve reviewed Fachkarten via the injected ``Retriever`` and
    return them as grounding facts (+ provisional draft hits). PRE-FETCH then render into the prompt —
    no mid-generation tool calls (build-spec §12). No retriever → empty result → L1 answers
    "vorläufig"."""
    if retriever is None:
        return RetrievalResult()
    return await retriever.retrieve(question, tenant_id=tenant_id, k=k)


async def compute(
    engine: CalcEngine | None,
    params: dict | None,
    *,
    grounding_facts: tuple[GroundingFact, ...] = (),
    context: dict | None = None,
    param_origins: dict | None = None,
) -> CalcResult:
    """Stage 3 — deterministic calc layer (M4), AFTER ground (Fachkarten-property inputs available).
    Evaluate the reviewed calc registry over the params (+ reviewed grounding facts for qualitative
    cross-layer flags) as a topological cascade. Pure; fail-closed (NotComputed reasons, never a
    misleading number). No engine → empty CalcResult. ``param_origins`` (M8-A) carries the
    per-input provenance from the binding layer into the computed values."""
    if engine is None:
        return CalcResult()
    return engine.evaluate(
        params=params or {},
        grounding_facts=grounding_facts,
        context=context,
        param_origins=param_origins,
    )


async def verify(
    verifier,
    generator,
    catalog,
    question: str,
    draft: Answer,
    *,
    flags: Flags,
    grounding_facts: tuple[GroundingFact, ...] = (),
    computed_values: tuple = (),
    not_computed: tuple = (),
):
    """Stage 5 — L3 verifier (M2/M3/M4). Independent critic pass against the trap catalog, the
    reviewed grounding facts (M3) AND the computed values (M4); on a reviewed hard-gate violation →
    regenerate-once or hedge; card/calc contradictions are FLAG-only. M8-C: the kern's fail-closed
    ``not_computed`` reasons feed the parametric-leak policy (note/hedge name the missing inputs).
    Returns ``(final, verdict)``."""
    from sealai_v2.core.l3_verifier import run_verify

    return await run_verify(
        verifier,
        generator,
        catalog,
        question,
        draft,
        flags=flags,
        grounding_facts=grounding_facts,
        computed_values=computed_values,
        not_computed=not_computed,
    )


async def cite(answer: Answer) -> Answer:
    """Stage 5 — provenance/citation. STUB: passthrough (L1 self-marks Allgemeinwissen at M1)."""
    return answer


# --- memory (M5, build-spec §7) — recall before answering, remember after ---


def recall(
    memory: ConversationMemory | None,
    cross_session: CrossSessionMemory | None,
    *,
    tenant_id: str,
    session: SessionContext | None,
    question: str,
) -> MemoryView:
    """Pre-answer recall: working window (L1) + structured case-state (L2) + relevance-injected
    durable facts (L4, inert until that sub-gate). No memory OR no session → empty view → the
    assembled prompt is byte-identical to the no-memory path (true no-op). Tenant scope is
    mandatory at the store layer (P0)."""
    if memory is None or session is None:
        return MemoryView()
    view = memory.recall(tenant_id=tenant_id, session_id=session.session_id)
    if cross_session is not None:
        durable = cross_session.relevant_facts(tenant_id=tenant_id, query=question)
        if durable:
            view = MemoryView(
                window=view.window, case_state=view.case_state, durable=durable
            )
    return view


async def remember(
    memory: ConversationMemory | None,
    distiller,
    *,
    tenant_id: str,
    session: SessionContext | None,
    question: str,
    answer: str,
    cross_session: CrossSessionMemory | None = None,
) -> None:
    """Post-answer record: append the turn (window L1 + history L3) and, if a distiller is wired,
    merge the LLM-distilled STATED facts into the case-state (L2). No memory OR no session → no-op
    AND no distill LLM call (keeps the single-turn eval a true, zero-cost no-op). Distilling AFTER
    the answer means it can never perturb the turn it observed.

    L4 curation: the same conservatively-distilled facts are promoted to the cross-session durable
    store (build-spec §7.4 "kuratiert merken" — the distiller is already the curated, user-stated,
    numeric-trace-guarded set, so this is a conservative promotion). The in-process cross-session
    impl stores but never injects (returns nothing); the durable adapter is what actually surfaces
    them in a later session — so this is inert for the offline eval."""
    if memory is None or session is None:
        return
    facts = ()
    if distiller is not None:
        facts = await distiller.distill(question=question, answer=answer)
    memory.record_turn(
        tenant_id=tenant_id,
        session_id=session.session_id,
        question=question,
        answer=answer,
        facts=facts,
    )
    if cross_session is not None and facts:
        cross_session.remember_durable(tenant_id=tenant_id, facts=facts)
