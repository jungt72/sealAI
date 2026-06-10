"""Core contracts — pure types + the LLM-client seam (build-spec §3/§4).

``core`` stays I/O-free (build-spec §3): it defines the data shapes and the
``LlmClient`` Protocol; the concrete network adapter lives in ``llm`` and is
injected. No ``app.*`` imports anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ModelConfig:
    """A resolved model tier: which model + optional sampling/length knobs."""

    model: str
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class LlmResult:
    text: str
    model: str
    finish_reason: str | None = None


@runtime_checkable
class LlmClient(Protocol):
    """The single I/O seam. Implemented by ``llm.client.OpenAiLlmClient``; faked in tests."""

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult: ...


class SystemPromptAssembler(Protocol):
    """Structural type for the prompt assembler (implemented by ``prompts.assembler``).

    Kept as a Protocol so ``core`` does not import ``prompts`` (which does template file I/O)."""

    def system_prompt(
        self,
        *,
        anrede: str,
        grounding_facts: list["GroundingFact"] | None,
        case_context: list[dict] | None,
        flags: "Flags",
        correction_note: str | None = None,
        computed_values: list[dict] | None = None,
        not_computed: list[dict] | None = None,
        calc_notes: list[str] | None = None,
        conversation_window: list[dict] | None = None,
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


@dataclass(frozen=True)
class GroundingFact:
    # M6 follow-up (owner-tracked): for the USER-FACING surface, propagate the source Claim's PRIMARY
    # sources (e.g. Parker O-Ring Handbook / ISO 3601-2) onto this fact and surface those in the
    # render — the internal card_id is meaningless to a manufacturer/user. Out of pure-render M4b scope.
    text: str
    quelle: str
    card_id: str = (
        ""  # source Fachkarte id (for citation + L3 card-contradiction validation)
    )


@dataclass(frozen=True)
class RetrievalResult:
    """L2 retrieval output. ``grounding_facts`` are reviewed → AUTHORITATIVE (cited into L1/L3);
    ``provisional`` come from draft cards → 'vorläufig', never authoritative, never corrective."""

    grounding_facts: tuple[GroundingFact, ...] = ()
    provisional: tuple[GroundingFact, ...] = ()

    @property
    def grounded(self) -> bool:
        return bool(self.grounding_facts)


@runtime_checkable
class Retriever(Protocol):
    """The L2 retrieval seam. An in-process impl serves CI/eval; a Qdrant adapter swaps in by config
    (build-spec §3) behind this same Protocol. Tenant scope is a MANDATORY repository-layer parameter
    (P0 — server-side filter only, never from LLM output)."""

    async def retrieve(
        self, query: str, *, tenant_id: str, k: int = 5
    ) -> "RetrievalResult": ...


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


class CalcEngine(Protocol):
    """The deterministic calc seam (pure, I/O-free). Evaluates the reviewed calc registry over the
    given params (+ reviewed Fachkarten property inputs) as a topological cascade to fixpoint."""

    def evaluate(
        self,
        *,
        params: dict,
        grounding_facts: tuple["GroundingFact", ...] = (),
        context: dict | None = None,
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
    positions: tuple[dict, ...] = ()  # RFQ headroom (deferred); ≥0, never assume exactly one


@dataclass(frozen=True)
class Artifact:
    """A deterministically rendered artifact (briefing | calc_report | …). ``body`` is the rendered
    text; ``provenance`` lists the cited cards/sources surfaced in it (audit/UI hook)."""

    kind: str  # "briefing" | "calc_report" | "rfq" (deferred)
    title: str
    body: str
    provenance: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class Turn:
    """One message in a session (layer 1 working window / layer 3 history). ``role`` is
    ``"user"`` | ``"assistant"``; ``index`` is monotonic within the session."""

    role: str
    text: str
    index: int = 0


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


@dataclass(frozen=True)
class MemoryView:
    """What ``recall`` returns for a turn: the working window (L1) + structured case-state (L2)
    + any relevance-injected durable facts (L4, empty until that sub-gate lands). Empty everywhere
    ⇒ the assembled prompt is byte-identical to the no-memory path (true no-op)."""

    window: tuple[Turn, ...] = ()
    case_state: tuple[RememberedFact, ...] = ()
    durable: tuple[RememberedFact, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.window or self.case_state or self.durable)


@runtime_checkable
class ConversationMemory(Protocol):
    """Layers 1-3 seam (working window + structured case-state + history). The hot pipeline path is
    ``recall`` (pre-answer) + ``record_turn`` (post-answer). An in-process impl serves CI/eval; a
    Redis/Postgres adapter swaps in by config behind this same Protocol (build-spec §3, M3 lazy-
    adapter pattern). Tenant scope is a MANDATORY repository-layer parameter (P0 — server-side only).
    The concrete store also carries the user-control + history surface (view/edit/delete/clear/list)."""

    def recall(self, *, tenant_id: str, session_id: str) -> MemoryView: ...

    def record_turn(
        self,
        *,
        tenant_id: str,
        session_id: str,
        question: str,
        answer: str,
        facts: tuple["RememberedFact", ...] = (),
    ) -> None: ...


@runtime_checkable
class CrossSessionMemory(Protocol):
    """Layer-4 seam (build-spec §7.4): durable per-user/tenant facts injected on RELEVANCE — extracted
    facts, NOT transcripts. The trivial in-process impl returns nothing; real curation + relevance +
    Qdrant retrieval are DEFERRED to a dedicated sub-gate (highest-stakes memory surface). Tenant
    scope mandatory (P0)."""

    def relevant_facts(
        self, *, tenant_id: str, query: str, k: int = 5
    ) -> tuple["RememberedFact", ...]: ...

    def remember_durable(
        self, *, tenant_id: str, facts: tuple["RememberedFact", ...]
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
HARD_GATES: tuple[str, ...] = (
    "walked_into_trap",
    "invented_precision",
    "confident_wrong",
    "memory_fabrication",
)
