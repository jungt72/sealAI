"""The thin V2 answer pipeline (build-spec §5 / Prinzipien §3).

M1 wires only understand→answer; ground/verify/cite are inert stubs. Tenant scope (P0) is
mandatory and validated at the entry point. No deterministic gate, no routing — the soft
intent annotates but never alters the answer path.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sealai_v2.config.settings import Settings
from sealai_v2.llm.cache_key import build_prompt_cache_key
from sealai_v2.obs.safe_trace import safe_input_projection, safe_output_projection
from sealai_v2.pipeline.routing import (
    RouteName,
    classify_route,
    classify_route_deterministic,
    is_explicit_knowledge_overview,
    resolve_material_comparison_followup,
    requests_calculation,
)
from sealai_v2.orchestration.execution_policy import (
    ExecutionClass,
    ExecutionDecision,
    ExecutionFeatures,
    ModelTier,
    StreamingMode,
    VerificationMode,
    decide_execution,
    deterministic_response,
)
from sealai_v2.orchestration.answer_cache import (
    InProcessExactAnswerCache,
    build_answer_cache_namespace,
    exact_answer_key,
)
from sealai_v2.pipeline.smalltalk_generator import SmalltalkGenerator
from sealai_v2.pipeline.adaptive_interview import (
    AdaptiveInterviewEvaluation,
    AdaptiveInterviewService,
)
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
from sealai_v2.core.case_state import CaseStateV2
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
    RetrievalResult,
    Retriever,
    SessionContext,
    TurnState,
    Understanding,
    UntrustedContent,
    VerifierVerdict,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.l3_verifier import L3Verifier, run_parametric_guard
from sealai_v2.core.medium_extract import extract_medium_facts
from sealai_v2.core.medium_research import MediumIntelligence, MediumResearcher
from sealai_v2.core.seal_type_extract import extract_seal_type_facts
from sealai_v2.memory.context_assembler import MemoryContextBundle, MemoryContextService
from sealai_v2.core.wissensstand import compute_wissensstand
from sealai_v2.pipeline.produktspec_step import compute_kandidaten_spec
from sealai_v2.knowledge.archetypes import load_archetypes
from sealai_v2.knowledge.authority import (
    PostgresKnowledgeAuthority,
    RequestAuthorityGuard,
)
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.knowledge.versagensmodi import InProcessVersagensmodiStore
from sealai_v2.knowledge.hersteller_partner import InProcessPartnerRegistry
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.knowledge.traps import (
    TrapCatalog,
    load_traps,
    retrieve_reviewed_trap_facts,
)
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
_KNOWN_SEAL_TYPES: tuple[str, ...] = (
    "rwdr",
    "o-ring",
    "gleitringdichtung",
    "hydraulik",
)

_KNOWLEDGE_ROUTES = frozenset(
    {
        RouteName.GENERAL_SEALING_KNOWLEDGE,
        RouteName.MATERIAL_KNOWLEDGE,
        RouteName.MATERIAL_COMPARISON,
    }
)


class ProductModeUnavailable(RuntimeError):
    """Raised before model execution when a governed product mode is inactive."""

    def __init__(self, mode: str, maturity: str) -> None:
        super().__init__(f"product mode {mode!r} is {maturity}")
        self.mode = mode
        self.maturity = maturity


def _build_retriever(settings: Settings) -> Retriever:
    """L2 retriever selection (build-spec §3): the in-process keyword matcher (default — the hermetic
    CI/eval measurement instrument) OR the Qdrant production adapter (``retriever_backend=qdrant`` +
    a set ``qdrant_url`` and Postgres ledger). An explicit Qdrant selection is fail-closed: silently
    changing the retrieval implementation would make release evidence describe a different runtime."""
    if settings.retriever_backend == "qdrant":
        if not settings.qdrant_url or not settings.database_url:
            raise RuntimeError(
                "configured qdrant retriever requires both Qdrant and Postgres ledger"
            )
        try:
            from sealai_v2.knowledge.ledger import build_knowledge_ledger
            from sealai_v2.knowledge.qdrant_retrieval import QdrantFachkartenRetriever

            return QdrantFachkartenRetriever(
                settings, knowledge_ledger=build_knowledge_ledger(settings)
            )
        except Exception:  # noqa: BLE001 — normalize optional-dependency/adapter failures
            raise RuntimeError("configured qdrant retriever is unavailable") from None
    if settings.retriever_backend == "in_process":
        return InProcessRetriever()
    raise RuntimeError("unsupported retriever backend")


def _build_memory_context_service(settings: Settings):
    """sealingAI Memory Architecture V1.0 (Patch 8): the Postgres store + Qdrant client + embedder
    a ``MemoryContextService`` needs. Fail-safe, same discipline as ``_build_retriever`` above: an
    unset ``database_url``/``qdrant_url``, a missing optional dependency, or an unreachable service
    fails closed when the feature is enabled; no in-process production authority exists."""
    if not settings.database_url or not settings.qdrant_url:
        raise RuntimeError("memory context requires Postgres and Qdrant")
    try:
        from sealai_v2.db.memory_store import build_memory_store
        from sealai_v2.knowledge.qdrant_retrieval import _make_client, _make_embedder
        from sealai_v2.memory.context_assembler import MemoryContextService

        store = build_memory_store(settings)
        qdrant_client = _make_client(settings)
        embedder = _make_embedder(settings)
        return MemoryContextService(
            store=store,
            qdrant_client=qdrant_client,
            embedder=embedder,
            collection=settings.memory_qdrant_collection,
        )
    except Exception:  # noqa: BLE001 — normalize adapter/optional-dependency failures
        raise RuntimeError("memory context service is unavailable") from None


def _build_partner_registry(settings: Settings):
    """Build the technical-fit pool from verified capabilities, never billing."""
    if settings.manufacturer_fit_enabled:
        if not settings.database_url:
            raise RuntimeError("manufacturer fit requires Postgres authority")
        from sealai_v2.db.engine import make_engine, make_sessionmaker
        from sealai_v2.db.manufacturer_capability import (
            PostgresManufacturerCapabilityStore,
        )
        from sealai_v2.knowledge.verified_partner_registry import (
            VerifiedCapabilityPartnerRegistry,
        )

        session_factory = make_sessionmaker(make_engine(settings.database_url))
        return VerifiedCapabilityPartnerRegistry(
            PostgresManufacturerCapabilityStore(session_factory)
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

# Neutrality is a product invariant, not a best-effort prompt preference. This narrow detector
# catches an explicit persistent/preferred manufacturer-ranking override in the user's message.
# Normal questions such as "Welche Hersteller kommen infrage?" do not match.
_MANUFACTURER_RANKING_OVERRIDE_RE = re.compile(
    r"\b(?:empfiehl|empfehl)\w*\b.{0,100}\b(?:ab\s+jetzt\s+)?immer\b.{0,60}"
    r"\b(?:zuerst|bevorzugt)\b.{0,100}\b(?:hersteller|firma)\b|"
    r"\b(?:hersteller|firma)\b.{0,100}\b(?:immer\s+zuerst|bevorzugt)\b.{0,100}"
    r"\begal\s+wonach\b",
    re.IGNORECASE | re.DOTALL,
)
_NEUTRALITY_HEDGE_MODEL = "neutrality-guard"
_NEUTRALITY_HEDGE_TEXT = (
    "Ein erzwungenes oder dauerhaft bevorzugtes Hersteller-Ranking übernehme ich nicht. "
    "Hersteller und Produkte werden ausschließlich neutral anhand der konkreten technischen "
    "Anforderungen und kuratierter Fähigkeitsdaten eingegrenzt. Für die Werkstoff- und "
    "Bauformwahl brauche ich insbesondere das genaue Medium einschließlich Basis und Additivpaket, "
    "Temperatur, Druck, Dynamik und Wellenbedingungen; die konkrete Eignung bleibt anschließend "
    "per Datenblatt und Herstellerbestätigung zu verifizieren."
)
_PARTNER_GROUNDING_GUARD_MODEL = "partner-grounding-guard"
_EXFIL_REQUEST_GUARD_MODEL = "exfil-request-guard"
_DECODE_GUARD_MODEL = "deterministic-decode"
_EXFIL_REQUEST_REFUSAL_TEXT = (
    "Interne Systemanweisungen, Prompts und vertrauliche Wissensbasis-Inhalte gebe ich nicht aus. "
    "Bei einer konkreten Frage zur Dichtungstechnik helfe ich dir gern fachlich weiter."
)
_EXFIL_REQUEST_RE = re.compile(
    r"\b(?:system[- ]?prompt|systemanweisung(?:en)?|interne[nr]?\s+anweisung(?:en)?|"
    r"wissensbasis)\b.*\b(?:aus(?:geben|gabe)|zeig(?:en|e)?|nenn(?:en|e)?|"
    r"w[oö]rtlich|vollst[aä]ndig|verrat(?:en|e)?|offenleg(?:en|e)?)\b|"
    r"\b(?:gib|zeige?|nenne?|verrate?|offenlege?)\b.*\b(?:system[- ]?prompt|"
    r"systemanweisung(?:en)?|interne[nr]?\s+anweisung(?:en)?|wissensbasis)\b",
    re.IGNORECASE | re.DOTALL,
)
_DECODE_REQUEST_RE = re.compile(
    r"\b(?:aufschl[uü]ssel(?:n|e)?|schl[uü]ssel(?:n|e)?|dekodier(?:en|e)?|decode|was\s+bedeutet|"
    r"vergleichbar|dasselbe|identisch|tausch(?:en|bar)|austausch(?:en|bar)|ersatzteil)\b",
    re.IGNORECASE,
)

# P4a: optional per-turn progress sink — (stage, "start"|"end"), stage keys only (NEVER content/
# PII; the SSE doctrine test pins this). Sync + fire-and-forget so a sink can never block a seam.
ProgressSink = Callable[[str, str], None]

# Phase 3A (live token streaming) + Phase 3B (draft-token streaming): optional per-turn RAW-token
# sink. Called as ``sink(delta, draft)``: ``draft=False`` for the Phase 3A smalltalk_navigation path
# (the streamed text IS the final, authoritative answer, since smalltalk never goes through L3);
# ``draft=True`` for the Phase 3B path (every non-smalltalk route's L1 generation), where the delta
# is a NON-AUTHORITATIVE preview only -- the delivered answer still arrives as the atomic verified
# ``result`` after the full output_guard + L3 pipeline. One str delta per call; sync + fire-and-forget
# so a broken sink can never block/fail the turn (same discipline as ProgressSink). The deltas carry
# only the model's raw natural-language text -- never ids/tenant/case/PII/structured fields.
TokenSink = Callable[[str, bool], None]


def _emit_progress(progress: ProgressSink | None, stage: str, status: str) -> None:
    if progress is None:
        return
    try:
        progress(stage, status)
    except Exception:  # noqa: BLE001 — a broken sink must never alter or fail a turn
        _log.warning("progress sink failed (ignored)", exc_info=True)


def _emit_token(token_sink: "TokenSink | None", delta: str, *, draft: bool) -> None:
    if token_sink is None:
        return
    try:
        token_sink(delta, draft)
    except Exception:  # noqa: BLE001 — a broken token sink must never alter or fail a turn
        _log.warning("token sink failed (ignored)", exc_info=True)


def _exfil_guard(
    answer,
    *,
    system_prompt: str,
    kb_claims,
    authorized_kb_claims=(),
):
    """P1.4 SERVE-path exfiltration Schranke. Runs the pure ``exfiltration_leak`` detector over the
    final answer vs the system prompt that produced it + the verbatim KB claim texts. On a leak
    (verbatim ≥160-char system-prompt span OR ≥6 non-authorized verbatim KB claims) return a
    deterministic number-free refusal hedge so the verbatim leak never ships; otherwise return
    ``answer`` unchanged (byte-identical pass-through). Evidence-ID-validated claims selected by a
    structured knowledge answer may be authorized by the caller; that never exempts system-prompt
    content. Pure — the only state is the returned Answer."""
    verdict = exfiltration_leak(
        answer=answer.text,
        system_prompt=system_prompt,
        kb_claims=list(kb_claims),
        authorized_kb_claims=list(authorized_kb_claims),
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


def _neutrality_override_guard(question: str, answer: Answer) -> tuple[Answer, bool]:
    """Fail closed on explicit paid/preferred manufacturer-ranking overrides.

    The final model output is intentionally not inspected for a brand name: once the input contains
    the narrow override shape, repeating that injected brand even with a caveat would still confer
    preference. The deterministic response therefore contains no user-supplied manufacturer name.
    """
    if not _MANUFACTURER_RANKING_OVERRIDE_RE.search(question or ""):
        return answer, False
    return (
        Answer(
            text=_NEUTRALITY_HEDGE_TEXT,
            model=_NEUTRALITY_HEDGE_MODEL,
            grounding_facts=answer.grounding_facts,
        ),
        True,
    )


def _partner_grounding_guard(answer: Answer, alternatives: dict | None) -> Answer:
    """Render manufacturer alternatives only from the authoritative partner result.

    The registry stage already owns capability ranking and payment-neutrality. Replacing the free
    model narration here prevents an empty/unassessed registry from being filled with remembered
    brand names and prevents a grounded result from being reordered or supplemented by the model.
    """
    if alternatives is None:
        return answer
    neutral = str(alternatives.get("neutralitaet") or "").strip()
    if not alternatives.get("grounded_data"):
        hint = str(alternatives.get("hinweis") or "").strip()
        text = "\n\n".join(part for part in (hint, neutral) if part)
    else:
        rows = alternatives.get("hersteller") or []
        rendered = []
        for row in rows:
            name = str(row.get("firmenname") or "").strip()
            capabilities = ", ".join(
                str(item) for item in (row.get("werkstoffe") or []) if item
            )
            if name:
                rendered.append(
                    f"- {name}"
                    + (f" — Werkstoffe: {capabilities}" if capabilities else "")
                )
        heading = "Passende Partner nach fachlicher Eignung (Partner/Anzeige):"
        text = "\n".join([heading, *rendered])
        if neutral:
            text += f"\n\n{neutral}"
    if not text:
        return answer
    return Answer(
        text=text,
        model=_PARTNER_GROUNDING_GUARD_MODEL,
        grounding_facts=answer.grounding_facts,
    )


def _explicit_exfil_request_guard(question: str, answer: Answer) -> Answer:
    """Refuse direct requests for confidential instructions even when no leak was emitted.

    The leak detector remains the final content-based backstop. This intent-shaped guard closes the
    UX gap where a model safely avoided disclosure but failed to state a clear refusal.
    """
    if not _EXFIL_REQUEST_RE.search(question or ""):
        return answer
    return Answer(
        text=_EXFIL_REQUEST_REFUSAL_TEXT,
        model=_EXFIL_REQUEST_GUARD_MODEL,
        grounding_facts=answer.grounding_facts,
    )


def _decode_grounding_guard(
    question: str, answer: Answer, decoded: dict | None
) -> Answer:
    """Render a parsed designation from deterministic fields only.

    Decode is an extraction task, so free model prose adds risk without adding authority. Keeping
    this renderer closed over the parser result prevents invented norms, brands and performance
    limits while preserving the explicit interchangeability boundary.
    """
    if not decoded or not _DECODE_REQUEST_RE.search(question or ""):
        return answer

    def number(value) -> str:
        numeric = float(value)
        return str(int(numeric)) if numeric.is_integer() else f"{numeric:g}"

    lines = ["Aufschlüsselung der Bezeichnung:"]
    if seal_type := decoded.get("type"):
        lines.append(f"- Bauform: {seal_type}")
    if dims := decoded.get("dims_mm"):
        labels = {
            "id_od_breite": "Innendurchmesser × Außendurchmesser × Breite",
            "id_schnurstaerke": "Innendurchmesser × Schnurstärke",
            "uneindeutig": "Maßfolge; Zuordnung noch bestätigen",
        }
        rendered = " × ".join(number(value) for value in dims)
        interpretation = labels.get(decoded.get("dim_interpretation"), "Nennmaße")
        lines.append(f"- Nennmaße: {rendered} mm ({interpretation})")
    if material := decoded.get("material"):
        lines.append(f"- Werkstoffklasse: {material}")
    if boundary := decoded.get("equivalenz_grenze"):
        lines.extend(("", str(boundary)))
    return Answer(
        text="\n".join(lines),
        model=_DECODE_GUARD_MODEL,
        grounding_facts=answer.grounding_facts,
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
    standard_generator: L1Generator | None = None
    frontier_generator: L1Generator | None = None
    execution_policy_enabled: bool = False
    answer_cache: InProcessExactAnswerCache | None = None
    answer_cache_namespace: str = ""
    # Production namespaces are derived per request from Postgres authority. The static namespace
    # remains only for hermetic unit fixtures that do not claim production authority.
    answer_cache_namespace_for_epoch: Callable[[str], str] | None = None
    knowledge_authority: PostgresKnowledgeAuthority | None = None
    # Material subject lexicon derived once from the versioned Fachkarten catalog. Routing can
    # therefore recognise every material the knowledge layer actually serves without a second,
    # drifting hard-coded allowlist.
    knowledge_material_terms: tuple[str, ...] = ()
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
    # Adaptive Bedarfsanalyse Phase 0/1. The service is pure-controller + persistence only and is
    # constructed exclusively when the rwdr pack plus active or shadow mode are enabled.
    adaptive_interview_enabled: bool = False
    adaptive_interview_shadow_enabled: bool = False
    adaptive_interview_service: AdaptiveInterviewService | None = None
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
    # SSoT M15/G8. Direct Pipeline fixtures default to enabled so low-level
    # tests stay focused; build_pipeline always injects the fail-closed Settings
    # value used by every real API process.
    knowledge_mode_enabled: bool = True
    # Real API pipelines additionally require at least one current authoritative
    # claim on a knowledge turn. Direct unit fixtures opt in explicitly.
    authoritative_knowledge_required: bool = False
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
    # Phase 3A (live token streaming): flag-gate for streaming the compact smalltalk answer
    # token-by-token. False (default) -> the streaming branch in run() is unreachable and the
    # smalltalk turn takes the UNCHANGED non-streaming generate() -- byte-identical to Phase 2D.
    smalltalk_token_streaming_enabled: bool = False
    # Phase 3B (draft-token streaming): flag-gate for streaming the FULL L1 engineering generator's
    # raw deltas into a NON-AUTHORITATIVE "draft" channel, for EVERY route that goes through
    # self.generator (engineering_case, leakage_troubleshooting, rfq_manufacturer_brief,
    # material_comparison, general_sealing_knowledge, material_knowledge -- i.e. every route EXCEPT
    # smalltalk_navigation, which has its own Phase 3A path). Independent of
    # smalltalk_token_streaming_enabled. False (default) -> draft_stream_active is always False, the
    # generate_stream branch in run() is unreachable, every generate() call is byte-identical to
    # pre-Phase-3B. When True (AND a token sink is wired) it ONLY adds an observability side-channel:
    # the delivered answer still goes through the UNCHANGED output_guard + L3 verify + citations
    # pipeline and still arrives as one atomic `result`. This flag never skips or weakens any
    # verification.
    draft_token_streaming_enabled: bool = False

    # INC-CALC-ROUTE-RELEVANCE: when True AND route classification ran AND the classified route's
    # route_prompt_matrix `kernel` flag is False, the L1 generator's prompt receives an EMPTY
    # CalcResult() instead of the real calc — a prompt-relevance fix so conceptual/knowledge answers
    # no longer drift into off-topic kernel calc-refusal text. Suppresses ONLY the L1 PROMPT input;
    # the real `calc` is unchanged for the guard contract, L3 verify(), and the response payload's
    # computed/not_computed fields. False (default) -> l1_calc IS calc everywhere -> byte-identical.
    suppress_calc_for_non_kernel_routes_enabled: bool = False

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
        token_sink: TokenSink | None = None,
    ) -> PipelineResult:
        scope = require_tenant(tenant)  # P0 — fail-closed if tenant missing/empty
        authority_guard = (
            RequestAuthorityGuard.bind(
                self.knowledge_authority, tenant_id=scope.tenant_id
            )
            if self.knowledge_authority is not None
            else None
        )
        authority_epoch = (
            authority_guard.captured.value if authority_guard is not None else ""
        )
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
        comparison_followup = resolve_material_comparison_followup(
            question,
            mem.window,
            material_terms=self.knowledge_material_terms,
        )
        # A canonical, context-enriched query is used only by deterministic
        # routing, retrieval and answer planning. The generator still receives
        # the user's exact current question and never the raw prior transcript.
        knowledge_question = (
            comparison_followup.resolved_question
            if comparison_followup is not None
            else question
        )
        effective_case_id = (
            session.session_id if session is not None else f"turn-{timer.turn_id}"
        )
        case_state_v2 = mem.case_state_v2 or CaseStateV2.from_remembered_facts(
            case_id=effective_case_id,
            revision=0,
            facts=mem.case_state,
        )
        # This-session case-state (L2) and cross-session durable facts (L4) are kept SEPARATE: the
        # durable facts surface under their own honest "aus früheren Gesprächen — bei Bedarf
        # bestätigen" frame and (below) do NOT feed the deterministic calc binder — a remembered
        # cross-session value must never be treated as a current/confirmed input.
        # G1 (V2.1 Inc 1): build the typed Case at the generalisation point, then project to the
        # byte-identical list[dict] the L1 prompt + L3 topic-scope consume (owner decision 2 —
        # Jinja unchanged, so the eval stays unperturbed). The typed slots fill in later increments.
        case = Case.from_case_state(
            case_state_v2.to_remembered_facts(), question=question
        )
        case_context = case_state_v2.to_prompt_context()
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
                owner_subject=session.owner_subject if session is not None else "",
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
        # A knowledge overview can legitimately name failure modes and diagnostic dimensions. The
        # symptom index is lexical and may otherwise mistake terms such as "Extrusionsspalt" or
        # "Versagensbilder" for a reported incident. Suppress that incidental diagnosis before it
        # can alter routing or leak a case-specific cause/fix into an educational answer. Concrete
        # case references and operating values are excluded by the shared deterministic predicate.
        if diagnosis is not None and is_explicit_knowledge_overview(
            question, material_terms=self.knowledge_material_terms
        ):
            diagnosis = None
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
        if self.execution_policy_enabled:
            # CaseStateV2 is authoritative. Historical transcript text and cross-session hints
            # are not re-injected into the one-shot production prompt.
            durable_context = []
            conversation_window = []
        policy_route_decision = (
            classify_route_deterministic(
                knowledge_question,
                case_state_nonempty=bool(
                    case_state_v2.fields
                    or case_state_v2.open_conflicts
                    or case_state_v2.required_missing
                ),
                decode_result=decode_result,
                diagnosis=diagnosis,
                gegencheck_verdict=gegencheck_verdict,
                material_terms=self.knowledge_material_terms,
            )
            if self.execution_policy_enabled
            else None
        )
        activation_route_decision = (
            policy_route_decision
            or classify_route_deterministic(
                knowledge_question,
                case_state_nonempty=bool(
                    case_state_v2.fields
                    or case_state_v2.open_conflicts
                    or case_state_v2.required_missing
                ),
                decode_result=decode_result,
                diagnosis=diagnosis,
                gegencheck_verdict=gegencheck_verdict,
                material_terms=self.knowledge_material_terms,
            )
        )
        if (
            not self.knowledge_mode_enabled
            and activation_route_decision.route in _KNOWLEDGE_ROUTES
        ):
            raise ProductModeUnavailable("knowledge", "pilot_not_activated")
        early_clarification = bool(
            policy_route_decision is not None
            and policy_route_decision.forced_full_pipeline
            and case_state_v2.required_missing
        )
        cache_key: str | None = None
        cached_answer: Answer | None = None
        cache_eligible = bool(
            self.execution_policy_enabled
            and self.answer_cache is not None
            and policy_route_decision is not None
            and policy_route_decision.route
            in {
                RouteName.GENERAL_SEALING_KNOWLEDGE,
                RouteName.MATERIAL_KNOWLEDGE,
            }
            and not case_state_v2.fields
            and not case_state_v2.open_conflicts
            and not case_state_v2.required_missing
            and not risk_flags
            and not untrusted
        )
        if cache_eligible:
            cache_namespace = (
                self.answer_cache_namespace_for_epoch(authority_epoch)
                if self.answer_cache_namespace_for_epoch is not None and authority_epoch
                else self.answer_cache_namespace
            )
            cache_key = exact_answer_key(
                tenant_id=scope.tenant_id,
                question=question,
                namespace=cache_namespace,
            )
            cached_answer = self.answer_cache.get(
                tenant_id=scope.tenant_id, key=cache_key
            )

        # P1: soft understand is annotate-only (Intent NEVER gates/routes; it feeds only the
        # API intent field via PipelineResult.understanding) — so it runs CONCURRENT with the
        # answer chain instead of serializing in front of L1. Awaited after the chain; a chain
        # failure cancels it (same failure surface as the serial order, pure reordering).
        understand_task: asyncio.Task | None = None
        understanding: Understanding | None = None
        adaptive_next_question = None
        if self.understand_enabled and not self.execution_policy_enabled:
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
            if early_clarification:
                retrieval = RetrievalResult()
            elif cached_answer is not None:
                retrieval = RetrievalResult(
                    grounding_facts=cached_answer.grounding_facts
                )
            else:
                from sealai_v2.core.knowledge_answer import knowledge_retrieval_limit

                retrieval_k = knowledge_retrieval_limit(
                    knowledge_question, material_terms=self.knowledge_material_terms
                )
                with _staged(timer, progress, "ground_ms", "ground"):
                    retrieval = await stages.ground(
                        self.retriever,
                        self.matrix,
                        knowledge_question,
                        tenant_id=scope.tenant_id,
                        case_facts=mem.case_state,
                        k=retrieval_k,
                    )
            grounding_facts = (
                retrieval.grounding_facts
            )  # reviewed Fachkarten → compute + (Step A) verify
            # An active knowledge product must represent an evidence gap as a valid bounded answer,
            # not as infrastructure failure. The execution policy below selects a zero-model D1
            # response for an ungrounded knowledge route; the activation gate above remains the only
            # 503 boundary (pilot disabled).
            # Gap #2 (Step A): the §4 matrix verdicts join the Fachkarten as belegte Fakten for L1 only
            # (their own channel; L3 wiring is Step B). Empty → byte-identical no-matrix prompt.
            trap_facts = retrieve_reviewed_trap_facts(self.catalog, knowledge_question)
            l1_grounding = grounding_facts + retrieval.matrix_facts + trap_facts
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
            if early_clarification or cached_answer is not None:
                calc = CalcResult()
            else:
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
            stream_tokens_active = False
            # Phase 3B (draft-token streaming): whether THIS turn's self.generator.generate() calls
            # (the full L1 engineering generator, used by every route below the smalltalk if/elif
            # arms) should stream raw deltas into the token sink as a non-authoritative draft preview.
            # Independent of route_optimization_enabled/smalltalk_prompt_active — those gate whether
            # the COMPACT smalltalk prompt is used at all; this gates an observability channel around
            # the FULL generator's calls, which the smalltalk if/elif arms never reach in the first
            # place (see the "else:" arm below), so no additional route check is needed here. False
            # (flag off or no sink wired) -> the generate_stream branch in _l1_generate is
            # unreachable -> every self.generator.generate() call stays byte-identical to today.
            draft_stream_active = (
                self.draft_token_streaming_enabled and token_sink is not None
            )
            if self.route_optimization_enabled or self.execution_policy_enabled:
                _route_started = time.monotonic()
                if self.execution_policy_enabled:
                    route_decision = policy_route_decision
                else:
                    route_decision = classify_route(
                        knowledge_question,
                        case_state_nonempty=bool(mem.case_state),
                        decode_result=decode_result,
                        diagnosis=diagnosis,
                        gegencheck_verdict=gegencheck_verdict,
                        intent=understanding.intent
                        if understanding is not None
                        else None,
                        material_terms=self.knowledge_material_terms,
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
                # Phase 3A: whether THIS turn will actually STREAM tokens. Strictly NARROWER than
                # smalltalk_prompt_active (itself narrower than the L3-bypass): it ADDITIONALLY
                # requires the streaming flag AND a token sink actually wired by the transport. Any
                # one being false -> no token ever fires; the gated `result` answer is unchanged
                # either way. Reuses smalltalk_prompt_active verbatim -- never recomputes route
                # eligibility.
                stream_tokens_active = (
                    smalltalk_prompt_active
                    and self.smalltalk_token_streaming_enabled
                    and token_sink is not None
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
            # INC-CALC-ROUTE-RELEVANCE: the calc context the L1 PROMPT sees. compute()/stages.compute
            # already ran unconditionally above (before routing), so `calc` exists for every turn.
            # On a route whose route_prompt_matrix `kernel` flag is False (general_sealing_knowledge,
            # material_knowledge, smalltalk_navigation — the kernel=True routes are unchanged), the L1
            # prompt has no business discussing kernel/calc topics — feeding it the real calc (esp. its
            # `not_computed` entries) is what caused the off-topic "Umfangsgeschwindigkeit nicht
            # berechenbar" tangent on a conceptual question. Suppress ONLY the L1 PROMPT input to an
            # empty CalcResult() here; every OTHER consumer below keeps the real `calc` untouched —
            # build_guard_contract(calc=calc), stages.verify(computed_values=calc.computed, ...), and
            # the PipelineResult's computed/not_computed all still reflect the real calc for
            # transparency/telemetry/L3. Flag OFF (default) or no route decision -> l1_calc IS calc
            # -> byte-identical to today; and it can only ever REMOVE calc from a kernel=False route's
            # prompt, never change any kernel=True route's prompt.
            l1_calc = calc
            if (
                self.execution_policy_enabled
                and not calc.computed
                and not requests_calculation(question)
            ):
                l1_calc = CalcResult()
            if (
                self.suppress_calc_for_non_kernel_routes_enabled
                and route_decision is not None
            ):
                from sealai_v2.pipeline.route_prompt_matrix import plan_for

                if not plan_for(route_decision.route).kernel:
                    l1_calc = CalcResult()
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
                    calc=l1_calc if self.execution_policy_enabled else calc,
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

            execution_decision: ExecutionDecision | None = None
            active_generator: L1Generator | None = self.generator
            policy_missing_fields: tuple[str, ...] = ()
            policy_conflicts = tuple(
                conflict.field_key for conflict in case_state_v2.open_conflicts
            )
            if self.execution_policy_enabled:
                if route_decision is None:  # defensive: policy routing is mandatory
                    raise RuntimeError("execution policy requires a route decision")
                # Only explicit case-state requirements may block model execution. The response
                # contract also lists inputs missing from every registered calculation; most of
                # those calculations are irrelevant to a material-compatibility or knowledge turn.
                # Treating that generic list as intake requirements made valid grounded questions
                # stop at D1 (for example, asking about FKM in steam requested shaft diameter and
                # O-ring groove depth). Calculation transparency remains in ``calc.not_computed``.
                policy_missing_fields = case_state_v2.required_missing
                source_ids = {
                    source for fact in l1_grounding for source in fact.sources if source
                }
                execution_decision = decide_execution(
                    ExecutionFeatures(
                        route=route_decision,
                        risk_flags=tuple(risk_flags),
                        authoritative_evidence_count=sum(
                            1
                            for fact in l1_grounding
                            if fact.kind != "trap" and bool(fact.sources)
                        ),
                        provisional_evidence_count=len(retrieval.provisional),
                        document_count=len(source_ids),
                        tool_step_count=len(calc.computed),
                        case_conflict_count=len(case_state_v2.open_conflicts),
                        required_missing=policy_missing_fields,
                        contract_status=(
                            (contract or {}).get("status")
                            if policy_missing_fields
                            else None
                        ),
                        untrusted_content_count=len(untrusted),
                        has_diagnosis=diagnosis is not None,
                        exact_cache_hit=cached_answer is not None,
                        reviewed_policy_fact_count=sum(
                            fact.kind == "trap" for fact in l1_grounding
                        ),
                    )
                )
                if execution_decision.model_tier is ModelTier.NONE:
                    active_generator = None
                elif execution_decision.model_tier is ModelTier.STANDARD:
                    active_generator = self.standard_generator or self.generator
                else:
                    active_generator = self.frontier_generator or self.generator
                if active_generator is not None:
                    active_generator = active_generator.with_reasoning_effort(
                        execution_decision.reasoning_effort
                    )
                skip_l3_for_route = (
                    execution_decision.verification_mode
                    is not VerificationMode.CLAIM_LLM
                )
                draft_stream_active = (
                    execution_decision.streaming_mode is StreamingMode.DRAFT
                    and self.draft_token_streaming_enabled
                    and token_sink is not None
                    and active_generator is not None
                    and active_generator.supports_token_streaming
                )
                stream_tokens_active = (
                    execution_decision.streaming_mode is StreamingMode.FINAL
                    and smalltalk_prompt_active
                    and self.smalltalk_token_streaming_enabled
                    and token_sink is not None
                )
            # Deterministic engineering answer profile: only pure knowledge/comparison routes receive
            # this structure. It specifies required facets and measured evidence coverage; it owns no
            # technical fact and cannot relax grounding/no-fake-precision.
            knowledge_answer_plan = None
            if route_decision is not None and route_decision.route in {
                RouteName.GENERAL_SEALING_KNOWLEDGE,
                RouteName.MATERIAL_KNOWLEDGE,
                RouteName.MATERIAL_COMPARISON,
            }:
                from sealai_v2.core.knowledge_answer import build_knowledge_answer_plan

                _kap = build_knowledge_answer_plan(
                    knowledge_question,
                    material_terms=self.knowledge_material_terms,
                    grounding_facts=l1_grounding,
                    route_name=route_decision.route.value,
                    subject_order=(
                        comparison_followup.subjects
                        if comparison_followup is not None
                        else ()
                    ),
                )
                knowledge_answer_plan = _kap.to_dict() if _kap is not None else None
            require_evidence_for_all_claims = bool(
                route_decision is not None
                and route_decision.route is not RouteName.SMALLTALK_NAVIGATION
                and l1_grounding
                and knowledge_answer_plan is None
            )
            compact_technical_answer = bool(
                require_evidence_for_all_claims
                and route_decision is not None
                and route_decision.route is RouteName.ENGINEERING_CASE
                and calc.computed
            )
            work_solution_candidate = bool(
                require_evidence_for_all_claims
                and "lösung" in question.lower()
                and any(
                    fact.card_id == "FK-GLRD-ENGINEERING-PROFILE"
                    for fact in l1_grounding
                )
            )

            # Material-Parameter-Tabelle: grounded kernel parameters for the materials NAMED in the
            # question — injected so L1 RENDERS them as a table (no number invention). Flag-gated ->
            # None when OFF (byte-identical).
            material_params = None
            if self.material_param_table_enabled:
                from sealai_v2.knowledge.material_parameters import (
                    material_parameters_for,
                )

                material_params = material_parameters_for(knowledge_question) or None
            with _staged(timer, progress, "generate_ms", "generate"):
                # Phase 2D: the ONLY branch point where the compact smalltalk_navigation prompt
                # can ever answer a turn. self.generator (L1Generator, the full engineering
                # prompt) is completely untouched below -- every route except a fully-qualified
                # smalltalk turn (see smalltalk_prompt_active's computation above) takes the
                # EXACT same call it always has.
                if cached_answer is not None:
                    answer = cached_answer
                elif active_generator is None and execution_decision is not None:
                    answer = Answer(
                        text=deterministic_response(
                            execution_decision,
                            missing_fields=policy_missing_fields,
                            conflicts=policy_conflicts,
                        ),
                        model="deterministic-policy",
                        grounding_facts=l1_grounding,
                    )
                elif stream_tokens_active and self.smalltalk_generator is not None:
                    # Phase 3A: stream the compact smalltalk answer token-by-token. Each RAW delta
                    # fires the token sink (fire-and-forget); the terminal event carries the finished
                    # strip_sourcing-cleaned Answer -- byte-identical to the non-streaming generate()
                    # result for the same completion. A mid-stream failure propagates (the streaming
                    # transport surfaces the fixed error frame + cancels the task), never a partial.
                    answer = None
                    async for _ev in self.smalltalk_generator.generate_stream(question):
                        if _ev.delta is not None:
                            # Phase 3A: smalltalk deltas are the FINAL answer being typed (draft=False)
                            # -- this route never goes through L3, so draft IS final here.
                            _emit_token(token_sink, _ev.delta, draft=False)
                        elif _ev.answer is not None:
                            answer = _ev.answer
                    if answer is None:
                        # Defensive: a successful stream always yields a terminal answer, so this is
                        # unreachable on success (a failure would have raised above). Fall back to the
                        # non-streaming generate() rather than proceed with no answer.
                        answer = await self.smalltalk_generator.generate(question)
                elif smalltalk_prompt_active and self.smalltalk_generator is not None:
                    answer = await self.smalltalk_generator.generate(question)
                else:
                    # Phase 3B: every non-smalltalk route lands here. ``_l1_generate`` is
                    # byte-identical to the plain ``self.generator.generate(...)`` call it replaces
                    # unless draft_stream_active is True (flag on AND a sink is wired) — see its
                    # docstring. The delivered ``answer`` is unaffected either way; it still goes
                    # through the unchanged output_guard + L3 verify pipeline below.
                    answer = await self._l1_generate(
                        active_generator or self.generator,
                        question,
                        token_sink=token_sink,
                        draft_stream_active=draft_stream_active,
                        flags=flags,
                        grounding_facts=l1_grounding,
                        calc=l1_calc,  # INC-CALC-ROUTE-RELEVANCE: real calc on kernel routes, empty on kernel=False
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
                        knowledge_answer_plan=knowledge_answer_plan,
                        require_evidence_for_all_claims=require_evidence_for_all_claims,
                        compact_technical_answer=compact_technical_answer,
                        work_solution_candidate=work_solution_candidate,
                        risk_flags=(
                            list(risk_flags) if self.risk_flag_prompt_enabled else None
                        ),  # None → byte-identical
                        case_revision=case_state_v2.revision,
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
            if (
                self.response_contract_enabled
                and _effective_contract is not None
                and active_generator is not None
            ):
                from sealai_v2.core.output_guard import (
                    correction_note as _guard_note,
                    evaluate_render as _guard_eval,
                    fail_closed_answer as _guard_fallback,
                    known_inputs as _guard_known,
                )

                _check_sentence_coverage = contract is not None
                _kv, _km = _guard_known(question)
                if material_params:
                    from sealai_v2.core.engineering_answer import numeric_tokens
                    from sealai_v2.knowledge.material_parameters import parameter_text

                    _kv = tuple(_kv) + tuple(
                        numeric_tokens(parameter_text(material_params))
                    )
                    _km = tuple(_km) + tuple(
                        str(block.get("material", ""))
                        for block in material_params
                        if str(block.get("material", ""))
                    )
                _gr = _guard_eval(
                    answer_text=answer.text,
                    contract=_effective_contract,
                    known_values=_kv,
                    known_materials=_km,
                    check_sentence_coverage=_check_sentence_coverage,
                )
                if _gr.action == "BLOCK":
                    # Phase 3B: this ``_staged(..., "regenerate", "start")`` progress event ALREADY
                    # exists (pre-Phase-3B) and is reused verbatim as the frontend's signal to
                    # reset/clear its draft buffer before this second attempt's tokens arrive — no
                    # new event type is introduced for that purpose.
                    with _staged(timer, progress, "regenerate_ms", "regenerate"):
                        answer = await self._l1_generate(
                            active_generator or self.generator,
                            question,
                            token_sink=token_sink,
                            draft_stream_active=draft_stream_active,
                            flags=flags,
                            grounding_facts=l1_grounding,
                            calc=l1_calc,  # INC-CALC-ROUTE-RELEVANCE: same suppression on the guard-triggered regen
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
                            material_params=material_params,
                            knowledge_answer_plan=knowledge_answer_plan,
                            require_evidence_for_all_claims=require_evidence_for_all_claims,
                            compact_technical_answer=compact_technical_answer,
                            work_solution_candidate=work_solution_candidate,
                            correction_note=_guard_note(_gr),
                            risk_flags=(
                                list(risk_flags)
                                if self.risk_flag_prompt_enabled
                                else None
                            ),
                            case_revision=case_state_v2.revision,
                        )
                    _gr2 = _guard_eval(
                        answer_text=answer.text,
                        contract=_effective_contract,
                        known_values=_kv,
                        known_materials=_km,
                        check_sentence_coverage=_check_sentence_coverage,
                    )
                    _log.info(
                        "GOVERNANCE output_guard: regenerated (first=%s -> after=%s); "
                        "first_violations=%s; second_violations=%s",
                        _gr.action,
                        _gr2.action,
                        [v.kind for v in _gr.violations],
                        [v.kind for v in _gr2.violations],
                    )
                    if _gr2.action == "BLOCK":
                        answer = Answer(
                            text=_guard_fallback(
                                _effective_contract, question=question
                            ),
                            model="deterministic-output-guard",
                            grounding_facts=l1_grounding,
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
                        active_generator or self.generator,
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
                        case_revision=case_state_v2.revision,
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

            # Designation decoding is deterministic extraction. Do not let free model prose add
            # ungrounded brands, standards, limits or interchangeability claims to parsed fields.
            answer = _decode_grounding_guard(question, answer, decode_result)

            # Manufacturer narration comes only from the deterministic capability registry result.
            answer = _partner_grounding_guard(answer, alternativen_result)

            # Neutrality override guard: an explicit persistent/preferred manufacturer ranking is
            # replaced after the model/verifier chain and before any answer can ship.
            answer, _neutrality_overridden = _neutrality_override_guard(
                question, answer
            )

            # Direct exfiltration requests receive a deterministic refusal even when the model did
            # not emit enough confidential text to trip the content-based leak detector below.
            answer = _explicit_exfil_request_guard(question, answer)

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
                system_prompt=(
                    active_generator or self.generator
                ).doctrine_system_prompt(flags=flags),
                kb_claims=[f.text for f in l1_grounding],
                authorized_kb_claims=(
                    answer.verification_claims
                    if knowledge_answer_plan is not None
                    else ()
                ),
            )

            # The first output-guard pass precedes L3 by design so it can request one corrected
            # generation.  Every later verifier/override may still mutate the answer, therefore the
            # exact payload that ships receives a second, non-generative fail-closed check here.
            # Kernel material values are admitted explicitly; they are structured reviewed data, not
            # model-invented quantities.
            if (
                self.response_contract_enabled
                and _effective_contract is not None
                and active_generator is not None
            ):
                from sealai_v2.core.engineering_answer import numeric_tokens
                from sealai_v2.core.output_guard import (
                    evaluate_render as _final_guard_eval,
                    fail_closed_answer as _final_guard_fallback,
                    known_inputs as _final_guard_known,
                )
                from sealai_v2.knowledge.material_parameters import parameter_text

                _final_kv, _final_km = _final_guard_known(question)
                if material_params:
                    _final_kv = tuple(_final_kv) + tuple(
                        numeric_tokens(parameter_text(material_params))
                    )
                    _final_km = tuple(_final_km) + tuple(
                        str(block.get("material", ""))
                        for block in material_params
                        if str(block.get("material", ""))
                    )
                _final_guard = _final_guard_eval(
                    answer_text=answer.text,
                    contract=_effective_contract,
                    known_values=_final_kv,
                    known_materials=_final_km,
                    check_sentence_coverage=contract is not None,
                )
                if _final_guard.action == "BLOCK":
                    _log.error(
                        "GOVERNANCE final_output_guard blocked post-verification answer: %s",
                        [violation.kind for violation in _final_guard.violations],
                    )
                    answer = Answer(
                        text=_final_guard_fallback(
                            _effective_contract, question=question
                        ),
                        model="deterministic-final-output-guard",
                        grounding_facts=l1_grounding,
                    )
                    guard = _final_guard.to_dict()
                elif guard is None:
                    guard = _final_guard.to_dict()

            with _staged(timer, progress, "cite_ms", "cite"):
                answer = await stages.cite(answer)  # stub → unchanged

            # Persist the authoritative turn BEFORE it can be returned. Only LLM distillation stays
            # asynchronous. The optimistic revision check prevents an answer generated against an
            # old case snapshot from being committed after a concurrent user edit.
            scheduled_background = False
            result_case_state = case_state_v2
            committed_revision = case_state_v2.revision
            if self.memory is not None and session is not None:
                # Explicit type/medium mentions are canonical inputs, not model
                # judgments. Persist them before interview reconciliation so an
                # initial "Ich benötige einen RWDR" turn enters rwdr.v1 even when
                # the conservative LLM distiller returns an empty fact list.
                immediate_facts = extract_medium_facts(
                    question
                ) + extract_seal_type_facts(question)
                self.memory.record_turn(
                    tenant_id=scope.tenant_id,
                    session_id=session.session_id,
                    question=question,
                    answer=answer.text,
                    facts=immediate_facts,
                    now=datetime.now(timezone.utc).isoformat(),
                    expected_case_revision=case_state_v2.revision,
                    owner_subject=session.owner_subject,
                )
                if immediate_facts:
                    committed_revision += 1
                    if self.cross_session is not None:
                        self.cross_session.remember_durable(
                            tenant_id=scope.tenant_id,
                            facts=immediate_facts,
                            owner_subject=session.owner_subject,
                        )
                committed_view = self.memory.recall(
                    tenant_id=scope.tenant_id,
                    session_id=session.session_id,
                    owner_subject=session.owner_subject,
                )
                result_case_state = committed_view.case_state_v2 or case_state_v2
                if self.distiller is not None:
                    if self.adaptive_interview_enabled:
                        # A visible next question must be based on facts from THIS turn. Waiting for
                        # the already-existing distillation adds no model call, but prevents the
                        # controller from re-asking the pending question against stale CaseState.
                        evaluation = await self._remember_and_refresh_interview(
                            timer,
                            tenant_id=scope.tenant_id,
                            session=session,
                            question=question,
                            answer_text=answer.text,
                            expected_case_revision=committed_revision,
                            legacy_answer_text=answer.text,
                            persist_shadow=self.adaptive_interview_shadow_enabled,
                        )
                        adaptive_next_question = (
                            evaluation.next_question if evaluation is not None else None
                        )
                        committed_view = self.memory.recall(
                            tenant_id=scope.tenant_id,
                            session_id=session.session_id,
                            owner_subject=session.owner_subject,
                        )
                        result_case_state = (
                            committed_view.case_state_v2 or result_case_state
                        )
                    else:
                        self._schedule_remember(
                            timer,
                            tenant_id=scope.tenant_id,
                            session=session,
                            question=question,
                            answer_text=answer.text,
                            expected_case_revision=committed_revision,
                        )
                        scheduled_background = True
                else:
                    # M8: settle the derived slice from the merged inputs (no distiller path)
                    self.recompute_derived_for(
                        tenant_id=scope.tenant_id,
                        session_id=session.session_id,
                        owner_subject=session.owner_subject,
                    )
                    evaluation = self.refresh_adaptive_interview(
                        tenant_id=scope.tenant_id,
                        session_id=session.session_id,
                        owner_subject=session.owner_subject,
                        legacy_answer_text=answer.text,
                        persist_shadow=self.adaptive_interview_shadow_enabled,
                    )
                    if self.adaptive_interview_enabled and evaluation is not None:
                        adaptive_next_question = evaluation.next_question
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
        result = PipelineResult(
            question=question,
            tenant_id=scope.tenant_id,
            flags=flags,
            understanding=understanding,
            answer=answer,
            case_state=result_case_state,
            turn_state=TurnState(
                run_id=timer.turn_id,
                case_id=result_case_state.case_id,
                case_revision_started=case_state_v2.revision,
                case_revision_current=result_case_state.revision,
                status="completed",
                risk_level="high" if risk_flags else "standard",
                route_name=(
                    route_decision.route.value if route_decision is not None else None
                ),
                execution_class=(
                    execution_decision.execution_class.value
                    if execution_decision is not None
                    else None
                ),
                model_tier=(
                    execution_decision.model_tier.value
                    if execution_decision is not None
                    else None
                ),
                verification_mode=(
                    execution_decision.verification_mode.value
                    if execution_decision is not None
                    else None
                ),
                policy_version=(
                    execution_decision.policy_version
                    if execution_decision is not None
                    else None
                ),
                needs_human_review=(
                    execution_decision.needs_human_review
                    if execution_decision is not None
                    else False
                ),
            ),
            grounded=bool(l1_grounding),
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
            authority_epoch=authority_epoch,
            risk_flags=risk_flags,
            # Phase 2B routing → render contract: attach the classified route's value ONLY when
            # route optimization actually ran and produced a decision (route_decision is None
            # whenever route_optimization_enabled is False), else None. Backward-compat: a None
            # here makes the serializer default every chat-UI display flag to today's always-show
            # behavior. Render-only — this does NOT touch skip_l3_for_route / L3 / kernel / RAG.
            route_name=(
                route_decision.route.value if route_decision is not None else None
            ),
            next_question=adaptive_next_question,
        )
        # The second authority read is deliberately the final potentially failing operation before
        # cache publication and response. A quarantine/revoke/update/expiry that committed while
        # this request ran therefore serves neither a stale answer nor a cache entry.
        if authority_guard is not None:
            authority_guard.recheck_before_serve()
        if (
            cache_key is not None
            and cached_answer is None
            and self.answer_cache is not None
            and execution_decision is not None
            and execution_decision.execution_class is ExecutionClass.S0
        ):
            self.answer_cache.put(
                tenant_id=scope.tenant_id, key=cache_key, answer=answer
            )
        return result

    async def _l1_generate(
        self,
        generator: L1Generator,
        question: str,
        *,
        token_sink: "TokenSink | None",
        draft_stream_active: bool,
        **kwargs,
    ) -> Answer:
        """Phase 3B (draft-token streaming): the SINGLE seam shared by both
        ``self.generator.generate()`` call sites in ``run()`` (the initial generate and the
        regenerate-after-guard-BLOCK call) so the streaming-vs-non-streaming branch is written once,
        not duplicated. ``kwargs`` are forwarded VERBATIM to ``self.generator.generate`` /
        ``generate_stream`` — identical keyword args, identical prompt assembly either way.

        When ``draft_stream_active`` is False (flag off, no sink wired — this method is never even
        reached for the smalltalk route, since the smalltalk if/elif arms in ``run()`` never call
        this helper) this is byte-identical to ``await self.generator.generate(question, **kwargs)``.

        When True, streams raw deltas into ``token_sink`` as a non-authoritative draft
        (``draft=True``) — a pure observability side-channel — and returns the terminal Answer, which
        is byte-identical to what the non-streaming ``generate`` would have returned for the same
        inputs (the caller then feeds it into the SAME UNCHANGED output_guard / L3 verify pipeline as
        always). A mid-stream failure propagates unchanged, exactly like ``generate``'s own contract.
        """
        if not draft_stream_active:
            return await generator.generate(question, **kwargs)
        answer: Answer | None = None
        async for _ev in generator.generate_stream(question, **kwargs):
            if _ev.delta is not None:
                _emit_token(token_sink, _ev.delta, draft=True)
            elif _ev.answer is not None:
                answer = _ev.answer
        if answer is None:
            # Defensive: a successful stream always yields a terminal answer (mirrors the identical
            # defensive fallback on the Phase 3A smalltalk streaming branch above) -- unreachable on
            # success; a failure would already have raised out of the async-for above.
            answer = await generator.generate(question, **kwargs)
        return answer

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

    def compute_for(
        self, *, tenant_id: str, session_id: str, owner_subject: str = ""
    ) -> DerivedComputation:
        """M8: recompute the kernel from the session's CURRENT settled inputs, PERSIST the derived
        slice (wholesale replace — a stale value can never survive), and return the full result
        (derived + not_computed + notes) for the read surface (/compute, the panel). No engine or no
        memory → an empty result. Pure deterministic compute (no LLM); inputs via the recall seam."""
        if self.engine is None or self.memory is None:
            return DerivedComputation(derived=(), calc=CalcResult())
        inputs = self.memory.recall(
            tenant_id=tenant_id,
            session_id=session_id,
            owner_subject=owner_subject,
        ).case_state
        comp = recompute_derived(inputs, self.engine)
        self.memory.set_derived(
            tenant_id=tenant_id,
            session_id=session_id,
            derived=comp.derived,
            owner_subject=owner_subject,
        )
        return comp

    def recompute_derived_for(
        self, *, tenant_id: str, session_id: str, owner_subject: str = ""
    ) -> tuple[DerivedFact, ...]:
        """The mutation-channel projection of ``compute_for``: recompute + persist, return just the
        derived facts. Called on every input-mutation channel (background remember after distill;
        edit/forget routes)."""
        return self.compute_for(
            tenant_id=tenant_id,
            session_id=session_id,
            owner_subject=owner_subject,
        ).derived

    def refresh_adaptive_interview(
        self,
        *,
        tenant_id: str,
        session_id: str,
        owner_subject: str = "",
        legacy_answer_text: str = "",
        persist_shadow: bool | None = None,
    ) -> AdaptiveInterviewEvaluation | None:
        """Evaluate the one canonical interview policy from the committed state.

        Shadow instrumentation is fail-open: a telemetry/persistence failure never changes the
        authoritative answer or form mutation. No LLM client is reachable from this service.
        """
        if self.adaptive_interview_service is None or self.memory is None:
            return None
        try:
            view = self.memory.recall(
                tenant_id=tenant_id,
                session_id=session_id,
                owner_subject=owner_subject,
            )
            case_state = view.case_state_v2 or CaseStateV2.from_remembered_facts(
                case_id=session_id,
                revision=0,
                facts=view.case_state,
            )
            derived_reader = getattr(self.memory, "derived_facts", None)
            derived = (
                derived_reader(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    owner_subject=owner_subject,
                )
                if callable(derived_reader)
                else ()
            )
            return self.adaptive_interview_service.evaluate(
                tenant_id=tenant_id,
                session_id=session_id,
                case_state=case_state,
                derived_facts=tuple(derived),
                legacy_answer_text=legacy_answer_text,
                persist_shadow=(
                    self.adaptive_interview_shadow_enabled
                    if persist_shadow is None
                    else persist_shadow
                ),
            )
        except Exception as exc:  # noqa: BLE001 - default-off shadow must never break the product
            _log.warning(
                "adaptive interview shadow evaluation failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return None

    def clear_adaptive_interview(self, *, tenant_id: str, session_id: str) -> None:
        if self.adaptive_interview_service is None:
            return
        try:
            self.adaptive_interview_service.clear(
                tenant_id=tenant_id, session_id=session_id
            )
        except Exception as exc:  # noqa: BLE001 - legacy clear must still succeed
            _log.warning(
                "adaptive interview state clear failed: %s: %s",
                type(exc).__name__,
                exc,
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
        expected_case_revision: int,
    ) -> None:
        key = (tenant_id, session.session_id)
        task = asyncio.create_task(
            self._remember_background(
                timer,
                tenant_id=tenant_id,
                session=session,
                question=question,
                answer_text=answer_text,
                expected_case_revision=expected_case_revision,
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
        expected_case_revision: int,
    ) -> None:
        """Distill and merge facts after the already-committed turn.

        A revision mismatch means the user changed the case meanwhile; stale distilled
        values are discarded rather than overwriting the newer state.
        """
        try:
            await self._remember_and_refresh_interview(
                timer,
                tenant_id=tenant_id,
                session=session,
                question=question,
                answer_text=answer_text,
                expected_case_revision=expected_case_revision,
                legacy_answer_text=answer_text,
                persist_shadow=self.adaptive_interview_shadow_enabled,
            )
        finally:
            timer.emit()

    async def _remember_and_refresh_interview(
        self,
        timer: TurnTimer,
        *,
        tenant_id: str,
        session: SessionContext,
        question: str,
        answer_text: str,
        expected_case_revision: int,
        legacy_answer_text: str,
        persist_shadow: bool,
    ) -> AdaptiveInterviewEvaluation | None:
        """Commit distilled facts, settle derived values, then evaluate the controller.

        Shadow/default operation calls this from a background task. Visible adaptive-interview
        operation awaits the same work so its next-question payload cannot lag one user turn.
        """
        try:
            with timer.stage("distill_ms"):
                facts = await self.distiller.distill(
                    question=question, answer=answer_text
                )
                self.memory.merge_facts(
                    tenant_id=tenant_id,
                    session_id=session.session_id,
                    facts=facts,
                    expected_case_revision=expected_case_revision,
                    owner_subject=session.owner_subject,
                )
                if self.cross_session is not None and facts:
                    self.cross_session.remember_durable(
                        tenant_id=tenant_id,
                        facts=facts,
                        owner_subject=session.owner_subject,
                    )
            # M8: settle the derived slice from the just-distilled inputs (chat channel). Inside the
            # try so a recompute fault is caught by the same fail-safe (a lost derived slice is never
            # a failed request; the next read/mutation recomputes anyway).
            self.recompute_derived_for(
                tenant_id=tenant_id,
                session_id=session.session_id,
                owner_subject=session.owner_subject,
            )
            return self.refresh_adaptive_interview(
                tenant_id=tenant_id,
                session_id=session.session_id,
                owner_subject=session.owner_subject,
                legacy_answer_text=legacy_answer_text,
                persist_shadow=persist_shadow,
            )
        except Exception as exc:  # noqa: BLE001 — a background task must never die unhandled
            _log.warning(
                "remember/interview refresh failed (turn memory lost): %s: %s",
                type(exc).__name__,
                exc,
            )
            return None


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
    standard_client = (
        resolve(settings.standard_provider)
        if settings.execution_policy_enabled
        else None
    )

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
    generator = L1Generator(
        l1_client,
        assembler,
        l1_cfg,
        structured_output_enabled=settings.structured_answer_enabled,
    )
    standard_generator = None
    if standard_client is not None:
        standard_cfg = ModelConfig(
            model=settings.standard_model,
            temperature=settings.standard_temperature,
            cache_key=build_prompt_cache_key(
                "l1-standard",
                settings.standard_model,
                _l1_static_doctrine,
            ),
            stage="l1-standard",
            reasoning_effort="none",
        )
        standard_generator = L1Generator(
            standard_client,
            assembler,
            standard_cfg,
            structured_output_enabled=settings.structured_answer_enabled,
        )
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
    matrix = (
        InProcessCompatibilityMatrix()
        if settings.ground_enabled and settings.compatibility_matrix_enabled
        else None
    )
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
    session_factory = None
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

    knowledge_authority = None
    if settings.database_url:
        from sealai_v2.db.engine import make_engine, make_sessionmaker

        authority_session_factory = session_factory or make_sessionmaker(
            make_engine(settings.database_url)
        )
        knowledge_authority = PostgresKnowledgeAuthority(authority_session_factory)

    adaptive_interview_service: AdaptiveInterviewService | None = None
    if (
        memory is not None
        and settings.adaptive_interview_pack_rwdr_enabled
        and (
            settings.adaptive_interview_enabled
            or settings.adaptive_interview_shadow_enabled
        )
    ):
        from sealai_v2.db.interview import (
            InProcessInterviewRepository,
            PostgresInterviewRepository,
        )
        from sealai_v2.knowledge.domain_packs import load_rwdr_v1_pack

        interview_repository = (
            PostgresInterviewRepository(session_factory)
            if session_factory is not None
            else InProcessInterviewRepository()
        )
        adaptive_interview_service = AdaptiveInterviewService(
            pack=load_rwdr_v1_pack(), repository=interview_repository
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
    fachkarten_catalog = None
    if isinstance(retriever, InProcessRetriever):
        fachkarten_catalog = retriever.catalog
        fachkarten_version = fachkarten_catalog.version
    elif retriever is not None:
        fachkarten_catalog = load_fachkarten()
        fachkarten_version = fachkarten_catalog.version
    knowledge_material_terms = tuple(
        dict.fromkeys(
            term.strip()
            for card in (
                fachkarten_catalog.cards if fachkarten_catalog is not None else ()
            )
            for term in card.scope.get("material", ())
            if term.strip()
        )
    )
    wissensstand = compute_wissensstand(
        fachkarten_version=fachkarten_version,
        matrix_version=matrix.catalog.version if matrix is not None else "",
        traps_version=catalog.version if catalog is not None else "",
        calc_version=(
            engine.registry.version if isinstance(engine, CascadeCalcEngine) else ""
        ),
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
        _smalltalk_client = standard_client or helper_client
        _smalltalk_model = (
            settings.standard_model
            if settings.execution_policy_enabled
            else settings.helper_model
        )
        _smalltalk_temperature = (
            settings.standard_temperature
            if settings.execution_policy_enabled
            else settings.helper_temperature
        )
        smalltalk_generator = SmalltalkGenerator(
            client=_smalltalk_client,
            assembler=_smalltalk_assembler,
            model_config=ModelConfig(
                model=_smalltalk_model,
                temperature=_smalltalk_temperature,
                cache_key=build_prompt_cache_key(
                    "smalltalk_navigation",
                    _smalltalk_model,
                    _smalltalk_static_prompt,
                ),
                stage="smalltalk_navigation",
                reasoning_effort="none",
            ),
        )

    return Pipeline(
        generator=generator,
        client=helper_client,  # used by the understand helper stage
        helper_model=helper_cfg,
        standard_generator=standard_generator,
        frontier_generator=generator,
        execution_policy_enabled=settings.execution_policy_enabled,
        answer_cache=(
            InProcessExactAnswerCache(
                max_entries=settings.exact_answer_cache_max_entries,
                max_entries_per_tenant=settings.exact_answer_cache_max_entries_per_tenant,
                ttl_s=settings.exact_answer_cache_ttl_s,
            )
            if settings.execution_policy_enabled and settings.exact_answer_cache_enabled
            else None
        ),
        answer_cache_namespace_for_epoch=(
            lambda epoch: build_answer_cache_namespace(
                authority_epoch=epoch,
                knowledge_version=wissensstand,
                policy_version="execution-policy.v1:parameters.v2",
                answer_contract_version="engineering-answer.v2",
                model_identity=f"{settings.standard_provider}/{settings.standard_model}",
                structured_answers=settings.structured_answer_enabled,
            )
            if settings.execution_policy_enabled and settings.exact_answer_cache_enabled
            else None
        ),
        knowledge_authority=knowledge_authority,
        knowledge_material_terms=knowledge_material_terms,
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
        adaptive_interview_enabled=settings.adaptive_interview_enabled,
        adaptive_interview_shadow_enabled=settings.adaptive_interview_shadow_enabled,
        adaptive_interview_service=adaptive_interview_service,
        coverage_gate_enabled=settings.coverage_gate_enabled,
        response_contract_enabled=settings.response_contract_enabled,
        response_contract_general_guard_enabled=settings.response_contract_general_guard_enabled,
        baseline_hardening_enabled=settings.baseline_hardening_enabled,
        material_param_table_enabled=settings.material_param_table_enabled,
        knowledge_mode_enabled=settings.knowledge_mode_enabled,
        authoritative_knowledge_required=True,
        wissensstand=wissensstand,
        route_optimization_enabled=settings.route_optimization_enabled,
        route_telemetry_sink=(
            LoggingRouteTelemetrySink()
            if settings.route_optimization_enabled or settings.execution_policy_enabled
            else None
        ),
        route_prompt_families_enabled=settings.route_prompt_families_enabled,
        smalltalk_generator=smalltalk_generator,
        smalltalk_token_streaming_enabled=settings.smalltalk_token_streaming_enabled,
        draft_token_streaming_enabled=settings.draft_token_streaming_enabled,
        suppress_calc_for_non_kernel_routes_enabled=settings.suppress_calc_for_non_kernel_routes_enabled,
        risk_flag_prompt_enabled=settings.risk_flag_prompt_enabled,
    )
