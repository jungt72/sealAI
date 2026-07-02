"""Pipeline stages — the verstehen→grounden→antworten→verifizieren→zitieren chain.
`understand` is the soft, annotate-only LLM intent (+ G4 archetype); the L1 `answer` lives in
``pipeline.py``. The former M2/M3 stubs are now fully implemented: `ground` does L2 grounding
(reviewed Fachkarten via the injected ``Retriever`` + the §4 Verträglichkeitsmatrix); `verify`
runs the L3 verifier (independent critic + the deterministic hard-gate/matrix guards, regenerate-
once or hedge); `cite` is a passthrough (provenance is surfaced by the serializer / L1's own
Allgemeinwissen self-marking). The further deterministic operations (compute, recall/remember,
gegencheck, diagnose, decode, alternativen) live alongside them here.
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
    RememberedFact,
    RetrievalResult,
    Retriever,
    SessionContext,
    Understanding,
)
from sealai_v2.core.gegencheck import evaluate_gegencheck
from sealai_v2.core.decode_extract import EQUIVALENZ_GRENZE, decode_designation
from sealai_v2.core.medium_extract import extract_medium_facts
from sealai_v2.core.seal_spec_extract import extract_seal_spec
from sealai_v2.knowledge.hersteller_partner import rank_partners
import re as _re

_ALT_RE = _re.compile(
    r"\b(alternativ|hersteller|lieferant|bezugsquelle|wer\s+(macht|kann|stellt|liefert|baut)|"
    r"vergleichbar|ersatz(teil)?|wer\s+noch)\b",
    _re.IGNORECASE,
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


def _understand_system(archetype_keys: tuple[str, ...] = ()) -> str:
    """The understand system prompt. With archetype keys available (G4), it ALSO asks for a soft
    ``archetype`` field constrained to those keys — one call, no second classifier (owner decision 3)."""
    if not archetype_keys:
        return _UNDERSTAND_SYSTEM
    keys = ", ".join(archetype_keys)
    return (
        _UNDERSTAND_SYSTEM
        + ' Ergänze das JSON-Objekt um ein Feld "archetype": die Maschinen-Art, AUSSCHLIESSLICH '
        + f"einer von [{keys}] — aber NUR, wenn sie klar genannt oder eindeutig erkennbar ist; sonst "
        + "null. Rate nicht; im Zweifel null. Auch dies ist eine WEICHE Annotation; sie steuert nichts."
    )


async def understand(
    client: LlmClient,
    model_config: ModelConfig,
    question: str,
    *,
    archetype_keys: tuple[str, ...] = (),
) -> Understanding:
    """Stage 1 — soft LLM intent (+ G4: soft archetype). Annotation only; NEVER gates or routes
    (build-spec §5.1). ``archetype`` is SERVER-SIDE validated against ``archetype_keys`` (a key the
    store actually has), so an LLM-invented key can never survive."""
    res = await client.generate(
        system=_understand_system(archetype_keys),
        user=question,
        model_config=model_config,
    )
    raw = res.text.strip()
    archetype: str | None = None
    try:
        data = json.loads(_extract_json(raw))
        intent = Intent(str(data.get("intent", "unklar")).strip().lower())
        rationale = str(data.get("rationale", ""))[:300]
        a = data.get("archetype")
        if a is not None and archetype_keys:
            a = str(a).strip().lower()
            if a in {k.lower() for k in archetype_keys}:  # only a KNOWN key survives
                archetype = a
    except (ValueError, KeyError, TypeError):
        intent, rationale = Intent.UNKLAR, ""
    return Understanding(
        intent=intent, rationale=rationale, archetype=archetype, raw=raw[:500]
    )


# --- inert stubs (M2/M3) ---


async def ground(
    retriever: Retriever | None,
    matrix,
    question: str,
    *,
    tenant_id: str,
    case_facts: tuple = (),
    k: int = 5,
) -> RetrievalResult:
    """Stage 2 — L2 grounding. Retrieve reviewed Fachkarten via the injected ``Retriever`` AND query
    the §4 Verträglichkeitsmatrix (Gap #2) for the case-relevant compatibility verdicts. PRE-FETCH then
    render into the prompt — no mid-generation tool calls (build-spec §12). Cards land in
    ``grounding_facts``; matrix cells land in ``matrix_facts`` (their own channel so the L1 vs L3 wiring
    is two separate eval-gated steps). No source → empty → L1 answers "vorläufig"."""
    result = RetrievalResult()
    if retriever is not None:
        result = await retriever.retrieve(question, tenant_id=tenant_id, k=k)
    matrix_facts = ()
    if matrix is not None:
        matrix_facts = matrix.query(
            tenant_id=tenant_id, query_text=question, case_facts=case_facts
        )
    if not matrix_facts:
        return result
    return RetrievalResult(
        grounding_facts=result.grounding_facts,
        provisional=result.provisional,
        matrix_facts=matrix_facts,
    )


async def compute(
    engine: CalcEngine | None,
    params: dict | None,
    *,
    grounding_facts: tuple[GroundingFact, ...] = (),
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
    matrix_facts: tuple[GroundingFact, ...] = (),
    calc=None,
    case_context: list[dict] | None = None,
    durable_context: list[dict] | None = None,
    conversation_window: list[dict] | None = None,
    untrusted: list[dict] | None = None,
    comparison_context: bool = False,
):
    """Stage 5 — L3 verifier (M2/M3/M4 + Gap #2). Independent critic pass against the trap catalog, the
    reviewed grounding facts (M3), the computed values (M4) AND the §4 Verträglichkeitsmatrix (Gap #2);
    on a reviewed hard-gate violation OR a reviewed matrix contradiction → regenerate-once or hedge;
    card/calc contradictions stay FLAG-only. M8-C: the kern's fail-closed ``not_computed`` reasons feed
    the parametric-leak policy (note/hedge name the missing inputs). OPTIMIZE_BACKLOG #5: ``question``/
    ``case_context`` scope the trap correction to the topic, and the full draft context (``calc`` +
    memory + untrusted) is threaded so the regeneration is not degraded. Returns ``(final, verdict)``."""
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
        matrix_facts=matrix_facts,
        calc=calc,
        case_context=case_context,
        durable_context=durable_context,
        conversation_window=conversation_window,
        untrusted=untrusted,
        comparison_context=comparison_context,
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
    # Phase-1 Medium-Wiring: PREPEND the deterministic medium facts. record_turn's per-feld write is
    # last-wins, so a distiller-emitted "medium" still WINS (provenance preserved), the medium is
    # RELIABLY present when the distiller drops it, and the coarse "medium_kategorie" is always added.
    facts = extract_medium_facts(question) + facts
    memory.record_turn(
        tenant_id=tenant_id,
        session_id=session.session_id,
        question=question,
        answer=answer,
        facts=facts,
    )
    if cross_session is not None and facts:
        cross_session.remember_durable(tenant_id=tenant_id, facts=facts)


def gegencheck(matrix, case, *, tenant_id: str) -> dict | None:
    """Stage - deterministic Gegencheck verdict (Modus E, build-spec section 5 op "Gegenchecken").

    Fires ONLY when the case carries BOTH an existing seal material AND a medium - a real
    "wir verwenden X, passt das?" situation; any other turn returns None, so the no-Gegencheck
    path stays byte-identical (no verdict attached). The result is the pure kernel's binary
    disqualified-or-not dict (core.gegencheck.evaluate_gegencheck): backend owns the verdict,
    L1 narrates the WHY via the matrix begruendung that ground already injects as matrix_facts.

    Doctrine: never affirms suitability (E4-1 - only unvertraeglich disqualifies; bedingt
    carries its grounded condition inline; everything else abstains). No I/O beyond the injected
    matrix, no LLM, no mutation. matrix is the section-4 InProcessCompatibilityMatrix (its
    catalog recovers the bewertung enum query drops); None (L2 kill-switch) -> None."""
    if matrix is None or case is None:
        return None
    spec = case.seal_spec or {}
    material = spec.get("material")
    medium_slot = case.medium or {}
    matched = medium_slot.get("matched") or (
        [medium_slot["name"]] if medium_slot.get("name") else []
    )
    if not material or not matched:
        return None
    catalog = getattr(matrix, "catalog", None)
    if catalog is None:
        return None
    # Join ALL matched media so the kernel query returns every relevant cell and its
    # disqualify-lean fold runs over all of them (a co-mentioned disqualifying medium wins,
    # and one medium named with several tags - "Heißdampf-Sterilisation (SIP)" - still fires).
    return evaluate_gegencheck(
        material, " ".join(matched), tenant=tenant_id, catalog=catalog
    )


# L6 (Relay-Increment P0-C, follow-up): a Gegencheck verdict established in an EARLIER turn must
# still gate `alternativen` in a LATER turn that doesn't restate material/medium — `gegencheck()`
# above is deliberately this-turn-only (Case.from_case_state extracts seal_spec/medium fresh from
# the live question, never from persisted facts — Modus E narration stays exactly as before,
# UNTOUCHED by this addition). These two helpers recover a canonical material/medium from the
# PERSISTED, session-local case-state instead, so the alternativen precondition can be checked
# against the conversation's accumulated case-state — not the current message's text alone.


def _case_state_material(case_state: tuple["RememberedFact", ...]) -> str | None:
    """Recover a canonical material from persisted case-state. Checks the FORM channel's already-
    canonical ``werkstoffvorgabe`` field first (situations.ts), then the CHAT distiller's free-text
    ``werkstoff`` field (distill.jinja) — but never trusts the distilled string directly (the
    distiller is an LLM, not a canonical vocabulary): it is re-run through the SAME deterministic
    ``extract_seal_spec`` the live turn uses, so only a real matrix-vocabulary material counts, never
    an arbitrary LLM-distilled phrase. Most recent fact wins (a corrected/updated statement)."""
    for feld_name in ("werkstoffvorgabe", "werkstoff"):
        for f in reversed(case_state):
            if f.feld == feld_name and f.wert:
                spec = extract_seal_spec(f.wert)
                if spec and spec.get("material"):
                    return spec["material"]
    return None


def _case_state_medium(case_state: tuple["RememberedFact", ...]) -> list[str]:
    """Recover ALL canonical media stated across the persisted case-state. ``feld="medium"`` is
    written deterministically by ``extract_medium_facts`` (chat-inline, every turn) — already a
    canonical §4-vocabulary tag, so no re-extraction is needed here (unlike material). Collects
    every DISTINCT value across turns (mirrors the disqualify-lean multi-medium fold in
    ``gegencheck`` — a co-mentioned disqualifying medium from an earlier turn must not be dropped)."""
    media: list[str] = []
    for f in case_state:
        if f.feld == "medium" and f.wert and f.wert not in media:
            media.append(f.wert)
    return media


def gegencheck_from_case_state(
    matrix, case_state: tuple["RememberedFact", ...], *, tenant_id: str
) -> dict | None:
    """L6 fallback for `alternativen`'s verdict precondition: re-derive a Gegencheck verdict from
    the session's PERSISTED case-state (material + medium accumulated across turns), independent
    of whether the LIVE turn's text restates them. `gegencheck()` itself is intentionally left
    this-turn-only (Modus E narration); this is a SEPARATE, additive path used only to decide
    whether a situational assessment has already happened for the conversation. No I/O beyond the
    injected matrix, no LLM, no mutation — pure, same discipline as `gegencheck()`."""
    if matrix is None:
        return None
    material = _case_state_material(case_state)
    media = _case_state_medium(case_state)
    if not material or not media:
        return None
    catalog = getattr(matrix, "catalog", None)
    if catalog is None:
        return None
    return evaluate_gegencheck(material, " ".join(media), tenant=tenant_id, catalog=catalog)


def diagnose(versagensmodi, question: str, *, tenant_id: str) -> dict | None:
    """Stage - deterministic Diagnose (Modus D, Dim. 5): match the reported symptom against the
    Versagensmodi store -> the strongest symptom/ursache/fix. Fires ONLY when a symptom is recognised
    (no match -> None -> byte-identical no-Diagnose turn). A DRAFT mode surfaces provisional=True
    ("vorlaeufig - gegen Hersteller verifizieren"); a reviewed mode is grounded. Backend owns the
    grounded(draft) cause/fix; never a final release (L4 stays with the manufacturer). No LLM, no
    mutation, no invented number. versagensmodi is the InProcessVersagensmodiStore; None -> None."""
    if versagensmodi is None:
        return None
    modes = versagensmodi.query(tenant_id=tenant_id, query_text=question)
    if not modes:
        return None
    m = modes[0]
    return {
        "ursache": m.ursache,
        "fix": m.fix,
        "source": m.quelle(),
        "provisional": not m.reviewed,
        "betrifft_archetypen": list(m.betrifft_archetypen),
    }


def decode(question: str) -> dict | None:
    """Stage - deterministic Decode (Modus G): parse a seal designation -> structured spec (dims
    echoed from the input, material, type). Fires ONLY when a dimension group is present (a real
    designation to decode); a bare material mention is not a decode request -> None (byte-identical
    no-Decode turn). Result-side: the parsed dims live in the structured spec, the narration stays
    qualitative (parametric-leak-safe). Equivalence ("Teil X = Teil Y") is NOT asserted (§9.2, the
    sharpest edge) - only the honest EQUIVALENZ_GRENZE boundary travels. Pure, no I/O, no LLM."""
    spec = decode_designation(question)
    if not spec or not spec.get("dims_mm"):
        return None
    return {**spec, "equivalenz_grenze": EQUIVALENZ_GRENZE}


def alternativen(
    partner_registry, question: str, gegencheck_verdict: dict | None, *, tenant_id: str
) -> dict | None:
    """Stage - Alternativen/Hersteller (Modus F, Dim. 6, owner business model): from the PARTNER POOL,
    the best-FIT manufacturers for the seal spec, ranked BY CAPABILITY ONLY (Produkt-Konzept §3.9 —
    payment gates pool MEMBERSHIP, NEVER ranking; ``rank_partners`` never reads ``plan``). Transparent:
    the list is PAYING partners (the UI labels it "Partner/Anzeige"). Fires ONLY on an explicit
    alternatives/manufacturer request (keyword gate); otherwise None. No partner matches the spec
    (incl. the empty registry — eval/CI) -> an honest "no partner listed" marker with ZERO firm names
    (P1.7 — the backend never invents a manufacturer). No LLM, no mutation. ``partner_registry`` is the
    in-process (CI) or Postgres (dashboard-editable prod) ``PartnerRegistry``.

    L6 "Matching folgt dem Verdikt, nie umgekehrt" (owner Leitbild-Audit 2026-07-02, Relay-Increment
    P0-C): the keyword gate alone used to fire ranking regardless of whether ANY situational
    assessment existed for the case — a first-turn "welcher Hersteller kann NBR-RWDR?" ranked
    partners before any Gegencheck had run. Now, once the keyword gate fires, a MISSING
    ``gegencheck_verdict`` (``stages.gegencheck`` returns ``None`` until the case carries BOTH a
    stated seal material AND a stated medium — the Matrix-Trichotomie precondition) yields an
    honest "assessment needed first" stance instead of a ranking: ZERO firm names (same P1.7
    discipline as the empty-pool case), steering the user toward what is missing. Once a verdict
    exists — of ANY kind: compatible, bedingt, disqualified, even a matrix-miss — ranking proceeds
    exactly as before; what matters is that an assessment was RUN, not its outcome."""
    if partner_registry is None or not _ALT_RE.search(question):
        return None
    if gegencheck_verdict is None:
        return {
            "grounded_data": False,
            "partner": True,  # the directory is a partner directory — stated transparently
            "neutralitaet": "Auswahl nach fachlicher Eignung (Werkstoff, Bauform), unabhängig von der Bezahlung.",
            "hinweis": (
                "Für eine Herstellerempfehlung fehlt zunächst eine fachliche Bewertung der Anwendung. "
                "Nenne Werkstoff und Medium — sobald diese Situationsbewertung vorliegt, zeige ich "
                "passende Partner."
            ),
        }
    spec = decode_designation(question) or {}
    material = spec.get("material")
    bauform = spec.get("type")
    ranked = rank_partners(
        partner_registry.list_active(), material=material, bauform=bauform
    )
    if not ranked:
        return {
            "grounded_data": False,
            "partner": True,  # the directory is a partner directory — stated transparently
            "neutralitaet": "Auswahl nach fachlicher Eignung (Werkstoff, Bauform), unabhängig von der Bezahlung.",
            "hinweis": (
                "Für diese Spezifikation ist aktuell kein Partner-Hersteller gelistet. Grenze die "
                "Fähigkeits-Achsen ein (Werkstoff, Bauform, Größe, Zertifikate) — passende Partner "
                "erscheinen hier, sobald sie gelistet sind."
            ),
        }
    return {
        "grounded_data": True,
        "partner": True,  # TRANSPARENT: these are paying partners (Anzeige), not a neutral market scan
        "hersteller": [
            {
                "id": p.hersteller,
                "firmenname": p.firmenname,
                "beschreibung": p.beschreibung,
                "website": p.website,
                "standort": p.standort,
                "werkstoffe": list(p.werkstoffe),
                "zertifikate": list(p.zertifikate),
            }
            for p in ranked
        ],
        "ordered_by": "capability",
        "neutralitaet": "Auswahl nach fachlicher Eignung — unabhängig von der Bezahlung. Gelistet sind Partner-Hersteller.",
    }
