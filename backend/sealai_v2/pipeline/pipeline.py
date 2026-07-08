"""The thin V2 answer pipeline (build-spec §5 / Prinzipien §3).

M1 wires only understand→answer; ground/verify/cite are inert stubs. Tenant scope (P0) is
mandatory and validated at the entry point. No deterministic gate, no routing — the soft
intent annotates but never alters the answer path.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sealai_v2.config.settings import Settings
from sealai_v2.llm.cache_key import build_prompt_cache_key
from sealai_v2.obs.safe_trace import safe_input_projection, safe_output_projection
from sealai_v2.pipeline.routing import RouteName, classify_route
from sealai_v2.pipeline.smalltalk_generator import SmalltalkGenerator
from sealai_v2.prompts.assembler import SmalltalkNavigationPromptAssembler
from sealai_v2.pipeline.route_telemetry import (
    LoggingRouteTelemetrySink,
    RouteTelemetry,
    RouteTelemetrySink,
)
from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.calc.inline_extract import (
    extract_inline,
    extract_rwdr_shaft,
    merge_inline,
)
from sealai_v2.core.calc.derived import DerivedComputation, recompute_derived
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import (
    Answer,
    CalcEngine,
    CalcResult,
    Case,
    ConversationMemory,
    CrossSessionMemory,
    DerivedFact,
    Flags,
    LlmClient,
    ModelConfig,
    PipelineResult,
    Retriever,
    SessionContext,
    Understanding,
    UntrustedContent,
    VerifierVerdict,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier, run_parametric_guard
from sealai_v2.core.medium_extract import extract_medium_facts
from sealai_v2.core.medium_research import MediumIntelligence, MediumResearcher
from sealai_v2.memory.context_assembler import MemoryContextBundle, MemoryContextService
from sealai_v2.core.wissensstand import compute_wissensstand
from sealai_v2.pipeline.produktspec_step import compute_kandidaten_spec
from sealai_v2.knowledge.archetypes import load_archetypes
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.knowledge.versagensmodi import InProcessVersagensmodiStore
from sealai_v2.knowledge.hersteller_partner import InProcessPartnerRegistry
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.knowledge.traps import TrapCatalog, load_traps
from sealai_v2.memory.distiller import Distiller
from sealai_v2.safety.risk_flags import detect_risk_flags
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.obs.tracing import traceable
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.timing import TurnTimer
from sealai_v2.prompts.assembler import (
    DistillPromptAssembler,
    MediumResearchPromptAssembler,
    PromptAssembler,
    UnderstandPromptAssembler,
    VerifierPromptAssembler,
)
from sealai_v2.security.leak_detect import exfiltration_leak
from sealai_v2.security.tenant import TenantContext, require_tenant

_log = logging.getLogger("sealai_v2.pipeline")

# 2026-07-04 routing/extraction audit: the currently ENABLED frontend packs — mirrors
# frontend-v2/src/schema/situations.ts's SITUATIONS array (rwdr, hydraulik; "statisch" exists there
# but is disabled=True, so it is deliberately excluded here too). Keep in sync with that file if a
# pack is ever added/enabled — this list is the server-side allowlist for `suggested_seal_type`
# (mirrors how `archetype` is validated against the archetype store's own keys), so an LLM can never
# suggest a pack the frontend doesn't actually have.
_KNOWN_SEAL_TYPES: tuple[str, ...] = ("rwdr", "hydraulik")


def _build_retriever(settings: Settings) -> Retriever:
    """L2 retriever selection (build-spec §3): the in-process keyword matcher (default — the hermetic
    CI/eval measurement instrument) OR the Qdrant production adapter (``retriever_backend=qdrant`` +
    a set ``qdrant_url``). Fail-safe: an unset url, a missing optional dep (fastembed/qdrant-client),
    or an unreachable Qdrant falls back to in-process rather than crashing startup."""
    if settings.retriever_backend == "qdrant" and settings.qdrant_url:
        try:
            from sealai_v2.knowledge.qdrant_retrieval import QdrantFachkartenRetriever

            return QdrantFachkartenRetriever(settings)
        except Exception as exc:  # noqa: BLE001 — fail safe to in-process; never crash on retrieval
            _log.warning("qdrant retriever unavailable (%s) → in-process fallback", exc)
    return InProcessRetriever()


def _build_memory_context_service(settings: Settings):
    """sealingAI Memory Architecture V1.0 (Patch 8): the Postgres store + Qdrant client + embedder
    a ``MemoryContextService`` needs. Fail-safe, same discipline as ``_build_retriever`` above: an
    unset ``database_url``/``qdrant_url``, a missing optional dep, or an unreachable DB/Qdrant
    returns None rather than crashing startup — the caller (``build_pipeline``) only invokes this
    when ``memory_context_enabled`` is set, mirroring the ``retriever``/``ground_enabled`` pattern."""
    if not settings.database_url or not settings.qdrant_url:
        return None
    try:
        from sealai_v2.db.memory_store import build_memory_store
        from sealai_v2.knowledge.qdrant_retrieval import _make_client, _make_embedder
        from sealai_v2.memory.context_assembler import MemoryContextService

        store = build_memory_store(settings)
        qdrant_client = _make_client(settings)
        embedder = _make_embedder(settings)
        return MemoryContextService(
            store=store, qdrant_client=qdrant_client, embedder=embedder
        )
    except Exception as exc:  # noqa: BLE001 — fail safe to None; never crash startup
        _log.warning(
            "memory context service unavailable (%s) → memory context inert", exc
        )
        return None


def _build_partner_registry(settings: Settings):
    """Modus F partner pool (owner business model): the Postgres adapter (dashboard-editable,
    system-of-record) when ``database_url`` is set, else the in-process registry (eval/CI hermetic —
    empty → honest "no partner listed" + zero firm names). Fail-safe: a missing dep / unreachable DB
    falls back to in-process rather than crashing startup."""
    if settings.database_url:
        try:
            from sealai_v2.db.engine import make_engine, make_sessionmaker
            from sealai_v2.db.hersteller_partner import PostgresPartnerRegistry

            return PostgresPartnerRegistry(
                make_sessionmaker(make_engine(settings.database_url))
            )
        except Exception as exc:  # noqa: BLE001 — fail safe to in-process; never crash on startup
            _log.warning(
                "partner registry DB unavailable (%s) → in-process fallback", exc
            )
    return InProcessPartnerRegistry()


# P1.4: the SERVE-path deterministic exfiltration Schranke. The eval already runs
# ``leak_detect`` over the INJECTION class (eval/harness ``_run_injection``); this wires the SAME
# pure detector into the live pipeline so a runtime system-prompt / KB-dump exfiltration is also
# defended deterministically (not only measured offline). On a leak the verbatim answer is replaced
# with a number-free, content-free refusal hedge BEFORE it can ship.
_EXFIL_HEDGE_MODEL = (
    "exfil-guard"  # sentinel: deterministic hedge, not model-generated (cf. l3-hedge)
)
_EXFIL_HEDGE_TEXT = (
    "Ich kann dazu keine internen Inhalte ausgeben (z. B. System-Vorgaben oder den vollständigen "
    "Wissensstand). Stell mir gern deine konkrete Dichtungsfrage — dann helfe ich dir fachlich weiter."
)

# P4a: optional per-turn progress sink — (stage, "start"|"end"), stage keys only (NEVER content/
# PII; the SSE doctrine test pins this). Sync + fire-and-forget so a sink can never block a seam.
ProgressSink = Callable[[str, str], None]


def _emit_progress(progress: ProgressSink | None, stage: str, status: str) -> None:
    if progress is None:
        return
    try:
        progress(stage, status)
    except Exception:  # noqa: BLE001 — a broken sink must never alter or fail a turn
        _log.warning("progress sink failed (ignored)", exc_info=True)


def _exfil_guard(answer, *, system_prompt: str, kb_claims):
    """P1.4 SERVE-path exfiltration Schranke. Runs the pure ``exfiltration_leak`` detector over the
    final answer vs the system prompt that produced it + the verbatim KB claim texts. On a leak
    (verbatim ≥160-char system-prompt span OR ≥6 verbatim KB claims) return a deterministic
    number-free refusal hedge so the verbatim leak never ships; otherwise return ``answer``
    unchanged (byte-identical pass-through). Pure — the only state is the returned Answer."""
    verdict = exfiltration_leak(
        answer=answer.text, system_prompt=system_prompt, kb_claims=list(kb_claims)
    )
    if not verdict.leaked:
        return answer, verdict
    _log.warning(
        "exfil guard tripped (serve path): system_prompt_leak=%s kb_claims_leaked=%s — answer hedged",
        verdict.system_prompt_leak,
        verdict.kb_claims_leaked,
    )
    # Mirror the L3 deterministic-hedge shape: replace text, keep the model sentinel + grounding refs.
    return (
        Answer(
            text=_EXFIL_HEDGE_TEXT,
            model=_EXFIL_HEDGE_MODEL,
            grounding_facts=answer.grounding_facts,
        ),
        verdict,
    )


@contextmanager
def _staged(timer, progress: ProgressSink | None, ms_key: str, stage: str):
    """One seam: progress start → timed body → progress end. On an exception the ``end`` is
    deliberately NOT emitted — the route's `error` frame follows the stage's `start`."""
    _emit_progress(progress, stage, "start")
    with timer.stage(ms_key):
        yield
    _emit_progress(progress, stage, "end")


def _resolve_medium(question: str, case_state) -> tuple[str, str]:
    """The medium for THIS turn (Phase 2): prefer the current message's deterministic extract, fall
    back to the recalled case-state. Returns (medium, kategorie) — ("", "") when none is stated."""
    facts = list(extract_medium_facts(question)) + list(case_state)
    medium = next((f.wert for f in facts if f.feld == "medium"), "")
    kategorie = next((f.wert for f in facts if f.feld == "medium_kategorie"), "")
    return medium, kategorie


def _trace_inputs(inputs: dict) -> dict:
    """LangSmith input view of a turn — Phase 0 (LangGraph-suitability audit): a SAFE projection
    only (booleans/lengths/hash), never the raw question. See ``obs.safe_trace`` for the policy
    this delegates to (production fails closed to ``safe_metadata_only`` regardless of what a
    caller requests)."""
    return safe_input_projection(
        question=inputs.get("question"),
        flags_repr=repr(inputs.get("flags")),
        has_untrusted=bool(inputs.get("untrusted")),
    )


def _trace_outputs(result) -> dict:
    """LangSmith output view — Phase 0 (LangGraph-suitability audit): a SAFE projection only
    (length/booleans/labels), never the raw answer text."""
    answer = getattr(result, "answer", None)
    verifier = getattr(result, "verifier", None)
    action = getattr(verifier, "action", None)
    return safe_output_projection(
        answer_text=getattr(answer, "text", None),
        answer_model=getattr(answer, "model", None),
        grounded=getattr(result, "grounded", None),
        verdict=getattr(action, "value", action) if action is not None else None,
    )


@dataclass
class Pipeline:
    generator: L1Generator
    client: LlmClient
    helper_model: ModelConfig
    understand_prompt_assembler: UnderstandPromptAssembler = field(
        default_factory=UnderstandPromptAssembler
    )
    understand_enabled: bool = True
    # G4: owner-reviewed archetype store (ArchetypeCatalog) — feeds the understand annotation + the L1
    # interview. None → no archetype recognition → byte-identical no-archetype prompt.
    archetypes: object | None = None
    verifier: L3Verifier | None = None  # None → L3 disabled (incident kill-switch only)
    catalog: TrapCatalog | None = None
    retriever: Retriever | None = (
        None  # None → L2 grounding off → every answer is "vorläufig"
    )
    matrix: object | None = (
        None  # §4 Verträglichkeitsmatrix (Gap #2) — compatibility verdicts for L2 grounding
    )
    versagensmodi: object | None = None  # Dim. 5 Versagensmodi store (Modus D Diagnose)
    partner_registry: object | None = (
        None  # Dim. 6 Hersteller-Partner pool (Modus F — PartnerRegistry; payment ≠ ranking)
    )
    engine: CalcEngine | None = (
        None  # None → M4 calc layer off → no "Berechnete Werte" block
    )
    # M5 memory: layers 1-3 (window/case-state/history) + the layer-4 cross-session seam +
    # the distiller. All None → memory is fully inert (no recall, no record, no distill call).
    memory: ConversationMemory | None = None
    cross_session: CrossSessionMemory | None = None
    distiller: Distiller | None = None
    # Medium Intelligence (Phase 2): helper-LLM research of the stated medium → provisional facts +
    # the MEDIUM tab. Default-OFF flag; L1-NEUTRAL (the facts never enter the L1 prompt), so enabling
    # only adds the tab + an isolated helper call — the eval/golden stays byte-identical. None
    # researcher OR flag off → fully inert.
    medium_researcher: MediumResearcher | None = None
    medium_intel_enabled: bool = False
    # sealingAI Memory Architecture V1.0 (Patch 8): the curated-memory context-assembly service.
    # Default-OFF flag; L1-NEUTRAL when off (service never constructed → result field stays None) —
    # same structural guarantee as Medium Intelligence above. None service OR flag off → fully inert.
    memory_context_service: MemoryContextService | None = None
    memory_context_enabled: bool = False
    # Kandidaten-Spezifikation (Produktspec v3.1): deterministic candidate Bauform/Werkstoff/DIN from the
    # case. Default-OFF flag (owner governance gate: expert Fachfreigabe + DIN-Lizenz). RWDR-scoped +
    # structurally capped (G1/G2/G3, always "vorläufig"); a render surface only — NEVER enters L1/L3, so
    # enabling keeps the prompt + eval byte-identical. Flag off → fully inert.
    produktspec_enabled: bool = False
    # 2026-07-04 routing/extraction audit: pack suggestion + free-text medium hint, both annotate-only
    # (never gates/routes), threaded through the existing `understand` LLM call. OFF -> the two new
    # Understanding fields stay None -> byte-identical prompt/eval.
    pack_suggestion_enabled: bool = False
    # V2.2 INC-COVERAGE-GATE (§4): when True, compute the deterministic coverage_status this turn and
    # attach it to the result. OFF → coverage stays None → byte-identical. (The status→mode COUPLING
    # into L1 is a separate, also-gated sub-step; this field only governs the computation/exposure.)
    coverage_gate_enabled: bool = False
    # INC-NARRATOR-CONTRACT Phase 1: assemble + attach the deterministic answer-contract (INERT — not
    # fed to L1 in Phase 1, so byte-identical). Governs computation/exposure only.
    response_contract_enabled: bool = False
    # P0-B (owner Leitbild-Audit 2026-07-02): widen the output_guard's safety net (forbidden phrase /
    # invented number / invented material) to turns WITHOUT a gegencheck_verdict — general knowledge,
    # fallarbeit before material+medium are both stated. Requires response_contract_enabled=True (this
    # flag only widens WHICH turns get a guard, not whether the guard machinery exists at all). The
    # guard-only contract (response_contract.build_guard_contract) is NEVER passed to
    # generator.generate(contract=...) — it never triggers the L1 Renderer-Modus prompt takeover, only
    # output_guard.evaluate_render(check_sentence_coverage=False). OFF -> no guard_contract is built ->
    # byte-identical to today (the existing Gegencheck-only guard path is completely unaffected either
    # way — this flag only ever ADDS a second, narrower guard path, never changes the first).
    response_contract_general_guard_enabled: bool = False
    # INC-BASELINE-HARDENING (V2.2): flag-gated Free-Narrator baseline fixes (RWDR shaft-Ø derivation
    # for the Umfangsgeschwindigkeit kern + the speed-trap / unclear-medium prompt discipline). OFF ->
    # no extra binding + no extra prompt block -> byte-identical. Governs the derivation + prompt block.
    baseline_hardening_enabled: bool = False
    material_param_table_enabled: bool = False
    # Legal-by-Design Phase D (Goal 6/7): when True, a turn whose question matched a risk-flag term
    # gets the additional system_l1.jinja `{% if risk_flags %}` instruction block. OFF -> risk_flags
    # is never passed to the generator -> byte-identical prompt. detect_risk_flags() is ALWAYS run
    # (see run()) and always attached to PipelineResult.risk_flags regardless of this flag — this
    # flag governs ONLY whether the detected terms also reach the L1 prompt.
    risk_flag_prompt_enabled: bool = False
    # P3 (audit §4.3 Versionierung / L8): the knowledge-catalog state this pipeline instance was
    # built against (core.wissensstand.compute_wissensstand) — computed ONCE in build_pipeline()
    # from the already-loaded catalogs (fachkarten/matrix/traps/versagensmodi), not per turn.
    # "" when no catalogs wired. Attached to every PipelineResult; never fed to L1/L3.
    wissensstand: str = ""
    # Phase 2B (LangGraph-suitability audit): conservative routing. OFF -> classify_route() is
    # never called at all (not just unused) -- strictly byte-identical to pre-Phase-2B behavior.
    # ON -> a route is computed (telemetry-only unless the route is a CHEAP route with zero
    # deterministic engineering signals, in which case L3 is skipped in favor of the SAME
    # existing run_parametric_guard fallback already used when the verifier is disabled --
    # no new guard mechanism is invented). Never affects engineering_case/leakage_troubleshooting/
    # material_comparison/rfq_manufacturer_brief -- those always force the full pipeline.
    route_optimization_enabled: bool = False
    route_telemetry_sink: "RouteTelemetrySink | None" = None
    # Phase 2D (LangGraph-suitability audit): controlled wiring of the Phase 2C-prepared compact
    # smalltalk_navigation prompt family. None (default) -> nothing to branch to, so
    # route_prompt_families_enabled being True with no generator wired is still a safe no-op
    # (the pipeline falls through to the unchanged full L1 generator, see run()). Only
    # constructed in build_pipeline() when settings.route_prompt_families_enabled is True.
    route_prompt_families_enabled: bool = False
    smalltalk_generator: "SmalltalkGenerator | None" = None

    # P2: in-flight background remember tasks, keyed by (tenant_id, session_id). Filled only
    # when a distiller is wired; drained by ``flush_memory`` (the ordering guard).
    _pending_remember: dict[tuple[str, str], asyncio.Task] = field(
        default_factory=dict, init=False, repr=False
    )

    @traceable(
        run_type="chain",
        name="v2_turn",
        process_inputs=_trace_inputs,
        process_outputs=_trace_outputs,
    )
    async def run(
        self,
        question: str,
        *,
        tenant: TenantContext,
        flags: Flags | None = None,
        params: dict | None = None,
        session: SessionContext | None = None,
        untrusted: tuple[UntrustedContent, ...] = (),
        progress: ProgressSink | None = None,
    ) -> PipelineResult:
        scope = require_tenant(tenant)  # P0 — fail-closed if tenant missing/empty
        flags = flags or Flags()
        timer = TurnTimer()  # per-stage timing; pure bookkeeping, never alters results
        # Legal-by-Design Phase D: deterministic, ALWAYS-on detection (no LLM, cannot be perturbed
        # by anything downstream) — always attached to the result (risk_flags= below); only reaches
        # the L1 prompt when risk_flag_prompt_enabled is separately on (see the generate() calls).
        risk_flags = detect_risk_flags(question)
        # M6b quarantine: untrusted content reaches L1 ONLY as delimited DATA (never grounding, never
        # cited). Empty → None → byte-identical no-op. The grounding path cannot consume it (keystone).
        untrusted_data = [
            {"text": u.text, "origin": u.origin} for u in untrusted
        ] or None

        # P2 ordering guard: a previous turn's background remember (distill + record) must
        # land before THIS turn's recall on the same session — the wait (usually 0) is the
        # visible cost of the guard, so it is timed.
        if self.memory is not None and session is not None:
            with timer.stage("flush_ms"):
                await self.flush_memory(
                    tenant_id=scope.tenant_id, session_id=session.session_id
                )

        # M5 recall (before answering): inert when memory/session absent → byte-identical no-op.
        with _staged(timer, progress, "recall_ms", "recall"):
            mem = stages.recall(
                self.memory,
                self.cross_session,
                tenant_id=scope.tenant_id,
                session=session,
                question=question,
            )
        # This-session case-state (L2) and cross-session durable facts (L4) are kept SEPARATE: the
        # durable facts surface under their own honest "aus früheren Gesprächen — bei Bedarf
        # bestätigen" frame and (below) do NOT feed the deterministic calc binder — a remembered
        # cross-session value must never be treated as a current/confirmed input.
        # G1 (V2.1 Inc 1): build the typed Case at the generalisation point, then project to the
        # byte-identical list[dict] the L1 prompt + L3 topic-scope consume (owner decision 2 —
        # Jinja unchanged, so the eval stays unperturbed). The typed slots fill in later increments.
        case = Case.from_case_state(mem.case_state, question=question)
        case_context = case.to_prompt_context()
        # Medium Intelligence (Phase 2): research the stated medium → provisional facts + the MEDIUM
        # tab. Gated (default-off) + fail-safe + L1-NEUTRAL (never enters the L1 prompt). Inert when
        # off / no researcher / no medium stated.
        medium_intelligence: MediumIntelligence | None = None
        if self.medium_intel_enabled and self.medium_researcher is not None:
            _medium, _kategorie = _resolve_medium(question, mem.case_state)
            if _medium:
                medium_intelligence = await self.medium_researcher.research(
                    _medium, _kategorie
                )
        # sealingAI Memory Architecture V1.0 (Patch 8): assemble the bounded curated-memory context
        # bundle. Gated (default-off) + fail-safe (MemoryContextService.assemble() never raises into
        # the turn) + L1-NEUTRAL in this patch (a render/serializer surface only — NOT injected into
        # the L1 prompt yet, see memory/context_assembler.py's module docstring). Inert when off / no
        # service wired.
        memory_context: MemoryContextBundle | None = None
        if self.memory_context_enabled and self.memory_context_service is not None:
            memory_context = await self.memory_context_service.assemble(
                question,
                tenant_id=scope.tenant_id,
                now=datetime.now(timezone.utc).isoformat(),
            )
        # Modus E: deterministic Gegencheck verdict - None unless the case carries an existing
        # seal material AND a medium. Backend owns the verdict; L1 narrates the why via the
        # matrix_facts grounded below. Never affirms suitability (E4-1). Pure + sync, no I/O.
        gegencheck_verdict = stages.gegencheck(
            self.matrix, case, tenant_id=scope.tenant_id
        )
        # Modus D: deterministic Diagnose - None unless the turn reports a recognised symptom.
        # Backend owns the grounded(draft) ursache/fix; draft -> provisional. Pure + sync, no I/O.
        diagnosis = stages.diagnose(
            self.versagensmodi, question, tenant_id=scope.tenant_id
        )
        # Modus G: deterministic Decode - None unless a designation (with dims) is present.
        # Result-side structured parse + the §9.2 equivalence boundary. Pure + sync, no I/O.
        decode_result = stages.decode(question)
        # Modus F: capable manufacturers BY CAPABILITY (neutral). None unless an alternatives/
        # manufacturer request; grounded_data=False with the owner-pending empty seed, or (L6,
        # P0-C) grounded_data=False "assessment needed first" when no Gegencheck verdict exists yet.
        # The verdict precondition honours a THIS-turn verdict first; failing that, it falls back
        # to a verdict re-derived from the session's PERSISTED case-state (stages.
        # gegencheck_from_case_state) — so an assessment made in an EARLIER turn still gates a
        # manufacturer question in a LATER turn that doesn't restate material/medium (Akzeptanz-
        # kriterium 2/4). gegencheck_verdict itself (Modus E narration) is UNCHANGED by this.
        # (P0-C review fix) The fallback is a REAL matrix query — only worth computing when THIS
        # turn was even asking about manufacturers; `is_alternativen_request` mirrors alternativen's
        # own keyword gate so unrelated turns (most of them) never pay for it.
        alternativen_verdict = None
        if self.partner_registry is not None and stages.is_alternativen_request(
            question
        ):
            alternativen_verdict = (
                gegencheck_verdict
                or stages.gegencheck_from_case_state(
                    self.matrix, mem.case_state, tenant_id=scope.tenant_id
                )
            )
        alternativen_result = stages.alternativen(
            self.partner_registry,
            question,
            alternativen_verdict,
            tenant_id=scope.tenant_id,
        )
        # Kandidaten-Spezifikation (Produktspec v3.1): deterministic candidate Bauform/Werkstoff/DIN.
        # FLAG-gated (default OFF) + RWDR-scoped + structurally capped (always "vorläufig", G1/G2/G3) +
        # fail-open. A render surface only — never injected into L1/L3 (the prompt stays byte-identical).
        seal_type = next(
            (
                f.wert
                for f in mem.case_state
                if f.feld in ("dichtungstyp", "seal_type") and f.wert
            ),
            "",
        )
        kandidaten_spec = compute_kandidaten_spec(
            mem.case_state,
            question,
            enabled=self.produktspec_enabled,
            seal_type=seal_type,
        )
        durable_context = [{"feld": f.feld, "wert": f.wert} for f in mem.durable]
        conversation_window = [{"role": t.role, "text": t.text} for t in mem.window]

        # P1: soft understand is annotate-only (Intent NEVER gates/routes; it feeds only the
        # API intent field via PipelineResult.understanding) — so it runs CONCURRENT with the
        # answer chain instead of serializing in front of L1. Awaited after the chain; a chain
        # failure cancels it (same failure surface as the serial order, pure reordering).
        understand_task: asyncio.Task | None = None
        understanding: Understanding | None = None
        if self.understand_enabled:
            archetype_keys = (
                tuple(self.archetypes.keys) if self.archetypes is not None else ()
            )
            # 2026-07-04 routing/extraction audit: only ask for a pack suggestion / medium hint when
            # the flag is on AND the case doesn't already have a settled value — never re-suggest
            # once resolved, and OFF keeps this call byte-identical to before (empty tuple / True are
            # the exact defaults of the understand prompt).
            known_seal_types: tuple[str, ...] = ()
            medium_already_known = True
            if self.pack_suggestion_enabled:
                known_seal_types = () if seal_type else _KNOWN_SEAL_TYPES
                medium_already_known = any(
                    f.feld == "medium" and f.wert for f in mem.case_state
                )

            async def _understand_timed():
                with _staged(timer, progress, "understand_ms", "understand"):
                    return await stages.understand(
                        self.client,
                        self.helper_model,
                        question,
                        prompt_assembler=self.understand_prompt_assembler,
                        archetype_keys=archetype_keys,
                        known_seal_types=known_seal_types,
                        medium_already_known=medium_already_known,
                    )

            understand_task = asyncio.create_task(_understand_timed())

        try:
            with _staged(timer, progress, "ground_ms", "ground"):
                retrieval = await stages.ground(
                    self.retriever,
                    self.matrix,
                    question,
                    tenant_id=scope.tenant_id,
                    case_facts=mem.case_state,
                )
            grounding_facts = (
                retrieval.grounding_facts
            )  # reviewed Fachkarten → compute + (Step A) verify
            # Gap #2 (Step A): the §4 matrix verdicts join the Fachkarten as belegte Fakten for L1 only
            # (their own channel; L3 wiring is Step B). Empty → byte-identical no-matrix prompt.
            l1_grounding = grounding_facts + retrieval.matrix_facts
            # M8-A provenance binding: remembered case facts → calc inputs, DETERMINISTIC + DECLARED
            # (owner-confirmed table; fail-closed on ambiguity — never LLM-judged). Explicit caller
            # params (eval fixtures) take precedence per key. Empty everywhere → byte-identical no-op.
            inline_facts = extract_inline(question)
            if self.baseline_hardening_enabled:
                # INC-BASELINE-HARDENING: Welle = d1 bei RWDR — derive the shaft Ø from a bare
                # designation ("RWDR 40x62x8") so the Umfangsgeschwindigkeit kern can fire even
                # without an explicit "40 mm". A TYPED shaft Ø still wins over the derived one
                # (overlay order: typed inline > derived); OFF -> byte-identical no-op.
                inline_facts = merge_inline(extract_rwdr_shaft(question), inline_facts)
            bound = bind_params(
                merge_inline(mem.case_state, inline_facts)
            )  # L4 durable facts excluded — never a calc input; inline overlay: fresh > recalled
            merged_params = dict(bound.params)
            param_origins = dict(bound.origins)
            for key, value in (params or {}).items():
                merged_params[key] = value
                param_origins[key] = "Parameter (explizit übergeben)"
            # Stage order: verstehen → ground → COMPUTE → answer → verify → (render). compute() runs
            # after ground so Fachkarten-property inputs (qualitative swelling flag) are available.
            with _staged(timer, progress, "compute_ms", "compute"):
                calc = await stages.compute(
                    self.engine,
                    merged_params or None,
                    grounding_facts=grounding_facts,
                    param_origins=param_origins or None,
                )
            if (
                bound.notes
            ):  # surfaced fail-closed drops — visible to L1 + render, never silent
                calc = CalcResult(
                    computed=calc.computed,
                    not_computed=calc.not_computed,
                    notes=calc.notes + bound.notes,
                )
            # G4: await understand BEFORE generate so a recognised archetype can guide the L1 prompt.
            # It ran CONCURRENT with ground+compute (created above); awaiting it here partially reverts
            # the P1 hidden-latency optimisation for the archetype path (owner-accepted; latency
            # measured). Annotate-only — the archetype NEVER gates/routes; it only injects the matching
            # reviewed profile's interview questions + blind spots as advisory L1 context.
            if understand_task is not None:
                understanding = await understand_task
            archetype_context = self._archetype_context(understanding)
            pack_suggestion_context = self._pack_suggestion_context(understanding)
            medium_hint_context = self._medium_hint_context(understanding)

            # Phase 2B (LangGraph-suitability audit): conservative routing. OFF (default) ->
            # this whole block is skipped -- classify_route() is never invoked, so behavior is
            # strictly byte-identical to pre-Phase-2B. ON -> compute a route from the SAME
            # deterministic signals already computed above (decode_result/diagnosis/
            # gegencheck_verdict/mem.case_state) + the already-running understand() intent.
            # skip_l3_for_route stays False unless the route is a CHEAP route with ZERO
            # deterministic engineering signals -- any signal, or any doubt, keeps it False.
            route_decision = None
            skip_l3_for_route = False
            # Phase 2D: whether THIS turn will actually use the compact smalltalk_navigation
            # prompt instead of the full L1 prompt. Stays False (byte-identical generate() call)
            # unless ALL of: route_optimization_enabled, route_prompt_families_enabled, the
            # classified route is smalltalk_navigation, forced_full_pipeline is False,
            # deterministic_signal_count is 0 (redundant with the route check, kept explicit per
            # the audit's own required-condition list), AND a smalltalk_generator is actually
            # wired (build_pipeline() only constructs one when the flag is on).
            smalltalk_prompt_active = False
            if self.route_optimization_enabled:
                _route_started = time.monotonic()
                route_decision = classify_route(
                    question,
                    case_state_nonempty=bool(mem.case_state),
                    decode_result=decode_result,
                    diagnosis=diagnosis,
                    gegencheck_verdict=gegencheck_verdict,
                    intent=understanding.intent if understanding is not None else None,
                )
                # Phase 2B safety correction: a stress test against the real eval seed cases (with
                # an adversarially-uniform "wissensfrage" intent guess) found real cases where
                # general_sealing_knowledge/material_knowledge signals under-fired on natural-
                # language phrasing no finite keyword list fully covers (chemical-resistance
                # claims, application descriptions without an explicit question form, etc.).
                # Rather than chase an ever-expanding regex list, the L3-bypass itself is
                # restricted to smalltalk_navigation ONLY -- the one route whose false-negative
                # surface is structurally small (a message that is genuinely just smalltalk
                # essentially never hides an engineering claim, since it doesn't reference the
                # domain at all). general_sealing_knowledge/material_knowledge are still computed
                # and labeled for telemetry, but never skip L3 in this phase -- see the Phase 2B
                # report for the full analysis and the recommended Phase 2C (a stronger content-
                # level guard, not more regexes) before extending this further.
                skip_l3_for_route = (
                    route_decision.route is RouteName.SMALLTALK_NAVIGATION
                    and not route_decision.forced_full_pipeline
                )
                # Phase 2D: the compact prompt is strictly NARROWER than the L3-bypass condition
                # above (both must hold: smalltalk_navigation is the route AND the pipeline is
                # actually willing to skip L3 for it) -- a smalltalk turn never gets the cheap
                # prompt while still being forced through the full path for some other reason.
                smalltalk_prompt_active = (
                    self.route_prompt_families_enabled
                    and self.smalltalk_generator is not None
                    and skip_l3_for_route
                    and route_decision.deterministic_signal_count == 0
                )
                if self.route_telemetry_sink is not None:
                    try:
                        self.route_telemetry_sink.record(
                            RouteTelemetry(
                                route_name=route_decision.route.value,
                                route_reason=route_decision.reason,
                                route_confidence=route_decision.confidence,
                                forced_full_pipeline=route_decision.forced_full_pipeline,
                                deterministic_signal_count=route_decision.deterministic_signal_count,
                                route_latency_ms=(time.monotonic() - _route_started)
                                * 1000.0,  # i5-ok: sec->ms unit conversion, not an engineering value
                                prompt_family=(
                                    "smalltalk_navigation"
                                    if smalltalk_prompt_active
                                    else None
                                ),
                                l3_bypassed=skip_l3_for_route,
                            )
                        )
                    except Exception:  # noqa: BLE001 -- telemetry must never break/mask a real turn
                        pass
            # V2.2 INC-COVERAGE-GATE (§4/§5): deterministic case-level coverage from the grounded
            # evidence (chemical = gegencheck verdict; archetype = profile), computed BEFORE generate
            # so it can hard-cap the allowed L1 mode. Flag-gated → None when OFF (byte-identical). The
            # LLM consumes the status; it never sets it (I-COV-1).
            coverage = None
            if self.coverage_gate_enabled:
                from sealai_v2.core.coverage import coverage_for

                coverage = coverage_for(gegencheck_verdict, archetype_context)
            # INC-NARRATOR-CONTRACT: assemble the deterministic answer-contract from the SAME grounded
            # evidence, BEFORE generate. Phase 2 — when the flag is ON it is PASSED to generate (renderer
            # mode); OFF → contract is None → not passed → the L1 prompt is byte-identical.
            contract = None
            if self.response_contract_enabled:
                from sealai_v2.core.coverage import coverage_for
                from sealai_v2.core.response_contract import build_contract

                _rc = build_contract(
                    coverage=coverage
                    if coverage is not None
                    else coverage_for(gegencheck_verdict, archetype_context),
                    grounding_facts=l1_grounding,
                    gegencheck_verdict=gegencheck_verdict,
                    calc=calc,
                )
                contract = _rc.to_dict() if _rc is not None else None
            # P0-B: on turns where the Gegencheck-shaped contract above is None (no verdict — general
            # knowledge / fallarbeit without material+medium yet), build a NARROWER guard-only contract
            # from the SAME grounding — never passed to generate() (see build_guard_contract's
            # docstring for why), only to the output_guard call below. OFF -> guard_contract stays
            # None -> the guard-wiring block's effective contract is unchanged -> byte-identical.
            guard_contract = None
            if (
                self.response_contract_enabled
                and self.response_contract_general_guard_enabled
                and contract is None
            ):
                from sealai_v2.core.response_contract import build_guard_contract

                _gc = build_guard_contract(grounding_facts=l1_grounding, calc=calc)
                guard_contract = _gc.to_dict() if _gc is not None else None
            # Material-Parameter-Tabelle: grounded kernel parameters for the materials NAMED in the
            # question — injected so L1 RENDERS them as a table (no number invention). Flag-gated ->
            # None when OFF (byte-identical).
            material_params = None
            if self.material_param_table_enabled:
                from sealai_v2.knowledge.material_parameters import (
                    material_parameters_for,
                )

                material_params = material_parameters_for(question) or None
            with _staged(timer, progress, "generate_ms", "generate"):
                # Phase 2D: the ONLY branch point where the compact smalltalk_navigation prompt
                # can ever answer a turn. self.generator (L1Generator, the full engineering
                # prompt) is completely untouched below -- every route except a fully-qualified
                # smalltalk turn (see smalltalk_prompt_active's computation above) takes the
                # EXACT same call it always has.
                if smalltalk_prompt_active and self.smalltalk_generator is not None:
                    answer = await self.smalltalk_generator.generate(question)
                else:
                    answer = await self.generator.generate(
                        question,
                        flags=flags,
                        grounding_facts=l1_grounding,
                        calc=calc,
                        case_context=case_context
                        or None,  # empty → None → byte-identical no-memory prompt
                        durable_context=durable_context
                        or None,  # empty → None → byte-identical no-cross-session prompt
                        conversation_window=conversation_window or None,
                        untrusted=untrusted_data,  # empty → None → byte-identical no-untrusted prompt
                        archetype_context=archetype_context,  # None → byte-identical no-archetype prompt
                        pack_suggestion_context=pack_suggestion_context,  # None → byte-identical
                        medium_hint_context=medium_hint_context,  # None → byte-identical
                        coverage=coverage,  # None → byte-identical no-coverage-gate prompt
                        contract=contract,  # None → byte-identical; ON → renderer-mode (Phase 2)
                        baseline_hardening=self.baseline_hardening_enabled,  # False → byte-identical
                        material_params=material_params,  # None → byte-identical no-table
                        risk_flags=(
                            list(risk_flags) if self.risk_flag_prompt_enabled else None
                        ),  # None → byte-identical
                    )
            draft = (
                answer  # first-pass L1 draft, captured before L3 may correct/hedge it
            )

            # INC-NARRATOR-CONTRACT Phase 3/5: the claim-level output guard on the rendered answer.
            # Fail-closed coverage — on BLOCK, regenerate ONCE with a deterministic correction note, then
            # re-score; the verdict is attached + logged (GOVERNANCE). Flag-gated + only with a contract →
            # OFF / no-contract = no-op = byte-identical. The (re)generated answer still goes through L3.
            # P0-B: the guard now ALSO runs against `guard_contract` (the narrower, non-renderer contract
            # built above) when there was no gegencheck-shaped `contract`. `check_sentence_coverage` is
            # False for that path (see build_guard_contract's docstring — L1 was never instructed to
            # stay inside the contract, so the strict "every technical sentence maps to a claim" check
            # would be nonsensical there). Regeneration passes `contract=contract` — the ORIGINAL
            # (renderer-mode-or-None) variable, NEVER `guard_contract` — so a guard-only turn's
            # regeneration still never enters Renderer-Modus, only receives the correction_note.
            guard = None
            _effective_contract = contract if contract is not None else guard_contract
            if self.response_contract_enabled and _effective_contract is not None:
                from sealai_v2.core.output_guard import (
                    correction_note as _guard_note,
                    evaluate_render as _guard_eval,
                    known_inputs as _guard_known,
                )

                _check_sentence_coverage = contract is not None
                _kv, _km = _guard_known(question)
                _gr = _guard_eval(
                    answer_text=answer.text,
                    contract=_effective_contract,
                    known_values=_kv,
                    known_materials=_km,
                    check_sentence_coverage=_check_sentence_coverage,
                )
                if _gr.action == "BLOCK":
                    with _staged(timer, progress, "regenerate_ms", "regenerate"):
                        answer = await self.generator.generate(
                            question,
                            flags=flags,
                            grounding_facts=l1_grounding,
                            calc=calc,
                            case_context=case_context or None,
                            durable_context=durable_context or None,
                            conversation_window=conversation_window or None,
                            untrusted=untrusted_data,
                            archetype_context=archetype_context,
                            pack_suggestion_context=pack_suggestion_context,
                            medium_hint_context=medium_hint_context,
                            coverage=coverage,
                            contract=contract,
                            baseline_hardening=self.baseline_hardening_enabled,
                            correction_note=_guard_note(_gr),
                            risk_flags=(
                                list(risk_flags)
                                if self.risk_flag_prompt_enabled
                                else None
                            ),
                        )
                    _gr2 = _guard_eval(
                        answer_text=answer.text,
                        contract=_effective_contract,
                        known_values=_kv,
                        known_materials=_km,
                        check_sentence_coverage=_check_sentence_coverage,
                    )
                    _log.info(
                        "GOVERNANCE output_guard: regenerated (first=%s -> after=%s); first_violations=%s",
                        _gr.action,
                        _gr2.action,
                        [v.kind for v in _gr.violations],
                    )
                    _gr = _gr2
                guard = _gr.to_dict()

            verdict: VerifierVerdict | None = None
            if (
                self.verifier is not None
                and self.catalog is not None
                and not skip_l3_for_route
            ):
                with _staged(timer, progress, "verify_ms", "verify"):
                    answer, verdict = await stages.verify(
                        self.verifier,
                        self.generator,
                        self.catalog,
                        question,
                        answer,
                        flags=flags,
                        grounding_facts=grounding_facts,
                        computed_values=calc.computed,
                        not_computed=calc.not_computed,
                        matrix_facts=retrieval.matrix_facts,  # Gap #2 Step B: matrix = L3 correction source
                        # OPTIMIZE_BACKLOG #5: full draft context → topic-scoped correction + non-degraded regen
                        calc=calc,
                        case_context=case_context or None,
                        durable_context=durable_context or None,
                        conversation_window=conversation_window or None,
                        untrusted=untrusted_data,
                        # §9.2 guard fires ONLY on a part-comparison turn (decode parsed a designation)
                        comparison_context=bool(decode_result),
                    )
            else:
                # P0.3: the DETERMINISTIC parametric Schranke is pure (no LLM) and must hold even when
                # the L3 verifier is disabled (incident kill-switch) or unconfigured — it would
                # otherwise vanish together with the LLM critic it currently lives inside.
                with _staged(timer, progress, "verify_ms", "verify"):
                    answer, verdict = run_parametric_guard(
                        answer,
                        computed_values=calc.computed,
                        not_computed=calc.not_computed,
                        comparison_context=bool(decode_result),
                    )

            # P1.4: SERVE-path deterministic exfiltration Schranke. Runs AFTER the final answer is set
            # (post verify if/else) and BEFORE cite, on the answer that would actually ship. The leak
            # reference is the STATIC doctrine system prompt (flags only) — the SAME reference the eval
            # uses (eval/harness ``_run_injection``) and the confidential surface we defend; it is
            # non-empty (the rendered doctrine is ~15k chars), so the ≥160-char verbatim check is real.
            # NOT the per-turn assembly: that legitimately embeds reviewed correction facts an L3 hedge
            # is allowed to state verbatim (would false-fire). KB dumps are the separate kb_claims
            # channel (Fachkarten + §4 matrix fact texts). Conservative thresholds → no false-fire on a
            # normal grounded answer; on a real leak the verbatim dump is swapped for a number-free
            # refusal before cite/return.
            answer, _exfil_verdict = _exfil_guard(
                answer,
                system_prompt=self.generator.doctrine_system_prompt(flags=flags),
                kb_claims=[f.text for f in l1_grounding],
            )

            with _staged(timer, progress, "cite_ms", "cite"):
                answer = await stages.cite(answer)  # stub → unchanged

            # M5 remember (after answering): record the turn + distill STATED facts into case-state.
            # No-op (and no distill LLM call) when memory/session absent — distilling AFTER the answer
            # means it can never perturb the turn it observed. (Timed only when it actually runs, so
            # the timing line omits ``distill_ms`` on the single-turn/no-session path.)
            # P2: with a distiller wired, the distill LLM call moves OFF the user-facing path —
            # a background task, ordering-guarded by ``flush_memory`` (next recall / memory read /
            # user mutation). Distiller-less remember (pure in-process record, no LLM) stays inline.
            scheduled_background = False
            if self.memory is not None and session is not None:
                if self.distiller is not None:
                    self._schedule_remember(
                        timer,
                        tenant_id=scope.tenant_id,
                        session=session,
                        question=question,
                        answer_text=answer.text,
                    )
                    scheduled_background = True
                else:
                    with timer.stage("distill_ms"):
                        await stages.remember(
                            self.memory,
                            self.distiller,
                            tenant_id=scope.tenant_id,
                            session=session,
                            question=question,
                            answer=answer.text,
                            cross_session=self.cross_session,
                        )
                    # M8: settle the derived slice from the merged inputs (no distiller path)
                    self.recompute_derived_for(
                        tenant_id=scope.tenant_id, session_id=session.session_id
                    )
        except BaseException:
            if understand_task is not None:
                if understand_task.done():
                    understand_task.exception()  # consume — the chain error is primary
                else:
                    understand_task.cancel()
            raise

        # ``understanding`` was awaited before generate (G4) — already set (or None if understand off).

        # One JSON line per turn (stage durations + total + turn id; no PII). ``total_ms`` is
        # frozen HERE — the user-facing latency; a backgrounded remember emits the line itself
        # once its ``distill_ms`` is known (so the line stays complete and stays one per turn).
        timer.finish()
        if not scheduled_background:
            timer.emit()
        return PipelineResult(
            question=question,
            tenant_id=scope.tenant_id,
            flags=flags,
            understanding=understanding,
            answer=answer,
            grounded=retrieval.grounded,
            verified=verdict is not None,
            cited=False,
            verifier=verdict,
            draft_answer=draft,
            grounding_facts=l1_grounding,  # Fachkarten + §4 matrix verdicts (the cited grounding)
            computed_values=calc.computed,
            not_computed=calc.not_computed,
            calc_notes=calc.notes,
            gegencheck=gegencheck_verdict,
            coverage=coverage,
            contract=contract,
            guard=guard,
            diagnose=diagnosis,
            decode=decode_result,
            alternativen=alternativen_result,
            medium_intelligence=medium_intelligence,
            memory_context=memory_context,
            kandidaten_spec=kandidaten_spec,
            wissensstand=self.wissensstand,
            risk_flags=risk_flags,
        )

    def _archetype_context(self, understanding: Understanding | None) -> dict | None:
        """G4: map a recognised soft archetype to its reviewed profile's advisory L1 context
        (interview questions + blind spots). None when there is no archetype / no store / no match —
        so the no-archetype path stays byte-identical. Annotate-only; it never gates or routes."""
        if understanding is None or self.archetypes is None:
            return None
        key = getattr(understanding, "archetype", None)
        if not key:
            return None
        profile = self.archetypes.by_archetype(key)
        if profile is None:
            return None
        return {
            "archetyp": profile.key,
            "interview_fragen": list(profile.interview_fragen),
            "blinde_flecken": list(profile.blinde_flecken),
        }

    def _pack_suggestion_context(
        self, understanding: Understanding | None
    ) -> dict | None:
        """2026-07-04 routing/extraction audit: map a recognised soft pack suggestion to its L1
        advisory context. None when there is no suggestion (flag off, LLM found nothing, or the
        value failed the server-side allowlist in stages.understand) — so the no-suggestion path
        stays byte-identical. Annotate-only; it never gates or routes or opens a pack itself."""
        if understanding is None or not self.pack_suggestion_enabled:
            return None
        seal_type = getattr(understanding, "suggested_seal_type", None)
        if not seal_type:
            return None
        return {"seal_type": seal_type}

    def _medium_hint_context(self, understanding: Understanding | None) -> dict | None:
        """2026-07-04 routing/extraction audit: map a captured free-text medium hint (the
        deterministic vocabulary found nothing this turn) to its L1 advisory context. None when
        there is no hint (flag off, medium already known, or the LLM found nothing) — so the
        no-hint path stays byte-identical. Annotate-only; never committed as a case-state fact."""
        if understanding is None or not self.pack_suggestion_enabled:
            return None
        hint = getattr(understanding, "medium_hint", None)
        if not hint:
            return None
        return {"medium_hint": hint}

    def compute_for(self, *, tenant_id: str, session_id: str) -> DerivedComputation:
        """M8: recompute the kernel from the session's CURRENT settled inputs, PERSIST the derived
        slice (wholesale replace — a stale value can never survive), and return the full result
        (derived + not_computed + notes) for the read surface (/compute, the panel). No engine or no
        memory → an empty result. Pure deterministic compute (no LLM); inputs via the recall seam."""
        if self.engine is None or self.memory is None:
            return DerivedComputation(derived=(), calc=CalcResult())
        inputs = self.memory.recall(
            tenant_id=tenant_id, session_id=session_id
        ).case_state
        comp = recompute_derived(inputs, self.engine)
        self.memory.set_derived(
            tenant_id=tenant_id, session_id=session_id, derived=comp.derived
        )
        return comp

    def recompute_derived_for(
        self, *, tenant_id: str, session_id: str
    ) -> tuple[DerivedFact, ...]:
        """The mutation-channel projection of ``compute_for``: recompute + persist, return just the
        derived facts. Called on every input-mutation channel (background remember after distill;
        edit/forget routes)."""
        return self.compute_for(tenant_id=tenant_id, session_id=session_id).derived

    async def flush_memory(self, *, tenant_id: str, session_id: str) -> None:
        """P2 ordering guard: await this session's in-flight background remember so the
        distilled case-state has landed before any subsequent recall, memory read (chips
        re-fetch), or user mutation (edit/forget). No pending task → no-op. The background
        wrapper is fail-safe (never raises); a task stranded on a dead/foreign event loop
        (test topologies — prod uvicorn and the eval are single-loop) is dropped with a
        warning instead of raising."""
        task = self._pending_remember.get((tenant_id, session_id))
        if task is None:
            return
        try:
            await task
        except (
            RuntimeError
        ) as exc:  # foreign/dead loop — drop the entry, never fail a read
            self._pending_remember.pop((tenant_id, session_id), None)
            _log.warning("flush_memory dropped an unawaitable remember task: %s", exc)

    async def flush_all_memory(self, *, tenant_id: str) -> None:
        """Same P2 ordering guard as ``flush_memory``, but for every one of this tenant's
        in-flight background remembers at once — for an endpoint that reads ACROSS all of a
        tenant's sessions (the "Fälle"-Sidebar case list) rather than one known ``session_id``,
        so it has no single key to flush. Snapshots the task list before awaiting (each task's
        own done-callback removes itself from ``_pending_remember``, so iterating the live dict
        while awaiting would be a mutate-during-iterate bug)."""
        tasks = [
            t for (tid, _sid), t in self._pending_remember.items() if tid == tenant_id
        ]
        for task in tasks:
            try:
                await task
            except RuntimeError as exc:  # foreign/dead loop — never fail the read
                _log.warning(
                    "flush_all_memory dropped an unawaitable remember task: %s", exc
                )

    def _schedule_remember(
        self,
        timer: TurnTimer,
        *,
        tenant_id: str,
        session: SessionContext,
        question: str,
        answer_text: str,
    ) -> None:
        key = (tenant_id, session.session_id)
        task = asyncio.create_task(
            self._remember_background(
                timer,
                tenant_id=tenant_id,
                session=session,
                question=question,
                answer_text=answer_text,
            )
        )
        self._pending_remember[key] = task

        def _deregister(t: asyncio.Task) -> None:
            if self._pending_remember.get(key) is t:
                del self._pending_remember[key]

        task.add_done_callback(_deregister)

    async def _remember_background(
        self,
        timer: TurnTimer,
        *,
        tenant_id: str,
        session: SessionContext,
        question: str,
        answer_text: str,
    ) -> None:
        """The deferred remember (distill LLM call + record_turn). Fail-safe: an error here is
        logged-only — the answer already went out, so the worst case is a lost memory record
        for this turn, never a failed request and never a guessed fact (the distiller's own
        numeric-trace guard is untouched). Emits the turn's timing line on completion."""
        try:
            with timer.stage("distill_ms"):
                await stages.remember(
                    self.memory,
                    self.distiller,
                    tenant_id=tenant_id,
                    session=session,
                    question=question,
                    answer=answer_text,
                    cross_session=self.cross_session,
                )
            # M8: settle the derived slice from the just-distilled inputs (chat channel). Inside the
            # try so a recompute fault is caught by the same fail-safe (a lost derived slice is never
            # a failed request; the next read/mutation recomputes anyway).
            self.recompute_derived_for(
                tenant_id=tenant_id, session_id=session.session_id
            )
        except Exception as exc:  # noqa: BLE001 — a background task must never die unhandled
            _log.warning(
                "background remember failed (turn memory lost): %s: %s",
                type(exc).__name__,
                exc,
            )
        finally:
            timer.emit()


def build_pipeline(
    settings: Settings,
    client: LlmClient | None = None,
    *,
    l1_model: str | None = None,
    client_for: Callable[[str], LlmClient] | None = None,
) -> Pipeline:
    """Wire the pipeline from settings + injected client(s). Two modes, both default-preserving:
    pass a single ``client`` (all roles share it — the test/default path, byte-identical) OR a
    ``client_for(provider)`` factory for per-role routing (a mixed model-swap cell). The template
    file reads happen once here (assembler construction), keeping the pure generator/verifier
    I/O-free. L3 is ALWAYS-ON (core trust layer) unless ``verify_enabled`` is off (incident only)."""
    if client_for is None and client is None:
        raise RuntimeError(
            "build_pipeline needs either a single ``client`` (all roles share it) or a "
            "``client_for`` provider factory (per-role routing) — never neither."
        )
    # Single-client mode: ignore provider, return the one client (preserves the fake-client tests
    # and the default object graph). Factory mode: each role resolves its provider's client.
    resolve = client_for if client_for is not None else (lambda _provider: client)
    l1_client = resolve(settings.l1_provider or settings.provider)
    verifier_client = resolve(settings.verifier_provider or settings.provider)
    helper_client = resolve(settings.helper_provider or settings.provider)

    assembler = PromptAssembler()
    _l1_model_name = l1_model or settings.l1_model
    # Phase 1 (LangGraph-suitability audit): the L1 doctrine-only prompt (flags only — no
    # grounding/case/memory data, identical to L1Generator.doctrine_system_prompt / the
    # exfiltration-gate reference) is a genuinely STATIC string, so a hash-versioned cache key is
    # safe to switch to now. Helper/verifier keep their literal keys for this phase — neither has
    # an equally clean static-only prompt available without a prompt split (out of scope here; see
    # the audit's routing-proposal phase).
    _l1_static_doctrine = assembler.system_prompt(
        flags=Flags(
            compliance_hint=settings.default_compliance_hint,
            safety_critical=settings.default_safety_critical,
        )
    )
    l1_cfg = ModelConfig(
        model=_l1_model_name,
        temperature=settings.l1_temperature,
        cache_key=build_prompt_cache_key("l1", _l1_model_name, _l1_static_doctrine),
        stage="l1",
    )
    helper_cfg = ModelConfig(
        model=settings.helper_model,
        temperature=settings.helper_temperature,
        cache_key="sealai-v2-helper",
        stage="helper",
    )
    generator = L1Generator(l1_client, assembler, l1_cfg)
    medium_researcher = MediumResearcher(
        helper_client, MediumResearchPromptAssembler(), helper_cfg
    )

    verifier: L3Verifier | None = None
    catalog: TrapCatalog | None = None
    if settings.verify_enabled:
        catalog = load_traps()
        verifier_cfg = ModelConfig(
            model=settings.verifier_model,
            temperature=settings.verifier_temperature,
            cache_key="sealai-v2-verifier",
            stage="verifier",
        )
        verifier = L3Verifier(
            verifier_client, VerifierPromptAssembler(), verifier_cfg, catalog
        )

    # L2 grounding: in-process Fachkarten retriever (M3). A Qdrant adapter swaps in here by config
    # (build-spec §3) behind the same Retriever Protocol — no core change.
    retriever: Retriever | None = (
        _build_retriever(settings) if settings.ground_enabled else None
    )
    # L2 grounding (Gap #2): the §4 Verträglichkeitsmatrix — file-backed reviewed seed behind the
    # CompatibilityMatrix Protocol (a DB/Qdrant adapter is the deferred prod path). Under the same
    # ground_enabled kill-switch as the retriever (both are the L2 layer).
    matrix = InProcessCompatibilityMatrix() if settings.ground_enabled else None
    versagensmodi = InProcessVersagensmodiStore() if settings.ground_enabled else None
    partner_registry = _build_partner_registry(settings)
    # sealingAI Memory Architecture V1.0 (Patch 8): only constructed when the flag is on — mirrors
    # the retriever/ground_enabled pattern above, so a disabled feature never pays the Qdrant/DB
    # client construction cost at all, not just at call time.
    memory_context_service: MemoryContextService | None = (
        _build_memory_context_service(settings)
        if settings.memory_context_enabled
        else None
    )

    # M4 deterministic calc layer: the cascade evaluator over the reviewed calc registry.
    engine: CalcEngine | None = (
        CascadeCalcEngine() if settings.compute_enabled else None
    )

    # M5 memory: working window/case-state/history (layers 1-3) + the cross-session seam (L4).
    # Wired always-on (M4a precedent: wired-in → measured) but inert without a session — the eval
    # passes no session, so the single-turn REPLAY stays a true, zero-cost no-op. With
    # ``database_url`` SET the durable SQLAlchemy adapters back the SAME Protocols (build-spec §3:
    # Postgres = system-of-record) so memory survives a restart; UNSET keeps the in-process store so
    # the offline eval/CI stay hermetic (no DB, no key). Pure config swap behind the Protocols.
    memory: ConversationMemory | None = None
    cross_session: CrossSessionMemory | None = None
    distiller: Distiller | None = None
    if settings.memory_enabled:
        if settings.database_url:
            # Lazy import: the offline path never touches SQLAlchemy.
            from sealai_v2.db.conversation_memory import PostgresConversationMemory
            from sealai_v2.db.cross_session_memory import PostgresCrossSessionMemory
            from sealai_v2.db.engine import make_engine, make_sessionmaker

            session_factory = make_sessionmaker(make_engine(settings.database_url))
            memory = PostgresConversationMemory(
                session_factory, window_turns=settings.memory_window_turns
            )
            cross_session = PostgresCrossSessionMemory(session_factory)
        else:
            memory = InProcessConversationMemory(
                window_turns=settings.memory_window_turns
            )
            cross_session = InProcessCrossSessionMemory()
        if settings.distill_enabled:
            distiller = Distiller(
                helper_client,
                DistillPromptAssembler(),
                ModelConfig(
                    model=settings.helper_model, temperature=settings.helper_temperature
                ),
            )

    # G4: owner-reviewed archetype store (Anwendungs-Archetypen) — feeds the understand annotation +
    # the L1 interview. Loaded with understand (it is the understand stage's grounding); file-backed
    # seed, canonical for this hop (a DB adapter is the deferred prod path, like the other stores).
    archetypes = load_archetypes() if settings.understand_enabled else None

    # P3 Wissensstand-Referenz: computed ONCE here from the catalogs this pipeline instance wires,
    # not per turn — the seed versions are load-time-fixed. Prefer the already-loaded in-memory
    # catalog (InProcessRetriever/InProcessCompatibilityMatrix/InProcessVersagensmodiStore all expose
    # ``.catalog``) to avoid a second parse; the Qdrant retriever holds no local FachkartenCatalog, so
    # its fachkarten version is read once via ``load_fachkarten()`` — the git-tracked seed that the
    # served collection was ingested from (not a live Qdrant-content hash; see core/wissensstand.py).
    fachkarten_version = ""
    if isinstance(retriever, InProcessRetriever):
        fachkarten_version = retriever.catalog.version
    elif retriever is not None:
        fachkarten_version = load_fachkarten().version
    wissensstand = compute_wissensstand(
        fachkarten_version=fachkarten_version,
        matrix_version=matrix.catalog.version if matrix is not None else "",
        traps_version=catalog.version if catalog is not None else "",
        versagensmodi_version=(
            versagensmodi.catalog.version if versagensmodi is not None else ""
        ),
    )

    # Phase 2D (LangGraph-suitability audit): construct the compact smalltalk_navigation
    # generator ONLY when the flag is on -- None otherwise, so run()'s
    # `self.smalltalk_generator is not None` check is a genuine no-op when this is unset (the
    # branch in run() is unreachable regardless of route_optimization_enabled/route_decision).
    # Reuses helper_client (the SAME already-wired cheap-tier client used by understand/distill --
    # already carries a telemetry sink when llm_telemetry_enabled is on) and the SAME
    # hash-based-cache-key scheme Phase 1 wired for L1 (build_prompt_cache_key), computed once
    # here from the fully-static template (see prompts/smalltalk_navigation.jinja).
    smalltalk_generator: SmalltalkGenerator | None = None
    if settings.route_prompt_families_enabled:
        _smalltalk_assembler = SmalltalkNavigationPromptAssembler()
        _smalltalk_static_prompt = _smalltalk_assembler.system_prompt()
        smalltalk_generator = SmalltalkGenerator(
            client=helper_client,
            assembler=_smalltalk_assembler,
            model_config=ModelConfig(
                model=settings.helper_model,
                temperature=settings.helper_temperature,
                cache_key=build_prompt_cache_key(
                    "smalltalk_navigation",
                    settings.helper_model,
                    _smalltalk_static_prompt,
                ),
                stage="smalltalk_navigation",
            ),
        )

    return Pipeline(
        generator=generator,
        client=helper_client,  # used by the understand helper stage
        helper_model=helper_cfg,
        understand_prompt_assembler=UnderstandPromptAssembler(),
        understand_enabled=settings.understand_enabled,
        archetypes=archetypes,
        verifier=verifier,
        catalog=catalog,
        retriever=retriever,
        matrix=matrix,
        versagensmodi=versagensmodi,
        partner_registry=partner_registry,
        engine=engine,
        memory=memory,
        cross_session=cross_session,
        distiller=distiller,
        medium_researcher=medium_researcher,
        medium_intel_enabled=settings.medium_intel_enabled,
        memory_context_service=memory_context_service,
        memory_context_enabled=settings.memory_context_enabled,
        produktspec_enabled=settings.produktspec_enabled,
        pack_suggestion_enabled=settings.pack_suggestion_enabled,
        coverage_gate_enabled=settings.coverage_gate_enabled,
        response_contract_enabled=settings.response_contract_enabled,
        response_contract_general_guard_enabled=settings.response_contract_general_guard_enabled,
        baseline_hardening_enabled=settings.baseline_hardening_enabled,
        material_param_table_enabled=settings.material_param_table_enabled,
        wissensstand=wissensstand,
        route_optimization_enabled=settings.route_optimization_enabled,
        route_telemetry_sink=(
            LoggingRouteTelemetrySink() if settings.route_optimization_enabled else None
        ),
        route_prompt_families_enabled=settings.route_prompt_families_enabled,
        smalltalk_generator=smalltalk_generator,
        risk_flag_prompt_enabled=settings.risk_flag_prompt_enabled,
    )
