"""The thin V2 answer pipeline (build-spec §5 / Prinzipien §3).

M1 wires only understand→answer; ground/verify/cite are inert stubs. Tenant scope (P0) is
mandatory and validated at the entry point. No deterministic gate, no routing — the soft
intent annotates but never alters the answer path.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field

from sealai_v2.config.settings import Settings
from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import (
    CalcEngine,
    CalcResult,
    ConversationMemory,
    CrossSessionMemory,
    Flags,
    LlmClient,
    ModelConfig,
    PipelineResult,
    Retriever,
    SessionContext,
    UntrustedContent,
    VerifierVerdict,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.knowledge.traps import TrapCatalog, load_traps
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.timing import TurnTimer
from sealai_v2.prompts.assembler import (
    DistillPromptAssembler,
    PromptAssembler,
    VerifierPromptAssembler,
)
from sealai_v2.security.tenant import TenantContext, require_tenant

_log = logging.getLogger("sealai_v2.pipeline")

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


@contextmanager
def _staged(timer, progress: ProgressSink | None, ms_key: str, stage: str):
    """One seam: progress start → timed body → progress end. On an exception the ``end`` is
    deliberately NOT emitted — the route's `error` frame follows the stage's `start`."""
    _emit_progress(progress, stage, "start")
    with timer.stage(ms_key):
        yield
    _emit_progress(progress, stage, "end")


@dataclass
class Pipeline:
    generator: L1Generator
    client: LlmClient
    helper_model: ModelConfig
    understand_enabled: bool = True
    verifier: L3Verifier | None = None  # None → L3 disabled (incident kill-switch only)
    catalog: TrapCatalog | None = None
    retriever: Retriever | None = (
        None  # None → L2 grounding off → every answer is "vorläufig"
    )
    engine: CalcEngine | None = (
        None  # None → M4 calc layer off → no "Berechnete Werte" block
    )
    # M5 memory: layers 1-3 (window/case-state/history) + the layer-4 cross-session seam +
    # the distiller. All None → memory is fully inert (no recall, no record, no distill call).
    memory: ConversationMemory | None = None
    cross_session: CrossSessionMemory | None = None
    distiller: Distiller | None = None
    # P2: in-flight background remember tasks, keyed by (tenant_id, session_id). Filled only
    # when a distiller is wired; drained by ``flush_memory`` (the ordering guard).
    _pending_remember: dict[tuple[str, str], asyncio.Task] = field(
        default_factory=dict, init=False, repr=False
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
        case_context = [
            {"feld": f.feld, "wert": f.wert} for f in (mem.case_state + mem.durable)
        ]
        conversation_window = [{"role": t.role, "text": t.text} for t in mem.window]

        # P1: soft understand is annotate-only (Intent NEVER gates/routes; it feeds only the
        # API intent field via PipelineResult.understanding) — so it runs CONCURRENT with the
        # answer chain instead of serializing in front of L1. Awaited after the chain; a chain
        # failure cancels it (same failure surface as the serial order, pure reordering).
        understand_task: asyncio.Task | None = None
        if self.understand_enabled:

            async def _understand_timed():
                with _staged(timer, progress, "understand_ms", "understand"):
                    return await stages.understand(
                        self.client, self.helper_model, question
                    )

            understand_task = asyncio.create_task(_understand_timed())

        try:
            with _staged(timer, progress, "ground_ms", "ground"):
                retrieval = await stages.ground(
                    self.retriever, question, tenant_id=scope.tenant_id
                )
            grounding_facts = (
                retrieval.grounding_facts
            )  # reviewed → authoritative + cited
            # M8-A provenance binding: remembered case facts → calc inputs, DETERMINISTIC + DECLARED
            # (owner-confirmed table; fail-closed on ambiguity — never LLM-judged). Explicit caller
            # params (eval fixtures) take precedence per key. Empty everywhere → byte-identical no-op.
            bound = bind_params(mem.case_state + mem.durable)
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
            with _staged(timer, progress, "generate_ms", "generate"):
                answer = await self.generator.generate(
                    question,
                    flags=flags,
                    grounding_facts=grounding_facts,
                    calc=calc,
                    case_context=case_context
                    or None,  # empty → None → byte-identical no-memory prompt
                    conversation_window=conversation_window or None,
                    untrusted=untrusted_data,  # empty → None → byte-identical no-untrusted prompt
                )
            draft = (
                answer  # first-pass L1 draft, captured before L3 may correct/hedge it
            )

            verdict: VerifierVerdict | None = None
            if self.verifier is not None and self.catalog is not None:
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
                        )
        except BaseException:
            if understand_task is not None:
                if understand_task.done():
                    understand_task.exception()  # consume — the chain error is primary
                else:
                    understand_task.cancel()
            raise

        understanding = await understand_task if understand_task is not None else None

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
            grounding_facts=grounding_facts,
            computed_values=calc.computed,
            not_computed=calc.not_computed,
            calc_notes=calc.notes,
        )

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
    settings: Settings, client: LlmClient, *, l1_model: str | None = None
) -> Pipeline:
    """Wire the pipeline from settings + an injected client. The template file reads happen once
    here (assembler construction), keeping the pure generator/verifier I/O-free. L3 is ALWAYS-ON
    (core trust layer, not flag-gated) unless ``verify_enabled`` is turned off (incident only)."""
    assembler = PromptAssembler()
    l1_cfg = ModelConfig(
        model=l1_model or settings.l1_model, temperature=settings.l1_temperature
    )
    helper_cfg = ModelConfig(
        model=settings.helper_model, temperature=settings.helper_temperature
    )
    generator = L1Generator(client, assembler, l1_cfg)

    verifier: L3Verifier | None = None
    catalog: TrapCatalog | None = None
    if settings.verify_enabled:
        catalog = load_traps()
        verifier_cfg = ModelConfig(
            model=settings.verifier_model, temperature=settings.verifier_temperature
        )
        verifier = L3Verifier(client, VerifierPromptAssembler(), verifier_cfg, catalog)

    # L2 grounding: in-process Fachkarten retriever (M3). A Qdrant adapter swaps in here by config
    # (build-spec §3) behind the same Retriever Protocol — no core change.
    retriever: Retriever | None = (
        InProcessRetriever() if settings.ground_enabled else None
    )

    # M4 deterministic calc layer: the cascade evaluator over the reviewed calc registry.
    engine: CalcEngine | None = (
        CascadeCalcEngine() if settings.compute_enabled else None
    )

    # M5 memory: in-process working window/case-state/history + the trivial cross-session seam.
    # Wired always-on (M4a precedent: wired-in → measured) but inert without a session — the eval
    # passes no session, so the single-turn REPLAY stays a true, zero-cost no-op. Redis/Postgres/
    # Qdrant adapters swap in here by config behind the same Protocols (build-spec §3) — deferred.
    memory: ConversationMemory | None = None
    cross_session: CrossSessionMemory | None = None
    distiller: Distiller | None = None
    if settings.memory_enabled:
        memory = InProcessConversationMemory(window_turns=settings.memory_window_turns)
        cross_session = InProcessCrossSessionMemory()
        if settings.distill_enabled:
            distiller = Distiller(
                client,
                DistillPromptAssembler(),
                ModelConfig(
                    model=settings.helper_model, temperature=settings.helper_temperature
                ),
            )

    return Pipeline(
        generator=generator,
        client=client,
        helper_model=helper_cfg,
        understand_enabled=settings.understand_enabled,
        verifier=verifier,
        catalog=catalog,
        retriever=retriever,
        engine=engine,
        memory=memory,
        cross_session=cross_session,
        distiller=distiller,
    )
