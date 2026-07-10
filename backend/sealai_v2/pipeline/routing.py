"""Phase 2B (LangGraph-suitability audit) — conservative route classification foundation.

Core safety doctrine (owner-set, non-negotiable): the router may only make the system MORE
conservative, never less. If there is any doubt, route to the full engineering pipeline. This is
implemented as a two-stage gate, not a single classifier call:

  Stage 1 (deterministic, near-zero cost, no LLM): a fixed set of already-tested extractors + small
  regex checks for ANY engineering signal (a designation/dimension, a recognised failure symptom, a
  known material+medium pairing, a bare engineering value+unit, RFQ/leakage/case language, a
  comparative-suitability claim about a material, or simply a non-empty accumulated case-state). A
  SINGLE hit forces the full pipeline — engineering_case, leakage_troubleshooting,
  material_comparison, or rfq_manufacturer_brief — with IDENTICAL behavior to today (no cheaper
  bypass, ever).

  Stage 2 (only reached when Stage 1 found NOTHING): the already-running, already-paid-for
  `understand()` soft intent may pick a cheap route (smalltalk_navigation,
  general_sealing_knowledge, material_knowledge). Any intent this stage cannot confidently place —
  missing, "unklar", or (defensively) "fallarbeit" despite zero Stage-1 signals — maps to
  unsupported_or_ambiguous, which ALSO forces the full pipeline. Doubt never downgrades.

Deliberate design choice: a BARE material or medium name mention (e.g. "was ist PTFE?") is, on its
own, exactly the profile of a genuine knowledge question — it must NOT force the full pipeline, or
the general_sealing_knowledge/material_knowledge routes could never fire. Only the COMBINATION of a
material AND a medium in the same message (a described operating situation, not a definition
request), or comparative-suitability language about a material (the L3 trap catalog's sharpest
edge — comparative ranking claims), forces the full path on material/medium grounds alone.

This module is pure (no I/O, no LLM calls of its own) and safe to unit-test with just a question
string. Wiring it into `pipeline.Pipeline.run()` is a separate, explicitly flag-gated concern — see
`config.settings.Settings.route_optimization_enabled`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from sealai_v2.core.contracts import Intent
from sealai_v2.core.medium_extract import extract_medium_facts
from sealai_v2.core.seal_spec_extract import extract_seal_spec
from sealai_v2.pipeline.stages import is_alternativen_request


class RouteName(str, Enum):
    SMALLTALK_NAVIGATION = "smalltalk_navigation"
    GENERAL_SEALING_KNOWLEDGE = "general_sealing_knowledge"
    MATERIAL_KNOWLEDGE = "material_knowledge"
    MATERIAL_COMPARISON = "material_comparison"
    ENGINEERING_CASE = "engineering_case"
    LEAKAGE_TROUBLESHOOTING = "leakage_troubleshooting"
    RFQ_MANUFACTURER_BRIEF = "rfq_manufacturer_brief"
    UNSUPPORTED_OR_AMBIGUOUS = "unsupported_or_ambiguous"


# Routes that MAY skip the full engineering path (subject to a lightweight deterministic guard —
# see pipeline.pipeline's wiring, which falls back to the EXISTING run_parametric_guard, never a
# new/invented mechanism). Every route not in this set is always forced_full_pipeline=True.
CHEAP_ROUTES: frozenset[RouteName] = frozenset(
    {
        RouteName.SMALLTALK_NAVIGATION,
        RouteName.GENERAL_SEALING_KNOWLEDGE,
        RouteName.MATERIAL_KNOWLEDGE,
    }
)


@dataclass(frozen=True)
class RouteDecision:
    route: RouteName
    reason: str
    confidence: float
    forced_full_pipeline: bool
    deterministic_signal_count: int


# --- Stage-1 signal regexes (deliberately explicit + narrow; each is independently testable) -----

# A bare engineering value with a unit (dimensions/speed/pressure/temperature), OUTSIDE the
# multi-number designation pattern decode_designation() already covers ("45x62x8"). This catches
# e.g. "Wellendurchmesser 45 mm" or "1500 U/min" stated alone.
_ENGINEERING_VALUE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:mm|cm|m/s|rpm|u/min|1/min|bar|mbar|psi|kpa|mpa|°c|°f|k)\b"
    r"|Ø\s*\d+"
    r"|\bpv[- ]?wert\b",
    re.IGNORECASE,
)

_COMPRESSION_RE = re.compile(
    r"\b(verpressung|kompression|übermaß|uebermass|presssitz|squeeze|interference)\b",
    re.IGNORECASE,
)

_RFQ_RE = re.compile(
    r"\b(rfq|anfrage|anfragen|ausschreibung|herstellerbrief|angebot\s+anfordern|angebot\s+einholen)\b",
    re.IGNORECASE,
)

_LEAKAGE_RE = re.compile(
    r"\b(leck\w*|tropft\w*|undicht\w*|ausgefallen|defekt\w*|schadensbild|versagt|kaputt|schaden\w*|"
    r"riss\w*|rissbildung)\b",
    re.IGNORECASE,
)

_CASE_LANGUAGE_RE = re.compile(
    r"\b(ersatz(?:teil)?|ersetzen|auslegen|auslegung|vorqualifizierung|"
    r"welche[rs]?\s+dichtung|dichtungsfall|ich\s+suche\s+(?:einen?|eine))\b",
    re.IGNORECASE,
)

# Kinematic/calc-relevant terms that name a value WITHOUT stating it numerically yet (e.g. asking
# to compute or reference Umfangsgeschwindigkeit) — the deterministic calc kernel (core/calc/) is
# exactly what would need to run for these, so absence of a bare number must not read as "safe".
_CALC_TERM_RE = re.compile(
    r"\b(umfangsgeschwindigkeit|pv[- ]?relevant\w*|schnelldrehend\w*|kaltfluss)\b",
    re.IGNORECASE,
)

# Chemical-resistance / overconfident-suitability-claim language — the Gegencheck/L3 trap
# catalog's core concern (a user's confident-but-unverified material choice).
_RESISTANCE_CLAIM_RE = re.compile(
    r"\b(best[aä]ndig\s+gegen|resistent\s+gegen|h[aä]lt\s+(?:\w+\s+){0,2}aus|aush[aä]lt|"
    r"geeignet\s+f[uü]r|ungeeignet)\b",
    re.IGNORECASE,
)

_COMPARISON_RE = re.compile(
    r"\b(vergleich\w*|unterschied\w*|besser|schlechter|\bvs\.?\b|\bversus\b|gegenüber|gegenueber|vor-\s*und\s*nachteile)\b",
    re.IGNORECASE,
)

# Suitability/recommendation-request language: "passt das?", "reicht das?", "ich brauche eine
# Dichtung fuer...", "welche X nehme ich/empfiehlst du" — the profile of a real (if under-
# specified) application question, not a definitional knowledge question. Broader than
# _CASE_LANGUAGE_RE on purpose (that regex catches explicit "Ersatz/Auslegung" vocabulary; this
# one catches the much more common "is this okay / what should I use" phrasing that dominates
# real intake messages, per a stress-test against the eval seed cases).
_SUITABILITY_QUESTION_RE = re.compile(
    r"\b(passt\s+(?:\w+\s+){0,2}(?:das|dazu|hierzu|hierf[uü]r)|reicht\s+das|"
    r"ist\s+das\s+(?:so\s+)?(?:in\s+)?ordnung|"
    r"k[oö]nnen\s+sie\s+best[aä]tigen|"
    r"(?:ich\s+brauche|brauche\s+ich|ich\s+ben[oö]tige|ben[oö]tige\s+ich)|"
    r"welche[rns]?\s+\w+\s+(?:nehme\s+ich|soll\s+ich|empfiehlst\s+du|empfehlst\s+du)|"
    r"kannst\s+du\s+mir\s+sagen|worauf\s+sollte\s+ich|"
    r"empfiehl\s+mir|empfehl\s+mir|was\s+nehme\s+ich|was\s+ist\s+da\s+los)\b",
    re.IGNORECASE,
)

# Meta/directive/injection-shaped language. Deliberately NOT presented as a complete defense —
# no fixed keyword list can be one (an adversarial input can always be rephrased around it). The
# PRIMARY defense against prompt injection / exfiltration is unchanged and fully unaffected by
# this router: the untrusted-content quarantine + the L3 trap catalog + output_guard keep running
# on every route this signal happens to miss. This check exists only to bias routing AWAY from a
# cheap bypass whenever a message looks even remotely like a directive to the system rather than a
# genuine domain question — a cheap, high-value first line, not the last line.
_META_INSTRUCTION_RE = re.compile(
    r"\b(ignorier\w*|system[- ]?prompt|systemanweisung|wissensbasis|"
    r"deine\s+regeln|deine\s+vorsichts\w*|andere\s+nutzer|w[oö]rtlich\s+aus|"
    r"ohne\s+auslassung|vollst[aä]ndig\w*\s+(?:system|prompt|instrukt\w*))\b",
    re.IGNORECASE,
)

# A short, explicit, self-contained material-name list (deliberately NOT importing
# seal_spec_extract's private _MATERIAL_PATTERNS — this module stays independently auditable).
# Used only for the material_comparison forcing check and the material_knowledge Stage-2 label —
# NEVER as a standalone forcing signal (see module docstring: a bare mention is a knowledge
# question, not an engineering case).
_MATERIAL_NAME_RE = re.compile(
    r"\b(ptfe|fkm|viton|epdm|nbr|hnbr|ffkm|vmq|silikon|silicone|pu|tpu|au|eu|pom|peek)\b",
    re.IGNORECASE,
)

_SMALLTALK_RE = re.compile(
    r"^\s*(?:hallo|hi|hey|guten\s+(?:morgen|tag|abend)|danke|vielen\s+dank|"
    r"tsch(?:u|ü)ss|auf\s+wiedersehen|was\s+kannst\s+du|hilfe)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

_SMALLTALK_PREFIX_RE = re.compile(
    r"^\s*(?:hallo|hi|hey|guten\s+(?:morgen|tag|abend)|danke|vielen\s+dank|"
    r"tsch(?:u|ü)ss|auf\s+wiedersehen)\b",
    re.IGNORECASE,
)


def _is_smalltalk_shape(question: str) -> bool:
    """Recognize a short social turn after engineering/security signals were ruled out.

    The exact-match regex remains the narrow fast path. The prefix path covers natural courtesy
    such as "Hallo, schön dass es euch gibt" without turning a greeting-prefixed engineering case
    into a cheap route: callers invoke this only after ``detect_engineering_signals`` returned empty.
    A length cap keeps open-ended requests on the conservative ambiguous route.
    """
    text = (question or "").strip()
    return bool(
        _SMALLTALK_RE.fullmatch(text)
        or (len(text) <= 160 and _SMALLTALK_PREFIX_RE.match(text))
    )


_DOMAIN_KNOWLEDGE_RE = re.compile(
    r"\b(dichtung(?:stechnik)?|dichtungsart|wellendichtring|radialwellendicht(?:ung|ring)|rwdr|"
    r"o-?ring|hydraulikdichtung|werkstoff|elastomer|thermoplast|nut|dichtlippe|"
    r"gegenlauffl(?:a|ä)che|schmierung|tribologie)\b",
    re.IGNORECASE,
)


def requests_calculation(question: str) -> bool:
    """Whether the user explicitly asks for a kernel quantity or calculation context."""
    return bool(_CALC_TERM_RE.search(question))


def detect_engineering_signals(
    question: str,
    *,
    case_state_nonempty: bool = False,
    decode_result: dict | None = None,
    diagnosis: dict | None = None,
    gegencheck_verdict: dict | None = None,
) -> tuple[str, ...]:
    """Every deterministic engineering signal that fires, by name. Pre-computed pipeline values
    (``decode_result``/``diagnosis``/``gegencheck_verdict``/``case_state_nonempty``) are accepted
    as optional hints so the caller (``Pipeline.run``) never pays for a second lookup/matrix query
    — they default to "absent" so this function is fully usable with just a question string in
    tests. A single positive signal is enough to force the full pipeline; the returned tuple's
    length is Stage 1's ``deterministic_signal_count``."""
    signals: list[str] = []
    if decode_result:
        signals.append("designation_or_dimensions")
    if diagnosis is not None:
        signals.append("recognized_failure_symptom")
    if gegencheck_verdict is not None:
        signals.append("material_and_medium_known")
    if case_state_nonempty:
        signals.append("case_state_nonempty")
    if is_alternativen_request(question):
        signals.append("manufacturer_alternatives_request")
    if _ENGINEERING_VALUE_RE.search(question):
        signals.append("engineering_value_with_unit")
    if _COMPRESSION_RE.search(question):
        signals.append("compression_or_interference_language")
    if _RFQ_RE.search(question):
        signals.append("rfq_language")
    if _LEAKAGE_RE.search(question):
        signals.append("leakage_or_failure_language")
    if _CASE_LANGUAGE_RE.search(question):
        signals.append("replacement_or_case_language")
    if _SUITABILITY_QUESTION_RE.search(question):
        signals.append("suitability_or_recommendation_request")
    if _META_INSTRUCTION_RE.search(question):
        signals.append("meta_or_directive_language")
    if requests_calculation(question):
        signals.append("kinematic_or_calc_term")
    if _RESISTANCE_CLAIM_RE.search(question):
        signals.append("resistance_or_suitability_claim")

    # Material/medium: a BARE mention of either alone is a knowledge-question profile ("was ist
    # PTFE?") and must NOT force the full pipeline — only the two TOGETHER in one message reflect
    # a described operating situation, not a definition request.
    has_material = bool(extract_seal_spec(question))
    has_medium = bool(extract_medium_facts(question))
    if has_material and has_medium:
        signals.append("material_and_medium_in_message")

    # Comparative-suitability language about a material is the L3 trap catalog's sharpest edge
    # (unauthorized comparative-ranking claims) — force the full path even with no medium stated.
    if _COMPARISON_RE.search(question) and (
        has_material or _MATERIAL_NAME_RE.search(question)
    ):
        signals.append("comparison_with_material")

    return tuple(signals)


def _forced_route(question: str, signals: tuple[str, ...]) -> RouteName:
    """Pick the most specific label among the always-full-pipeline routes. This choice is
    OBSERVABILITY ONLY in Phase 2B — every one of these routes gets byte-identical treatment
    (the current full pipeline); the label only makes telemetry/dashboards readable."""
    if _RFQ_RE.search(question):
        return RouteName.RFQ_MANUFACTURER_BRIEF
    if "recognized_failure_symptom" in signals or _LEAKAGE_RE.search(question):
        return RouteName.LEAKAGE_TROUBLESHOOTING
    if "comparison_with_material" in signals:
        return RouteName.MATERIAL_COMPARISON
    return RouteName.ENGINEERING_CASE


def classify_route(
    question: str,
    *,
    case_state_nonempty: bool = False,
    decode_result: dict | None = None,
    diagnosis: dict | None = None,
    gegencheck_verdict: dict | None = None,
    intent: Intent | None = None,
) -> RouteDecision:
    """The full two-stage gate. ``intent`` is the soft ``understand()`` classification — pass
    ``None`` when it is unavailable (understand disabled, or not yet resolved); doing so is always
    safe because a missing intent maps to ``unsupported_or_ambiguous`` (forced full pipeline)."""
    signals = detect_engineering_signals(
        question,
        case_state_nonempty=case_state_nonempty,
        decode_result=decode_result,
        diagnosis=diagnosis,
        gegencheck_verdict=gegencheck_verdict,
    )
    if signals:
        return RouteDecision(
            route=_forced_route(question, signals),
            reason=f"deterministic_signals:{','.join(signals)}",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=len(signals),
        )

    # Stage 2 — zero deterministic signals. Any doubt still forces the full pipeline.
    if intent is None:
        return RouteDecision(
            route=RouteName.UNSUPPORTED_OR_AMBIGUOUS,
            reason="no_intent_available",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=0,
        )

    if intent == Intent.GESPRAECH:
        return RouteDecision(
            route=RouteName.SMALLTALK_NAVIGATION,
            reason="intent=gespraech",
            confidence=0.7,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )

    if intent in (Intent.WISSENSFRAGE, Intent.FAKTFRAGE):
        route = (
            RouteName.MATERIAL_KNOWLEDGE
            if _MATERIAL_NAME_RE.search(question)
            else RouteName.GENERAL_SEALING_KNOWLEDGE
        )
        return RouteDecision(
            route=route,
            reason=f"intent={intent.value}",
            confidence=0.7,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )

    # FALLARBEIT despite zero Stage-1 signals (shouldn't normally happen — stay safe anyway) or
    # UNKLAR: doubt, not evidence of low risk.
    return RouteDecision(
        route=RouteName.UNSUPPORTED_OR_AMBIGUOUS,
        reason=f"intent={intent.value}_no_signals",
        confidence=1.0,
        forced_full_pipeline=True,
        deterministic_signal_count=0,
    )


def classify_route_deterministic(
    question: str,
    *,
    case_state_nonempty: bool = False,
    decode_result: dict | None = None,
    diagnosis: dict | None = None,
    gegencheck_verdict: dict | None = None,
) -> RouteDecision:
    """LLM-free production router.

    The same conservative engineering signals as :func:`classify_route` force
    the full path. Only narrow, explicit smalltalk and domain-knowledge shapes
    receive a cheaper route; anything else is ambiguous and therefore full.
    """
    signals = detect_engineering_signals(
        question,
        case_state_nonempty=case_state_nonempty,
        decode_result=decode_result,
        diagnosis=diagnosis,
        gegencheck_verdict=gegencheck_verdict,
    )
    if signals:
        return RouteDecision(
            route=_forced_route(question, signals),
            reason=f"deterministic_signals:{','.join(signals)}",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=len(signals),
        )
    if _is_smalltalk_shape(question):
        return RouteDecision(
            route=RouteName.SMALLTALK_NAVIGATION,
            reason="deterministic_smalltalk_shape",
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    if _MATERIAL_NAME_RE.search(question):
        return RouteDecision(
            route=RouteName.MATERIAL_KNOWLEDGE,
            reason="deterministic_material_knowledge_shape",
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    if _DOMAIN_KNOWLEDGE_RE.search(question):
        return RouteDecision(
            route=RouteName.GENERAL_SEALING_KNOWLEDGE,
            reason="deterministic_domain_knowledge_shape",
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    return RouteDecision(
        route=RouteName.UNSUPPORTED_OR_AMBIGUOUS,
        reason="no_deterministic_route",
        confidence=1.0,
        forced_full_pipeline=True,
        deterministic_signal_count=0,
    )
