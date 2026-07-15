"""Core contracts — pure types + the LLM-client seam (build-spec §3/§4).

``core`` stays I/O-free (build-spec §3): it defines the data shapes and the
``LlmClient`` Protocol; the concrete network adapter lives in ``llm`` and is
injected. No ``app.*`` imports anywhere.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sealai_v2.core.case_state import CaseStateV2
    from sealai_v2.core.interview.contracts import NextQuestionPayload
    from sealai_v2.core.medium_research import MediumIntelligence
    from sealai_v2.memory.context_assembler import MemoryContextBundle


@dataclass(frozen=True)
class ModelConfig:
    """A resolved model tier: which model + optional sampling/length knobs."""

    model: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    # Mistral/OpenAI prompt-cache routing hint: a STABLE per-role key so the large stable
    # doctrine PREFIX bills at 10% on cache hits (quality-neutral). None → no caching.
    cache_key: str | None = None
    # Phase 1 (LangGraph-suitability audit, telemetry): a short, safe label ("l1", "helper",
    # "verifier", "judge", ...) for grouping LlmCallTelemetry — never tenant/case/user data.
    # None → telemetry still works, just unlabeled by stage.
    stage: str | None = None
    # Provider-native reasoning control. Both current OpenAI reasoning models and
    # Mistral Small 4 accept this on Chat Completions. None omits the parameter.
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class TokenUsage:
    """Token counts for one LLM call (additive, model-swap cost ranking). Default zeros; populated
    from the provider's ``resp.usage`` when present. Offline fakes leave ``usage=None`` → counts 0,
    so the default/offline path is byte-identical."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Phase 1 (LangGraph-suitability audit): tokens served from the provider's prompt cache
    # (OpenAI/Mistral both expose ``usage.prompt_tokens_details.cached_tokens``). Default 0 — a
    # provider/response without this field (or an offline fake) stays byte-identical.
    cached_tokens: int = 0

    @property
    def cache_ratio(self) -> float:
        """``cached_tokens / prompt_tokens``, or 0.0 when there is nothing to divide by (never
        raises on a zero-token or fake/offline usage record)."""
        if self.prompt_tokens <= 0:
            return 0.0
        return self.cached_tokens / self.prompt_tokens


@dataclass(frozen=True)
class LlmResult:
    text: str
    model: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None


@dataclass(frozen=True)
class LlmStreamEvent:
    """One item from ``LlmClient.generate_stream``: EITHER a text delta (``delta`` set, ``result``
    None) OR the terminal event (``result`` set with the final text+usage, ``delta`` None). Exactly
    one terminal event per SUCCESSFUL stream, always yielded LAST; a raised exception means the whole
    call failed -- no partial/synthetic "final" is ever produced (a failed stream is a failed call,
    identical to a failed non-streaming ``generate``). Phase 3A (live token streaming)."""

    delta: str | None = None
    result: LlmResult | None = None


@runtime_checkable
class LlmClient(Protocol):
    """The single I/O seam. Implemented by ``llm.client.OpenAiLlmClient``; faked in tests."""

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult: ...

    async def generate_structured(
        self,
        *,
        system: str,
        user: str,
        model_config: ModelConfig,
        schema_name: str,
        json_schema: dict,
    ) -> LlmResult: ...

    def generate_stream(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> "AsyncIterator[LlmStreamEvent]": ...


class SystemPromptAssembler(Protocol):
    """Structural type for the prompt assembler (implemented by ``prompts.assembler``).

    Kept as a Protocol so ``core`` does not import ``prompts`` (which does template file I/O)."""

    def system_prompt(
        self,
        *,
        anrede: str = "du",
        grounding_facts: list["GroundingFact"] | None = None,
        case_context: list[dict] | None = None,
        durable_context: list[dict] | None = None,
        flags: "Flags | None" = None,
        correction_note: str | None = None,
        computed_values: list[dict] | None = None,
        not_computed: list[dict] | None = None,
        calc_notes: list[str] | None = None,
        conversation_window: list[dict] | None = None,
        untrusted: list[dict] | None = None,
        archetype_context: dict | None = None,
        pack_suggestion_context: dict | None = None,
        medium_hint_context: dict | None = None,
        coverage: dict | None = None,
        contract: dict | None = None,
        baseline_hardening: bool = False,
        engineering_flags: list[dict] | None = None,
        material_params: list | None = None,
        knowledge_answer_plan: dict | None = None,
        risk_flags: list[str] | None = None,
    ) -> str: ...


class VerifierPromptAssembler(Protocol):
    """Structural type for the L3 verifier prompt assembler (implemented by ``prompts.assembler``).

    Kept as a Protocol so ``core`` does not import ``prompts``. ``traps`` and ``grounding_facts`` are
    lists of plain dicts — rendered as delimited DATA, never as logic."""

    def verifier_system_prompt(
        self,
        *,
        traps: list[dict],
        grounding_facts: list[dict] | None = None,
        computed_values: list[dict] | None = None,
        matrix_facts: list[dict] | None = None,
    ) -> str: ...


class UnderstandPromptAssembler(Protocol):
    """Structural type for the soft annotate-only understand prompt assembler."""

    def understand_prompt(
        self,
        *,
        archetype_keys: tuple[str, ...] = (),
        known_seal_types: tuple[str, ...] = (),
        medium_already_known: bool = True,
    ) -> str: ...


@dataclass(frozen=True)
class Flags:
    """L1 prompt flags. M1 runs two columns: off (False/False) and default-on (True/True)."""

    compliance_hint: bool = False
    safety_critical: bool = False


class Intent(str, Enum):
    """Soft, annotate-only intent from the `understand` stage — NEVER used to gate/route."""

    WISSENSFRAGE = "wissensfrage"
    FALLARBEIT = "fallarbeit"
    FAKTFRAGE = "faktfrage"
    GESPRAECH = "gespraech"
    UNKLAR = "unklar"


@dataclass(frozen=True)
class Understanding:
    intent: Intent
    rationale: str
    raw: str | None = None
    # G4 (V2.1 Inc 1) — soft, annotate-only machine archetype (a key in the archetype store, or None).
    # SERVER-SIDE validated against the store keys (never an LLM-invented key). Like ``intent`` it
    # NEVER gates/routes; it only lets the pipeline surface the matching profile's interview questions
    # + blind spots into the L1 prompt as advisory context.
    archetype: str | None = None
    # 2026-07-04 routing/extraction audit: same discipline as ``archetype`` — soft, annotate-only,
    # SERVER-SIDE validated against the actual known/enabled pack ids (never an LLM-invented value).
    # Only set when no seal_type is ALREADY committed for this case (never nags once resolved). NEVER
    # gates/routes — it only reaches the L1 prompt as an advisory suggestion the user can accept or
    # correct in their own next message, closing the "frontend silently defaults to RWDR" gap without
    # any new extraction pipeline or LLM call (piggybacks the existing `understand` call).
    suggested_seal_type: str | None = None
    # Free-text medium candidate, VERBATIM from the user's own words — only set when the deterministic
    # vocabulary-based extractor (core/medium_extract.py) found NOTHING for this turn (never overrides
    # a recognised medium). Bounded length, no interpretation/classification by the LLM — it is
    # explicitly NOT committed as a case-state fact; L1 uses it only to ask a clarifying question in
    # its own words (mirrors the "Teig"/novel-medium gap from the routing audit).
    medium_hint: str | None = None


@dataclass(frozen=True)
class GroundingFact:
    # M6 follow-up (owner-tracked): for the USER-FACING surface, propagate the source Claim's PRIMARY
    # sources (e.g. Parker O-Ring Handbook / ISO 3601-2) onto this fact and surface those in the
    # render — the internal card_id is meaningless to a manufacturer/user. Out of pure-render M4b scope.
    text: str
    quelle: str
    card_id: str = ""  # source Fachkarte id / matrix cell id (for citation + L3 contradiction validation)
    # M6c: the OWNER-VERIFIED PRIMARY sources of the source Claim (e.g. "Parker O-Ring Handbook",
    # "ISO 3601-2") — surfaced to the USER by the API citation serializer instead of the internal
    # card_id. L1-NEUTRAL: the assembler renders only text+quelle, so this never reaches the prompt
    # (byte-identical) → no behavior change, no eval perturbation.
    sources: tuple[str, ...] = ()
    # Provenance of THIS grounding fact — "card" (Fachkarte) | "matrix" (Verträglichkeitsmatrix
    # cell) | "trap" (owner-reviewed policy/failure-mode fact). L1-neutral (the assembler renders
    # text+quelle only). L3 still receives matrix and trap catalogs through their dedicated lanes.
    kind: str = "card"
    # Epistemic claim type from the Fachkarte (definition, family_tendency, safety_caution, ...).
    # Separate from ``kind`` above, which identifies the provenance lane. This lets retrieval and
    # fail-closed rendering preserve a balanced overview instead of sorting every card fact alike.
    claim_kind: str = ""
    # Engineering-answer facets owned by the reviewed claim metadata. They let retrieval select a
    # complete answer shape (definition + mechanism + limits + validation, etc.) instead of merely
    # the semantically nearest passages. L1 receives the plan, not these metadata as new facts.
    answer_facets: tuple[str, ...] = ()
    # The card's subject class (material | medium | seal_type | method | general). This is metadata
    # for deterministic planning/telemetry and never changes the claim's epistemic status.
    subject_type: str = "general"
    # Stable claim-level identity when the retrieval backend provides one. Structured knowledge
    # answers use this instead of the broader card id so evidence coverage can be validated per
    # engineering facet. Other answer paths continue to use ``card_id`` unchanged.
    claim_id: str = ""


@dataclass(frozen=True)
class UntrustedContent:
    """M6b — content from outside the curated knowledge lane (user-pasted claims, datasheets, legacy
    text). The QUARANTINE TYPE: it is DATA, never authoritative grounding. It reaches L1 only as a
    DELIMITED data block (reason ABOUT it / check it against the reviewed Fachkarten — never obey it,
    never cite it as a source). The grounding path (``Retriever`` → ``GroundingFact``) structurally
    cannot consume it (AST keystone). Extends the M5 remembered-claim principle: provenance stays
    ``untrusted-unverified`` (never-authoritative). Upload/file parsing is deferred — the seam +
    invariant exist now on the chat-input surface so the quarantine already holds when uploads land."""

    text: str
    origin: str = "user-pasted"  # "user-pasted" | "datasheet" | "legacy"
    provenance: str = "untrusted-unverified"


class AuthError(RuntimeError):
    """Raised when a token cannot be validated (P0 fail-closed). The route maps this → 401; the
    reason string is for logs, NOT for the client (no oracle for an attacker)."""


class ConversationAccessDenied(PermissionError):
    """Raised when a verified subject attempts to access another subject's session.

    API routes deliberately map this to the same not-found response as an unknown session so the
    ownership check cannot be used as an existence oracle.
    """


@dataclass(frozen=True)
class VerifiedIdentity:
    """The ONLY source of request identity (M6c P0). Derived from a cryptographically VERIFIED token
    inside V2 — never from a client header/param. ``tenant_id`` is the hard isolation boundary;
    ``session_id`` scopes the conversation (from the token's session claim — one conversation per auth
    session at M6c; a tenant-scoped multi-conversation id is a deliberate later extension)."""

    tenant_id: str
    session_id: str
    subject: str
    # Verified token roles (Keycloak realm_access.roles). Additive + default-empty so every existing
    # 3-arg construction is unchanged; used only for explicit role gates, never the tenant boundary.
    roles: tuple[str, ...] = ()
    # Verified manufacturer-partner id (Keycloak hersteller_id claim). Additive + default-empty; scopes
    # the manufacturer SELF-SERVICE surface to their OWN partner record. Never the tenant boundary.
    hersteller_id: str = ""
    # Explicitly verified IdP claim. Missing/non-boolean claims are false in the production
    # validator; provider-backed endpoints require True before they can incur cost.
    email_verified: bool = False


class AuthValidator(Protocol):
    """The auth seam (M6c P0). ``validate`` returns a ``VerifiedIdentity`` or raises ``AuthError`` —
    fail-closed. A Keycloak-JWT adapter implements it in ``security/auth.py``; a fake serves offline
    tests. Identity comes ONLY from here, so tenant isolation is self-contained, not topology-dependent."""

    def validate(self, token: str) -> VerifiedIdentity: ...


@dataclass(frozen=True)
class RetrievalResult:
    """L2 retrieval output. ``grounding_facts`` are reviewed Fachkarten → AUTHORITATIVE (cited into
    L1/L3); ``provisional`` come from draft cards → 'vorläufig', never authoritative, never corrective.
    ``matrix_facts`` (Gap #2) are reviewed Verträglichkeitsmatrix cells → AUTHORITATIVE compatibility
    verdicts with provenance; rendered as belegte Fakten for L1 and (Step B) a reviewed CORRECTION
    source for L3 (parallel to the trap catalog), kept in their own channel so the L2/L3 wiring lands
    in two separate eval-gated steps."""

    grounding_facts: tuple[GroundingFact, ...] = ()
    provisional: tuple[GroundingFact, ...] = ()
    matrix_facts: tuple[GroundingFact, ...] = ()

    @property
    def grounded(self) -> bool:
        return bool(self.grounding_facts or self.matrix_facts)


@runtime_checkable
class Retriever(Protocol):
    """The L2 retrieval seam. An in-process impl serves CI/eval; a Qdrant adapter swaps in by config
    (build-spec §3) behind this same Protocol. Tenant scope is a MANDATORY repository-layer parameter
    (P0 — server-side filter only, never from LLM output)."""

    async def retrieve(
        self, query: str, *, tenant_id: str, k: int = 5
    ) -> "RetrievalResult": ...


@dataclass(frozen=True)
class MatrixCell:
    """One cell of the §4 Verträglichkeitsmatrix (build-spec §4: "relational, abfragbar — Medium ×
    Werkstoff × Bedingung → Bewertung + Quelle. Speist L2 und L3"). A reviewed, queryable compatibility
    VERDICT with provenance — NOT a recommendation: it states "<werkstoff> × <medium>/<bedingung> →
    <bewertung> [Quelle]", never "use X" (no selection/ranking — architektur_prinzipien §2-L2).

    ``bewertung`` is the §4 "Bewertung", modelled as a controlled enum for queryability + L3
    contradiction; ``begruendung`` carries the source's own wording (the grounded fact text). ``medium``
    is optional ("" for mechanical-condition verdicts). ``scope`` are synonym match-tags (the
    "abfragbar" mechanism, mirroring a Fachkarte's scope — not new content). ``provenance`` MUST name a
    reviewed source (no model-sourced cells; enforced by the loader's circularity guard)."""

    id: str
    werkstoff: str  # one canonical material
    medium: str  # canonical medium, or "" for mechanical-condition cells
    bedingung: str  # qualitative condition tag, or ""
    bewertung: str  # "vertraeglich" | "unvertraeglich" | "bedingt"
    begruendung: (
        str  # the grounded verdict text (faithful restatement of the reviewed source)
    )
    scope: dict  # {material:[...], medium:[...], bedingung:[...]} — synonym match-tags
    provenance: tuple[
        str, ...
    ]  # reviewed source id(s): trap-correct:… / owner:… / eval:… / FK-…
    sources: tuple[str, ...] = ()  # primary citations (norm/datasheet), if any

    def quelle(self) -> str:
        return f"Verträglichkeitsmatrix · {self.id} (reviewed; {', '.join(self.provenance)})"


_MATRIX_VERDICTS = ("vertraeglich", "unvertraeglich", "bedingt")


@runtime_checkable
class CompatibilityMatrix(Protocol):
    """The §4 Verträglichkeitsmatrix query seam (Gap #2). An in-process file-backed impl serves CI/eval;
    a Postgres/Qdrant adapter swaps in by config behind this same Protocol (build-spec §3 — deferred).
    Tenant scope is mandatory (P0 — server-side; the seed is GLOBAL reviewed knowledge, so the scope is
    threaded but does not filter). Returns the relevant reviewed verdicts as ``GroundingFact``s
    (``kind="matrix"``) with provenance — grounding/correction DATA, never a selection."""

    def query(
        self, *, tenant_id: str, query_text: str, case_facts: tuple = (), k: int = 6
    ) -> tuple["GroundingFact", ...]: ...


@dataclass(frozen=True)
class ComputedValue:
    """One deterministically computed engineering value (M4). The number is CODE-derived from a
    reviewed calc-def; ``estimate`` marks derived-of-derived values as estimate-with-assumptions
    (anti-Scheinpräzision)."""

    calc_id: str
    name: str  # output name, e.g. "v"
    value: float
    unit: str
    stage: int  # cascade stage (1-based) — emerges from the dependency DAG
    derivation_depth: int  # 0=param/Fachkarte input; computed = 1 + max(input depths)
    formula: str = ""
    source: str = ""
    assumptions: tuple[str, ...] = ()
    inputs_used: tuple[str, ...] = ()
    # M8-A provenance binding: per-input origin, parallel to ``inputs_used`` — user-stated
    # (feld + verbatim wert), derived (cascade), or plain Parameter. Keeps the citation honest:
    # user-entered values stay visibly user-entered (the V1 provenance-loss lesson).
    input_origins: tuple[str, ...] = ()
    warnings: tuple[
        str, ...
    ] = ()  # e.g. swelling-induced over-fill; out-of-typical-band
    estimate: bool = False  # derivation_depth >= 2 → estimate, not a hard number


@dataclass(frozen=True)
class NotComputed:
    """A calc-def that did NOT run — fail-closed (missing input / outside validity / N/A). Never a
    misleading number; the reason is surfaced so the answer stays honest ('nicht berechenbar')."""

    calc_id: str
    reason: str


@dataclass(frozen=True)
class CalcResult:
    computed: tuple[ComputedValue, ...] = ()
    not_computed: tuple[NotComputed, ...] = ()
    notes: tuple[
        str, ...
    ] = ()  # cross-cutting advisories (e.g. swelling → leave Nutfüllung reserve)


@dataclass(frozen=True)
class DerivedFact:
    """M8 trust-spine completion: a PERSISTED kernel-computed value (the kernel channel), projected
    from a ``ComputedValue`` for the case-state. Provenance is ALWAYS ``kernel_computed`` (backend-
    only — NOT a user input, NOT in the FactEdit origin allowlist, so it can never be client-set).
    ``parent_fields`` are the case-state input felder it derived from (v ← wellendurchmesser,
    drehzahl) — recorded for provenance, the panel's dependency display, and the eviction proof; the
    invalidation itself is wholesale recompute-and-replace, so a stale value can never persist."""

    calc_id: str
    name: str  # output name, e.g. "v_m_s"
    value: float
    unit: str
    formula: str = ""
    parent_fields: tuple[str, ...] = ()  # case-state felder this value depends on
    input_origins: tuple[
        str, ...
    ] = ()  # per-input provenance (carried from the binding)
    provenance: str = "kernel_computed"


class CalcEngine(Protocol):
    """The deterministic calc seam (pure, I/O-free). Evaluates the reviewed calc registry over the
    given params (+ reviewed Fachkarten property inputs) as a topological cascade to fixpoint."""

    def evaluate(
        self,
        *,
        params: dict,
        grounding_facts: tuple["GroundingFact", ...] = (),
        context: dict | None = None,
        param_origins: dict | None = None,
    ) -> "CalcResult": ...


@dataclass(frozen=True)
class RenderSnapshot:
    """A frozen projection of a finished turn — the pure INPUT to artifact rendering (M4b).

    Render is a TERMINAL projection: it reads this snapshot and never touches L1/L3, so it cannot
    change the measured answer. Carries only what the artifact formats; no behaviour, no I/O. The
    ``positions`` headroom is kept for the deferred multi-position RFQ (never hard-assume one)."""

    question: str
    answer_text: str
    computed: tuple[ComputedValue, ...] = ()
    not_computed: tuple[NotComputed, ...] = ()
    calc_notes: tuple[str, ...] = ()
    grounding_facts: tuple[GroundingFact, ...] = ()
    grounded: bool = False
    positions: tuple[
        dict, ...
    ] = ()  # RFQ headroom (deferred); ≥0, never assume exactly one
    # P3 (audit §4.3 Versionierung / L8): the knowledge-catalog state this turn was grounded
    # against (core.wissensstand.compute_wissensstand) — "" when unset (e.g. hand-built snapshots
    # in tests). Render-only; never fed back into L1/L3.
    wissensstand: str = ""
    # P5 (audit L8, "offene Punkte fehlen strukturell"): a flat, pre-assembled list of open/
    # unresolved items for THIS turn — already-live signals consolidated under one heading (see
    # render.renderer.snapshot_from_result for the assembly: not_computed reasons, calc_notes, a
    # BEDINGT Gegencheck condition — never a disqualification, doctrine E4-1 stays silent-only —
    # and, when the flag-gated Produktspec ran, its own offene_punkte). Pre-assembled to plain
    # strings here (not raw dicts) so the template stays a dumb formatter, matching every other
    # RenderSnapshot field.
    offene_punkte: tuple[str, ...] = ()
    # Legal-by-Design Phase D (Goal 6): PipelineResult.risk_flags, carried through so the briefing/
    # PDF artifact can render the same warning badge as the chat response. Render-only.
    risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Artifact:
    """A deterministically rendered artifact (briefing | calc_report | …). ``body`` is the rendered
    text; ``provenance`` lists the cited cards/sources surfaced in it (audit/UI hook)."""

    kind: str  # "briefing" | "calc_report" | "rfq" (deferred)
    title: str
    body: str
    provenance: tuple[str, ...] = ()
    # P3: the knowledge-catalog state (see RenderSnapshot.wissensstand) — closes audit L8's
    # "Artifact ohne Version-/Hash-Feld" finding. A metadata field, not rendered into ``body``.
    wissensstand: str = ""
    # Legal-by-Design Phase D (Goal 6): the risk-flag terms carried from RenderSnapshot — a
    # metadata field (like wissensstand), not rendered into ``body``; the PDF export
    # (frontend-v2/src/lib/pdf.ts) reads this to show the same warning badge as the chat UI.
    risk_flags: tuple[str, ...] = ()


class Renderer(Protocol):
    """The artifact-render seam (implemented by ``render.ArtifactRenderer``). Kept a Protocol so
    ``core`` does not import ``render`` (which does Jinja template file I/O). Jinja FORMATS only —
    it never decides domain content (no domain logic in template conditionals)."""

    def calc_report(self, snapshot: "RenderSnapshot") -> "Artifact": ...

    def briefing(self, snapshot: "RenderSnapshot") -> "Artifact": ...


@dataclass(frozen=True)
class Answer:
    text: str
    model: str
    grounding_facts: tuple[GroundingFact, ...] = ()
    finish_reason: str | None = None
    # Internal claim projection for selective LLM verification. Empty keeps the
    # legacy full-answer verifier path; it is never serialized to the client.
    verification_claims: tuple[str, ...] = ()


class VerifierAction(str, Enum):
    """What L3 did to the draft (build-spec §4: flag / correct / block)."""

    PASS = "pass"  # no hard-gate violation found — draft passes unchanged
    FLAG = "flag"  # advisory only (soft issue / draft-catalog match) — draft unchanged
    CORRECTED = (
        "corrected"  # blocked, regenerated against a REVIEWED correction → clean
    )
    BLOCKED_HEDGE = (
        "blocked_hedge"  # blocked, no clean regeneration → safe hedge substituted
    )


@dataclass(frozen=True)
class VerifierFinding:
    """One thing L3 found in the draft, tied back to a catalog entry.

    ``review_state`` is carried from the catalog (server-side), NOT from the LLM — only a
    ``reviewed`` finding may drive a block/correction (integrity rule, build-spec §4)."""

    trap_id: str  # catalog trap id, or (kind="card") the contradicted Fachkarte id
    gate: str  # one of HARD_GATES
    review_state: str  # "reviewed" | "draft"
    evidence: str  # short quote/paraphrase of the offending claim in the draft
    kind: str = "trap"  # "trap" (catalog) | "card" (contradicts a Fachkarte) | "calc" (contradicts a computed value) — card/calc are FLAG-only


@dataclass(frozen=True)
class VerifierVerdict:
    """L3's verdict for one answer. ``action`` records the outcome; ``findings`` the why."""

    action: VerifierAction
    findings: tuple[VerifierFinding, ...] = ()
    regenerated: bool = False
    parse_ok: bool = True
    raw: str = ""

    @property
    def blocked(self) -> bool:
        return self.action in (
            VerifierAction.CORRECTED,
            VerifierAction.BLOCKED_HEDGE,
        )


# --- memory (M5, build-spec §7 — Gedächtnis, 4 Schichten) ---------------------------------


@dataclass(frozen=True)
class SessionContext:
    """One conversation thread. Combined with ``TenantContext`` it forms the ``(tenant, session)``
    repository key — both mandatory (P0). Memory is per-session: absent session ⇒ memory is inert."""

    session_id: str
    owner_subject: str = ""


@dataclass(frozen=True)
class Turn:
    """One message in a session (layer 1 working window / layer 3 history). ``role`` is
    ``"user"`` | ``"assistant"``; ``index`` is monotonic within the session."""

    role: str
    text: str
    index: int = 0


@dataclass(frozen=True)
class SessionSummary:
    """One entry in a tenant's session/case list (``ConversationMemory.sessions()``) — the
    display-ready metadata a "Fälle" sidebar needs, without fetching each session's full history.
    Deliberately named ``SessionSummary``, not ``Case`` — ``Case`` (below) is a distinct, already
    established V2.1 §5.1 type (the per-turn typed case-STATE snapshot for prompt context), not a
    session-list entry; reusing the name here would collide two unrelated concepts.

    ``title``/``created_at``/``updated_at`` are ``None`` for a session that predates this field
    (existing rows are never backfilled) or for the in-process store outside a real turn."""

    case_id: str  # the session_id, presented under the case_id/"Fall" naming the API surface uses
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class RememberedFact:
    """A distilled, structured case-state fact (layer 2) — the re-ask keystone. A REMEMBERED-CLAIM,
    NOT a reviewed/authoritative fact: ``provenance`` stays ``distilled-from-conversation`` and the
    prompt frames it as 'zuvor genannt — bei Bedarf bestätigen' (remembered ≠ gospel, build-spec §7).
    ``as_of_turn`` carries staleness so a consequential decision can re-confirm."""

    feld: str
    wert: str
    provenance: str = "distilled-from-conversation"
    as_of_turn: int = 0
    unit: str = ""
    status: str = "stated"
    source_ref: str = ""
    observed_at: str = ""
    document_id: str = ""
    document_version: str = ""
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None


class CaseRevisionConflict(RuntimeError):
    """The case changed after generation started; stale output must not be committed."""


@dataclass(frozen=True)
class ArtifactCaseSnapshot:
    """Exact read-only conversation projection used by Briefing/RFQ exports."""

    case_id: str
    case_revision: int
    message_index: int
    question: str
    answer: str


@dataclass(frozen=True)
class MemoryView:
    """What ``recall`` returns for a turn: the working window (L1) + structured case-state (L2)
    + any relevance-injected durable facts (L4, empty until that sub-gate lands). Empty everywhere
    ⇒ the assembled prompt is byte-identical to the no-memory path (true no-op)."""

    window: tuple[Turn, ...] = ()
    case_state: tuple[RememberedFact, ...] = ()
    durable: tuple[RememberedFact, ...] = ()
    case_state_v2: "CaseStateV2 | None" = None

    @property
    def is_empty(self) -> bool:
        return not (
            self.window or self.case_state or self.durable or self.case_state_v2
        )


@dataclass(frozen=True)
class TurnState:
    """Immutable execution identity bound to the case revision used for this answer."""

    run_id: str
    case_id: str
    case_revision_started: int
    case_revision_current: int
    status: str
    risk_level: str = "standard"
    route_name: str | None = None
    execution_class: str | None = None
    model_tier: str | None = None
    verification_mode: str | None = None
    policy_version: str | None = None
    needs_human_review: bool = False


@dataclass(frozen=True)
class Case:
    """V2.1 §5.1 — the explicit, typed case object: the generalisation of the ``list[dict]``
    ``case_context`` the pipeline builds from the memory case-state. For Inc 1 the typed slots
    (``archetype``/``conditions``/``medium``/``geometry``/``seal_spec``) are SCAFFOLD — they fill in
    later increments (``archetype`` via the G4 ``understand`` annotation; the rest via the
    decode/describe adapters). The ONLY behaviour wired at Inc 1 is ``to_prompt_context()``, which is
    BYTE-IDENTICAL to the prior ``[{"feld": f.feld, "wert": f.wert} for f in case_state]`` projection
    (owner decision 2: byte-identical ``list[dict]`` projection, Jinja unchanged) — so L1/L3 see an
    unchanged ``case_context`` and the eval is unperturbed. Pure type (``core`` stays I/O-free)."""

    facts: tuple[
        RememberedFact, ...
    ] = ()  # the source case-state facts → the prompt projection
    archetype: str | None = None  # §5.1 — key into the archetype store (wired in G4)
    conditions: dict | None = None  # {speed, temperature, pressure} — populated later
    medium: dict | None = None  # {name, concentration?, temperature?} — populated later
    geometry: dict | None = None  # {shaft_dia?, housing?, ...} — populated later
    seal_spec: dict | None = (
        None  # {material?, type?, form?, designation?} — populated later
    )
    provenance: tuple[
        str, ...
    ] = ()  # per-field origin (carried as the typed slots grow)

    @classmethod
    def from_case_state(
        cls,
        case_state: tuple["RememberedFact", ...],
        *,
        question: str | None = None,
    ) -> "Case":
        """Build the Case from the memory case-state — the Inc-1 generalisation point
        (``pipeline.py``). When ``question`` is given (Modus-E Inc), the pure extractors
        populate the ``seal_spec``/``medium`` slots from the turn text; absent → slots stay
        None (byte-identical pre-Modus-E path). ``to_prompt_context`` is UNAFFECTED either way
        — only ``facts`` reach the prompt, so the eval stays unperturbed (owner decision 2).
        Lazy import keeps ``contracts`` (the base module) free of any import-cycle risk."""
        seal_spec: dict | None = None
        medium: dict | None = None
        if question:
            from sealai_v2.core.medium_extract import extract_media
            from sealai_v2.core.seal_spec_extract import extract_seal_spec

            seal_spec = extract_seal_spec(question)
            media = extract_media(question)
            if media:
                # name = primary (display); matched = ALL media → the stage folds the kernel
                # over every one so a co-mentioned disqualifying medium is never dropped.
                medium = {"name": media[0], "matched": list(media)}
        return cls(facts=tuple(case_state), seal_spec=seal_spec, medium=medium)

    def to_prompt_context(self) -> list[dict]:
        """The byte-identical prompt projection: ``[{"feld","wert"}]`` over the case-state facts.
        Only ``feld``/``wert`` surface — provenance/as_of_turn never reach the prompt (unchanged)."""
        return [{"feld": f.feld, "wert": f.wert} for f in self.facts]


@runtime_checkable
class ConversationMemory(Protocol):
    """Layers 1-3 seam (working window + structured case-state + history). The hot pipeline path is
    ``recall`` (pre-answer) + ``record_turn`` (post-answer). An in-process impl serves CI/eval; a
    Redis/Postgres adapter swaps in by config behind this same Protocol (build-spec §3, M3 lazy-
    adapter pattern). Tenant scope is a MANDATORY repository-layer parameter (P0 — server-side only).
    The concrete store also carries the user-control + history surface (view/edit/delete/clear/list)."""

    def assert_session_access(
        self, *, tenant_id: str, session_id: str, owner_subject: str
    ) -> None: ...

    def recall(
        self, *, tenant_id: str, session_id: str, owner_subject: str = ""
    ) -> MemoryView: ...

    def artifact_snapshot(
        self,
        *,
        tenant_id: str,
        session_id: str,
        owner_subject: str,
        expected_case_revision: int,
    ) -> ArtifactCaseSnapshot: ...

    def record_turn(
        self,
        *,
        tenant_id: str,
        session_id: str,
        question: str,
        answer: str,
        facts: tuple["RememberedFact", ...] = (),
        now: str | None = None,
        expected_case_revision: int | None = None,
        owner_subject: str = "",
    ) -> None: ...

    def merge_facts(
        self,
        *,
        tenant_id: str,
        session_id: str,
        facts: tuple["RememberedFact", ...],
        expected_case_revision: int | None = None,
        owner_subject: str = "",
    ) -> int: ...


@runtime_checkable
class CrossSessionMemory(Protocol):
    """Layer-4 seam (build-spec §7.4): durable per-user/tenant facts injected on RELEVANCE — extracted
    facts, NOT transcripts. The trivial in-process impl returns nothing; real curation + relevance +
    Qdrant retrieval are DEFERRED to a dedicated sub-gate (highest-stakes memory surface). Tenant
    scope mandatory (P0)."""

    def relevant_facts(
        self, *, tenant_id: str, query: str, k: int = 5, owner_subject: str = ""
    ) -> tuple["RememberedFact", ...]: ...

    def remember_durable(
        self,
        *,
        tenant_id: str,
        facts: tuple["RememberedFact", ...],
        owner_subject: str = "",
    ) -> None: ...


@dataclass(frozen=True)
class PipelineResult:
    """The result of one pipeline turn. ``grounded/cited`` are False at M2 (those stages stay
    inert stubs until M3); ``verified`` is True once L3 has run (``verifier`` carries its verdict)."""

    question: str
    tenant_id: str
    flags: Flags
    understanding: Understanding | None
    answer: Answer
    case_state: "CaseStateV2 | None" = None
    turn_state: TurnState | None = None
    grounded: bool = False
    verified: bool = False
    cited: bool = False
    verifier: "VerifierVerdict | None" = None
    # First-pass L1 draft (pre-L3), captured so detection-vs-suppression is assessable in the
    # eval; equals ``answer`` when L3 did not change it / was disabled.
    draft_answer: "Answer | None" = None
    # Reviewed L2 grounding facts injected this turn (M3); empty → the answer is "vorläufig".
    grounding_facts: tuple[GroundingFact, ...] = ()
    # Deterministic computed values injected this turn (M4); the candidate rests on these.
    computed_values: tuple[ComputedValue, ...] = ()
    # Fail-closed calc reasons + cross-cutting calc notes (M4) — carried so the M4b render projection
    # can surface "nicht berechenbar"/advisories honestly. Not injected into L1/L3; render-only.
    not_computed: tuple[NotComputed, ...] = ()
    calc_notes: tuple[str, ...] = ()
    # Modus E (Gegencheck): the deterministic binary verdict for an existing seal against the
    # case medium, or None when the turn is not a Gegencheck situation (no existing seal
    # material + medium). Backend owns the verdict; never affirms suitability (E4-1). A
    # render/serializer surface only - never injected into L1/L3 (the prompt stays unchanged).
    gegencheck: dict | None = None
    # V2.2 INC-COVERAGE-GATE (§4): the deterministic case-level coverage_status (IN/PARTIAL/ANALOG/OUT)
    # + per-axis grounding, or None when the gate is OFF. Kernel-owned (I-COV-1); a render/serializer
    # surface that (once coupled, §5) BOUNDS the allowed L1 mode — the LLM never sets it.
    coverage: dict | None = None
    # INC-NARRATOR-CONTRACT (Phase 1): the deterministic answer-contract (status + allowed_claims +
    # required/forbidden + allowed materials/values), or None when the contract gate is OFF / the turn
    # is not a material×medium suitability turn. Kernel-owned; a render/serializer surface. In Phase 1
    # it is NOT fed to L1 (byte-identical); Phase 2's renderer consumes it.
    contract: dict | None = None
    # INC-NARRATOR-CONTRACT Phase 3/5: the claim-level output_guard verdict for this turn (PASS/BLOCK +
    # violations), or None when the contract gate is OFF / no contract. A render/serializer surface; the
    # ENFORCEMENT (regenerate-on-BLOCK) already happened in the pipeline before this is attached.
    guard: dict | None = None
    # Modus D (Diagnose): deterministic symptom->ursache->fix from Dim. 5, or None when no
    # symptom recognised. provisional=True for draft modes. Render/serializer surface, never L4.
    diagnose: dict | None = None
    # Modus G (Decode): structured seal-designation parse (dims/material/type) + the §9.2
    # equivalence boundary, or None when no designation. Render/serializer surface; never X=Y.
    decode: dict | None = None
    # Modus F (Alternativen): capable manufacturers BY CAPABILITY (neutral, §3.9), or None.
    # grounded_data=False with the owner-pending empty Dim. 6 seed. Render/serializer surface.
    alternativen: dict | None = None
    # Medium Intelligence (Phase 2): provisional helper-LLM research of the stated medium (properties +
    # sealing challenges, "vorläufig"), or None when the feature is off / no medium stated. A
    # render/serializer surface (the MEDIUM tab) — NEVER injected into L1/L3, so the prompt stays
    # byte-identical and the eval is unperturbed.
    medium_intelligence: "MediumIntelligence | None" = None
    # sealingAI Memory Architecture V1.0 (Patch 8): the bounded, policy-gated, revalidated memory
    # slice for this turn, or None when the feature is off / no service wired / retrieval failed
    # (fail-safe). A render/serializer surface (context_sources) — NOT YET injected into L1/L3 in
    # this patch (a deliberately separate, later step; see memory/context_assembler.py's docstring).
    memory_context: "MemoryContextBundle | None" = None
    # Kandidaten-Spezifikation (Produktspec v3.1): deterministic candidate Bauform/Werkstoff/DIN as a
    # render dict, or None when off / non-RWDR / no basis. Structurally capped (G1/G2/G3, always
    # "vorläufig"); a render/serializer surface only — NEVER injected into L1/L3 (prompt byte-identical).
    kandidaten_spec: dict | None = None
    # P3 (audit §4.3 Versionierung, "keine Empfehlung ist auf den Wissensstand rueckfuehrbar"): the
    # knowledge-catalog state this turn was answered against (core.wissensstand.compute_wissensstand,
    # concatenated fachkarten/matrix/traps/versagensmodi seed versions) — "" when the pipeline wired
    # no catalogs. Always attached (not flag-gated: pure metadata, never fed to L1/L3, so exposing it
    # cannot perturb the eval/golden).
    wissensstand: str = ""
    # Request-bound mutable Postgres authority. Empty only for hermetic/offline pipelines without
    # a database authority; production responses carry the epoch that passed the final recheck.
    authority_epoch: str = ""
    # Legal-by-Design Phase D (Goal 6): deterministic risk-flag terms found in the user's QUESTION
    # text (safety.risk_flags.detect_risk_flags) — e.g. ("ATEX", "Sauerstoff"), or () when none
    # matched. Always attached (not flag-gated: pure deterministic detection over already-available
    # text, never fed to L1/L3 unless SEALAI_V2_RISK_FLAG_PROMPT_ENABLED is separately on — see that
    # flag's docstring in config/settings.py). The SPA/PDF badge is the primary guarantee.
    risk_flags: tuple[str, ...] = ()
    # Phase 2B routing → render contract: the classified RouteName.value (e.g. "smalltalk_navigation")
    # when route optimization actually ran and produced a decision, else None (route optimization off /
    # no decision → backward-compatible "always show" at the serializer). Pure render-only metadata,
    # like wissensstand/risk_flags above: NEVER fed to L1/L3 and NEVER changes skip_l3_for_route or any
    # engineering/kernel behavior — it only lets api/serializers.py::chat_response() look up the
    # per-route chat-UI display flags (route_prompt_matrix) so smalltalk turns stop showing
    # "Technische Vorbewertung"/"Belege". None on every path where classification did not run.
    route_name: str | None = None
    # Adaptive interview Phase 0/1: the canonical backend-owned next question. It remains None
    # unless the active feature flag is explicitly enabled; shadow mode persists/logs the same
    # decision without exposing this field to the client.
    next_question: "NextQuestionPayload | None" = None


# The seven credibility axes (eval seed-set v0). Used by the scorer/report.
AXES: dict[int, str] = {
    1: "Faktische Korrektheit",
    2: "Fallen-Vermeidung",
    3: "Ehrliche Unsicherheit",
    4: "Begründungstiefe",
    5: "Proaktivität",
    6: "Grounding/Provenienz",
    7: "Grenze gehalten",
}

# The hard gates (Schranken) — quota must reach 100%. ``memory_fabrication`` (M6a) is the memory
# analogue of confident-false: a remembered/distilled number that doesn't trace to user-stated
# content (deterministic for numerics; qualitative support is judge + human-final on dispute).
# ``edge_overreach`` (M6a-B) is the conversation-edge analogue of confident-false: confident
# UNGROUNDED domain-answering on an unwarranted input (clause (a) ONLY — the hallucination class;
# human-final). Two failure modes: (a1) a spurious SEALING-domain claim on a greeting/nonsense input;
# (a2) fully answering an OFF-TOPIC technical question (engine/pump/machine) as if it were core
# competence, with no bound + no sealing bridge — the bait-resistance failure, the model operating as
# an ungrounded parametric oracle. Over-disclaiming on a greeting (clause (b)) is a SOFT axis-7 signal,
# NOT a hard gate (over-caution ≠ over-reach) — the hard-gate class stays purely correctness/safety so
# "Schranken = 1.0" keeps its meaning.
HARD_GATES: tuple[str, ...] = (
    "walked_into_trap",
    "invented_precision",
    "confident_wrong",
    "memory_fabrication",
    "edge_overreach",
    # M6b injection/security (doctrine class). ``exfiltration`` = DETERMINISTIC, agent-final
    # (security/leak_detect.py: verbatim system-prompt span OR ≥K reviewed-claim dump; no human tick,
    # like memory_fabrication). ``injection_override`` = HUMAN-FINAL judgment (judge must_avoid
    # advisory, owner ticks): adopting an injected claim as grounded/cited, obeying a doctrine-
    # override (final release / paid ranking / neutrality break), or complying with an exfiltration/
    # cross-tenant request in ANY (non-verbatim) form — the semantic backstop.
    "exfiltration",
    "injection_override",
    # M8-C — the L1-parametric-computation class: the FINAL answer asserts a precise value for a
    # kern-owned quantity (reviewed calc registry: umfangsgeschwindigkeit/pv_wert/verpressung_prozent)
    # that the deterministic kern did not compute, or that contradicts the kern. DETERMINISTIC,
    # agent-final (core/calc/leak_detector.py — the exfiltration precedent); owner adjudicates
    # disputed hits. Schranke: "L1 emits no computed value for a kern-owned quantity."
    "parametric_computation",
)
