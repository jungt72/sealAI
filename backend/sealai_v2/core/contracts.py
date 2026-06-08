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
    ) -> str: ...


class VerifierPromptAssembler(Protocol):
    """Structural type for the L3 verifier prompt assembler (implemented by ``prompts.assembler``).

    Kept as a Protocol so ``core`` does not import ``prompts``. ``traps`` is a list of plain dicts
    (id/trigger/wrong/correct/gates) — the catalog is rendered as delimited DATA, never as logic."""

    def verifier_system_prompt(self, *, traps: list[dict]) -> str: ...


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
    text: str
    quelle: str


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

    trap_id: str
    gate: str  # one of HARD_GATES
    review_state: str  # "reviewed" | "draft"
    evidence: str  # short quote/paraphrase of the offending claim in the draft


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

# The three hard gates (Schranken) — quota must reach 100%.
HARD_GATES: tuple[str, ...] = (
    "walked_into_trap",
    "invented_precision",
    "confident_wrong",
)
