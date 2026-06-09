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
    Flags,
    GroundingFact,
    Intent,
    LlmClient,
    ModelConfig,
    RetrievalResult,
    Retriever,
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
) -> CalcResult:
    """Stage 3 — deterministic calc layer (M4), AFTER ground (Fachkarten-property inputs available).
    Evaluate the reviewed calc registry over the params (+ reviewed grounding facts for qualitative
    cross-layer flags) as a topological cascade. Pure; fail-closed (NotComputed reasons, never a
    misleading number). No engine → empty CalcResult."""
    if engine is None:
        return CalcResult()
    return engine.evaluate(
        params=params or {}, grounding_facts=grounding_facts, context=context
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
):
    """Stage 5 — L3 verifier (M2/M3/M4). Independent critic pass against the trap catalog, the
    reviewed grounding facts (M3) AND the computed values (M4); on a reviewed hard-gate violation →
    regenerate-once or hedge; card/calc contradictions are FLAG-only. Returns ``(final, verdict)``."""
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
    )


async def cite(answer: Answer) -> Answer:
    """Stage 5 — provenance/citation. STUB: passthrough (L1 self-marks Allgemeinwissen at M1)."""
    return answer
