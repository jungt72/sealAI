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
from sealai_v2.core.knowledge_answer import (
    detected_material_subjects,
    detected_seal_subjects,
    is_exact_material_alias,
)
from sealai_v2.core.medium_extract import extract_media, extract_medium_facts
from sealai_v2.core.seal_spec_extract import extract_seal_spec
from sealai_v2.core.text_match import query_tokens, tag_matches
from sealai_v2.pipeline.stages import is_alternativen_request


class RouteName(str, Enum):
    SMALLTALK_NAVIGATION = "smalltalk_navigation"
    # 2026-07-19 (case-intake fix): a first-turn message that expresses discussion/help INTENT
    # ("ich möchte eine Dichtungslösung besprechen") but carries ZERO technical content and zero
    # deterministic engineering signals. Distinct from smalltalk (no social/greeting shape) and
    # from general_sealing_knowledge (no actual knowledge REQUEST — see _KNOWLEDGE_REQUEST_RE).
    # Intentionally treated as a CHEAP route with the same narrow, content-free-output rationale
    # as smalltalk_navigation — see CHEAP_ROUTES below.
    CASE_INTAKE_INVITE = "case_intake_invite"
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
        RouteName.CASE_INTAKE_INVITE,
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


@dataclass(frozen=True)
class MaterialComparisonFollowup:
    """Typed resolution of a comparison reference in the current user turn.

    ``resolved`` is the only state allowed to reach retrieval or generation.
    ``needs_clarification`` is a deterministic abstention: it prevents a fluent
    but unrelated comparison when words such as "beide" have no provable pair.
    """

    resolved_question: str
    subjects: tuple[str, ...]
    subject_type: str = "material"
    status: str = "resolved"
    clarification: str = ""

    @property
    def needs_clarification(self) -> bool:
        return self.status != "resolved"


# --- Stage-1 signal regexes (deliberately explicit + narrow; each is independently testable) -----

# A bare engineering value with a unit (dimensions/speed/pressure/temperature), OUTSIDE the
# multi-number designation pattern decode_designation() already covers ("45x62x8"). This catches
# e.g. "Wellendurchmesser 45 mm" or "1500 U/min" stated alone.
_ENGINEERING_VALUE_RE = re.compile(
    # Natural German compound spelling frequently joins a value and unit with
    # a hyphen ("40-mm-Welle", "10-bar-Leitung").  Treat that spelling exactly
    # like "40 mm"; otherwise an unequivocal operating fact can fall through
    # to the semantic ambiguity route.
    r"\b\d+(?:[.,]\d+)?\s*[-–—]?\s*"
    r"(?:mm|cm|m/s|rpm|u/min|1/min|bar|mbar|psi|kpa|mpa|°c|°f|k|"
    r"grad(?:\s+(?:celsius|fahrenheit))?)\b"
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
    r"riss\w*|rissbildung|eingelaufen\w*|[oö]lfilm\w*|"
    r"(?:medium|[oö]l|wasser)\s+(?:verlieren|verliert|tritt\s+aus)|"
    r"nach\s+(?:dem\s+)?stillstand\s+(?:immer\s+)?nass)\b",
    re.IGNORECASE,
)

# A sealing target is not yet an observed failure.  Keep "Leckage null" and "maximale
# Dichtheit" on the design/selection path unless the same turn also contains an actual symptom.
# This prevents target language from being reframed as a troubleshooting incident.
_LEAKAGE_TARGET_RE = re.compile(
    r"\b(?:maximale\s+dichtheit|leckage\s*(?:[:=]\s*)?(?:null|0)|"
    r"leckagefrei\w*|(?:ziel|anforderung|wunsch)\w*[^?!.]{0,35}\bleckage)\b",
    re.IGNORECASE,
)
_OBSERVED_FAILURE_RE = re.compile(
    r"\b(?:leckt|tropft\w*|undicht\w*|ausgefallen|defekt\w*|versagt|kaputt|"
    r"schadensbild|schaden\w*|riss\w*|eingelaufen\w*|[oö]lfilm\w*|"
    r"(?:beobacht|mess|feststell)\w*[^?!.]{0,50}\bleckage\w*|"
    r"(?:jetzt|aktuell|derzeit)\b[^?!.]{0,50}\bleckage\w*|"
    r"leckage\w*[^?!.]{0,20}\b(?:von\s+)?(?:0*[1-9]\d*|0*[.,]\d*[1-9]\d*)\s*"
    r"(?:ml|l|cm[³3]|mm[³3])(?:\s*(?:/|pro)\s*(?:h|std\.?|minute|min))?|"
    r"(?:medium|[oö]l|wasser)\s+(?:verlieren|verliert|tritt\s+aus)|"
    r"nach\s+(?:dem\s+)?stillstand\s+(?:immer\s+)?nass)\b",
    re.IGNORECASE,
)
_OBSERVED_FAILURE_ASSERTION_RE = re.compile(
    r"\b(?:ist|sind|war|waren|wurde|wurden)\s+(?:st[aä]ndig\s+)?undicht\w*\b|"
    r"\b(?:zeigt|zeigen|hat|haben)\b[^?!.]{0,45}\b(?:riss\w*|schaden\w*|[oö]lfilm\w*)\b",
    re.IGNORECASE,
)

_CASE_LANGUAGE_RE = re.compile(
    r"\b(ersatz(?:teil)?|ersetzen|vorqualifizierung|"
    r"welche[rs]?\s+dichtung|dichtungsfall|ich\s+suche\s+(?:einen?|eine))\b",
    re.IGNORECASE,
)

# "Auslegung" is also a legitimate knowledge subject ("Erklaere die O-Ring-Auslegung"). Keep it
# separate from unequivocal case language so an explicit overview request can discuss engineering
# design axes without being mistaken for a concrete application. It still forces the full path for
# every non-overview shape and whenever a real case signal (value, damage, suitability, etc.) fires.
_DESIGN_TOPIC_RE = re.compile(r"\b(auslegen|auslegung)\b", re.IGNORECASE)

# Naming a kernel quantity is not itself a request to calculate it.  In particular, educational
# questions such as "warum fällt ein RWDR bei zu hoher Umfangsgeschwindigkeit aus?" must reach the
# knowledge/explanation path instead of being converted into an intake request for diameter and
# speed.  The calculation goal therefore requires a value-seeking speech act as well as the kernel
# term. Concrete dimensions and operating values remain independent deterministic route signals.
_CALC_QUANTITY_RE = re.compile(
    r"\b(?:umfangsgeschwindigkeit|pv[- ]?wert|verpressung)\b", re.IGNORECASE
)
_EXPLICIT_CALC_SPEECH_RE = re.compile(
    r"\b(?:berechne|berechnen|berechnung|rechne|ausrechnen|ermittle|bestimme|"
    r"wie\s+hoch|welchen\s+wert|was\s+betr(?:ä|ae)gt)\b",
    re.IGNORECASE,
)

# Goal language for a concrete engineering solution turn.  This is deliberately separate from
# route classification: it never chooses a route or authorises a claim.  It only tells the already
# selected engineering path that the user asked for a candidate/approach now, rather than for a
# generic intake interview.  Cover speech acts, not one benchmark sentence.
_SOLUTION_REQUEST_RE = re.compile(
    r"(?:\b(?:dichtungsl[öo]sung|l[öo]sungs(?:ansatz|weg|vorschlag)|"
    r"ansatz|ausleg(?:en|ung)|konzept|empfehl(?:en|ung))\b|"
    r"\bwelche(?:r|s)?\s+(?:dichtung|dichtungsart|bauform|werkstoff|material)\b|"
    r"\bwas\s+w(?:ä|ae)re\b[^?!.]{0,80}\bsinnvoll\b|"
    r"\bwas\s+ist\b[^?!.]{0,80}\boptimal\b|"
    r"\boptimale?\s+(?:dichtung|dichtungsl[öo]sung|l[öo]sung|auslegung)\b|"
    r"\bwie\s+w(?:ü|ue)rdest\s+du\b[^?!.]{0,80}\b(?:lösen|loesen|auslegen)\b|"
    r"\bworauf\s+sollte\s+ich\s+bei\s+(?:der|einer)\s+"
    r"(?:werkstoff|material)(?:wahl|auswahl)\s+achten\b|"
    r"\b(?:werkstoff|material)\b[^?!.]{0,50}\bpasst\b)",
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
    r"\b(vergleich\w*|unterschied\w*|unterscheid\w*|besser|schlechter|\bvs\.?\b|\bversus\b|gegenüber|gegenueber|vor-\s*und\s*nachteile)\b",
    re.IGNORECASE,
)

# Suitability/recommendation-request language: "passt das?", "reicht das?", "ich brauche eine
# Dichtung fuer...", "welche X nehme ich/empfiehlst du" — the profile of a real (if under-
# specified) application question, not a definitional knowledge question. Broader than
# _CASE_LANGUAGE_RE/_DESIGN_TOPIC_RE on purpose (those regexes catch explicit replacement/design
# vocabulary; this one catches the much more common "is this okay / what should I use" phrasing
# that dominates
# real intake messages, per a stress-test against the eval seed cases).
_SUITABILITY_QUESTION_RE = re.compile(
    r"\b(passt\s+(?:\w+\s+){0,2}(?:das|dazu|hierzu|hierf[uü]r)|reicht\s+das|"
    r"ist\s+das\s+(?:so\s+)?(?:in\s+)?ordnung|"
    r"k[oö]nnen\s+sie\s+best[aä]tigen|"
    r"(?:(?:ich|wir)\s+brauche\w*|(?:ich|wir)\s+ben[oö]tige\w*)\s+"
    r"(?:eine[nr]?\s+)?"
    r"(?:[\wäöüß/-]+\s+){0,2}(?:dichtung|o-?ring|rwdr|wellendichtring)|"
    r"(?:ich|wir)\s+(?:brauche\w*|ben[oö]tige\w*)\b[^?!.]{0,80}"
    r"\b(?:und|sowie)\s+(?:eine[nr]?\s+)?"
    r"(?:dichtung|o-?ring|rwdr|wellendichtring)|"
    r"(?:empfiehlst|empfehlst)\s+du\s+(?:mir\s+)?(?:eine[nr]?\s+)?"
    r"(?:[\wäöüß/-]+\s+){0,2}(?:dichtung|o-?ring|rwdr|wellendichtring)|"
    r"(?:dichtung\w*|wellendichtung\w*|gleitringdichtung\w*|wellendichtring\w*|"
    r"o-?ring\w*|rwdr|werkstoff\w*|material\w*|compound\w*)\b[^?!.]{0,100}"
    r"\b(?:kannst|k[oö]nntest|w[uü]rdest)\s+du\s+"
    r"(?:ihn|sie|den|die|das|diesen|diese)\b[^?!.]{0,30}"
    r"\b(?:empfehl\w*|ausleg\w*|ausw[aä]hl\w*|dimensionier\w*)|"
    r"welche[rns]?\s+(?:dichtung|o-?ring|rwdr|wellendichtring)\s+passt|"
    r"welche[rns]?\s+\w+\s+(?:nehme\s+ich|soll\s+ich|empfiehlst\s+du|empfehlst\s+du)|"
    r"welche[rns]?\s+(?:werkstoff|material|elastomer|compound)\b[^?!.]{0,80}"
    r"(?:geeignet|zu\s+pr[uü]fen|in\s+frage|w[aä]hlen)|"
    r"worauf\s+sollte\s+ich\s+bei\s+(?:der|einer)\s+"
    r"(?:(?:werkstoff|material)(?:wahl|auswahl)|auswahl|auslegung)\s+achten|"
    r"empfiehl\s+mir|empfehl\s+mir|was\s+nehme\s+ich|was\s+ist\s+da\s+los)\b",
    re.IGNORECASE,
)

# Adjacent component selection must not inherit an engineering route merely because the component
# sits on a pump, mixer or reactor.  Those machine nouns are useful domain anchors for seal cases,
# but an explicit motor/drive sizing request is a different professional discipline.  Keep the
# detector speech-act based so a question about how an already selected drive affects a seal can
# still enter the engineering path.
_MASCULINE_DRIVE_TARGET = (
    r"(?:elektromotor\w*|motor(?:auswahl|auslegung)?|"
    r"antrieb(?:sauswahl|sauslegung)?|getriebemotor\w*)"
)
_FEMININE_DRIVE_TARGET = r"(?:motorleistung|antriebsleistung)"
_DRIVE_SELECTION_TARGET = rf"(?:{_MASCULINE_DRIVE_TARGET}|{_FEMININE_DRIVE_TARGET})"
_SEAL_SELECTION_TARGET = (
    r"(?:dichtung\w*|wellendichtung\w*|wellendichtring\w*|o-?ring\w*|rwdr|"
    r"gleitringdichtung\w*|werkstoff\w*|material\w*|compound\w*)"
)
_DRIVE_SELECTION_VERB = (
    r"(?:empf(?:ehl|iehl)\w*|ausleg\w*|dimensionier\w*|ausw[aä]hl\w*)"
)
_SEAL_SELECTION_TARGET_RE = re.compile(rf"\b{_SEAL_SELECTION_TARGET}\b", re.IGNORECASE)
_MASCULINE_SEAL_TARGET_RE = re.compile(
    r"\b(?:wellendichtring(?:e|en|s)?|o-?ring(?:e|en|s)?|rwdr|"
    r"werkstoff(?:e|en|s|wahl|auswahl)?)\b"
    r"(?![-/](?:einkauf|lieferant|hersteller|beschaffung|handel))",
    re.IGNORECASE,
)
_FEMININE_SEAL_TARGET_RE = re.compile(
    r"\b(?:dichtung(?:en|s|sauswahl|sl[oö]sung)?|"
    r"wellendichtung(?:en|s)?|gleitringdichtung(?:en|s)?)\b"
    r"(?![-/](?:einkauf|lieferant|hersteller|beschaffung|handel))",
    re.IGNORECASE,
)
_MASCULINE_DRIVE_ANAPHORA_RE = re.compile(
    rf"\b(?P<drive>{_MASCULINE_DRIVE_TARGET})\b[^?!.]{{0,180}}"
    rf"\b(?:kannst|k[oö]nntest|w[uü]rdest)\s+du\s+"
    rf"(?P<pronoun>ihn|den|diesen)\b[^?!.]{{0,30}}\b{_DRIVE_SELECTION_VERB}\b",
    re.IGNORECASE,
)
_FEMININE_DRIVE_ANAPHORA_RE = re.compile(
    rf"\b(?P<drive>{_FEMININE_DRIVE_TARGET})\b[^?!.]{{0,180}}"
    rf"\b(?:kannst|k[oö]nntest|w[uü]rdest)\s+du\s+"
    rf"(?P<pronoun>sie|die|diese)\b[^?!.]{{0,30}}\b{_DRIVE_SELECTION_VERB}\b",
    re.IGNORECASE,
)
_ADJACENT_DRIVE_SELECTION_RE = re.compile(
    rf"(?:"
    # Direct wh-object: the requested object itself is a drive target.  A preceding "welchen
    # Einfluss" therefore cannot match because "Einfluss" is not silently skipped.
    rf"\bwelch\w*\s+(?:[\wäöüß-]+\s+){{0,1}}{_DRIVE_SELECTION_TARGET}\b"
    rf"[^?!.]{{0,100}}\b(?:soll\w*\s+(?:ich|wir)\b[^?!.]{{0,40}}"
    rf"(?:nehm\w*|w[aä]hl\w*|verwend\w*)|{_DRIVE_SELECTION_VERB}|"
    rf"(?:ich|wir)\b[^?!.]{{0,60}}(?:nehm\w*|w[aä]hl\w*|verwend\w*)\s+"
    rf"(?:soll\w*|kann\w*)|brauch\w*|ben[oö]tig\w*)\b|"
    # Direct polite object: "den Antrieb ... auslegen".  The target must immediately follow the
    # request frame, so "eine Dichtung für den Antrieb" is not reinterpreted as drive selection.
    rf"\b(?:kannst|k[oö]nntest|w[uü]rdest)\s+du\s+(?:mir\s+)?"
    rf"(?:(?:den|die|das|einen|eine|unseren|diesen|diese)\s+)?"
    rf"(?:[\wäöüß-]+\s+){{0,1}}"
    rf"{_DRIVE_SELECTION_TARGET}\b"
    rf"(?![^?!.]{{0,80}}\b{_SEAL_SELECTION_TARGET}\b)[^?!.]{{0,80}}"
    rf"\b{_DRIVE_SELECTION_VERB}\b|"
    # Noun-first polite anaphora with grammatical agreement.  This preserves genuine drive
    # requests such as "Motor ..., kannst du ihn auslegen?" without reintroducing the false
    # binding in "Dichtung für den Motor, kannst du sie auslegen?".
    rf"\b{_MASCULINE_DRIVE_TARGET}\b[^?!.]{{0,180}}"
    rf"\b(?:kannst|k[oö]nntest|w[uü]rdest)\s+du\s+"
    rf"(?:ihn|den|diesen)\b[^?!.]{{0,30}}\b{_DRIVE_SELECTION_VERB}\b|"
    rf"\b{_FEMININE_DRIVE_TARGET}\b[^?!.]{{0,180}}"
    rf"\b(?:kannst|k[oö]nntest|w[uü]rdest)\s+du\s+"
    rf"(?:sie|die|diese)\b[^?!.]{{0,30}}\b{_DRIVE_SELECTION_VERB}\b|"
    # Declarative/telegraphic target followed by a sizing verb.  A competing seal-selection noun
    # between the drive and verb invalidates the hard boundary and leaves the normal router in
    # control (e.g. "Antrieb 1500 U/min, welche Dichtung empfiehlst du?").
    rf"\b{_DRIVE_SELECTION_TARGET}\b"
    rf"(?![^?!.]{{0,80}}\b{_SEAL_SELECTION_TARGET}\b)"
    # A new polite frame after the noun has its own object binding.  In "Dichtung für den Motor,
    # kannst du sie auslegen?", feminine "sie" refers to Dichtung, not Motor.  Genuine direct
    # polite drive requests are already covered by the dedicated branch above.
    rf"(?![^?!.]{{0,80}}\b(?:kannst|k[oö]nntest|w[uü]rdest)\s+du\b)"
    rf"[^?!.]{{0,80}}\b{_DRIVE_SELECTION_VERB}\b|"
    # First-person need with the drive as the direct object.  "Wir brauchen eine Dichtung für den
    # Motor" does not match because the drive is not adjacent to the need verb.
    rf"\b(?:ich|wir)\s+(?:brauch\w*|ben[oö]tig\w*)\s+"
    rf"(?:(?:den|die|das|einen|eine)\s+)?(?:[\wäöüß-]+\s+){{0,1}}"
    rf"{_DRIVE_SELECTION_TARGET}\b"
    rf")",
    re.IGNORECASE,
)


def is_ambiguous_drive_seal_anaphora(question: str) -> bool:
    """Return whether a drive-selection pronoun has a same-gender sealing antecedent.

    German anaphora can remain structurally ambiguous even after distance, word order and
    prepositions are considered.  This boundary therefore does not guess.  A competing sealing
    noun anywhere before the pronoun in the same sentence produces one deterministic
    clarification; it never exposes motor sizing to free generation or rejects a presumed seal
    request.
    """

    text = question or ""
    for request_re, seal_re in (
        (_MASCULINE_DRIVE_ANAPHORA_RE, _MASCULINE_SEAL_TARGET_RE),
        (_FEMININE_DRIVE_ANAPHORA_RE, _FEMININE_SEAL_TARGET_RE),
    ):
        for request_match in request_re.finditer(text):
            drive_start = request_match.start("drive")
            sentence_start = (
                max(
                    text.rfind(".", 0, drive_start),
                    text.rfind("!", 0, drive_start),
                    text.rfind("?", 0, drive_start),
                    text.rfind(";", 0, drive_start),
                )
                + 1
            )
            antecedent_region = text[sentence_start : request_match.start("pronoun")]
            if seal_re.search(antecedent_region):
                return True
    return False


def is_adjacent_out_of_scope_request(question: str) -> bool:
    """Return whether the current speech act requests drive/component selection, not seal work."""

    text = question or ""
    return bool(_ADJACENT_DRIVE_SELECTION_RE.search(text))


def has_sealing_target(question: str) -> bool:
    """Return whether a drive-boundary turn also names a supported sealing target.

    This deliberately detects the object, not an exhaustive list of request verbs.  A mixed turn
    is decomposed by the deterministic boundary renderer: the drive part is refused while the
    sealing part is preserved as governed case work.  Even a contextual seal mention therefore
    receives a harmless sealing bridge instead of exposing motor selection to free generation.
    """

    return bool(_SEAL_SELECTION_TARGET_RE.search(question or ""))


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
    r"\b(ptfe|fkm|viton|epdm|nbr|hnbr|ffkm|vmq|silikon|silicone|pu|tpu|pom|peek|"
    r"elastomer\w*|kautschuk\w*|thermoplast\w*)\b",
    re.IGNORECASE,
)

_SMALLTALK_RE = re.compile(
    r"^\s*(?:hallo|hi|hey|moin|servus|guten\s+(?:morgen|tag|abend)|danke|vielen\s+dank|"
    r"tsch(?:u|ü)ss|auf\s+wiedersehen|was\s+kannst\s+du|hilfe)\s*[!.?]*\s*$",
    re.IGNORECASE,
)

_SMALLTALK_PREFIX_RE = re.compile(
    r"^\s*(?:hallo|hi|hey|moin|servus|guten\s+(?:morgen|tag|abend)|danke|vielen\s+dank|"
    r"tsch(?:u|ü)ss|auf\s+wiedersehen)\b",
    re.IGNORECASE,
)

# A greeting is only smalltalk when the REST of the message is social as well. Previously every
# greeting-prefixed message below 160 characters was accepted, so "Guten Morgen, Details zu NBR"
# silently lost its technical intent. Unknown residual content now fails conservative (full path)
# instead of being swallowed by a social prefix.
_SOCIAL_REMAINDER_RE = re.compile(
    r"^\s*[,!?.-]*\s*(?:"
    r"(?:und\s+)?guten\s+(?:morgen|tag|abend)|"
    r"(?:dir|euch)|"
    r"f(?:ue|ü)r\s+die\s+hilfe|"
    r"wie\s+geht(?:'s|\s+es)(?:\s+(?:dir|euch))?|"
    r"sch[oö]n,?\s+dass\s+es\s+(?:dich|euch)\s+gibt|"
    r"ich\s+hoffe,?\s+es\s+geht\s+(?:dir|euch)\s+gut|"
    r"freut\s+mich(?:,?\s+(?:dich|euch)\s+kennenzulernen)?|"
    r"danke(?:\s+dir|\s+euch)?|"
    r"(?:einen\s+)?sch[oö]nen\s+(?:morgen|tag|abend)"
    r")\s*[!.?]*\s*$",
    re.IGNORECASE,
)

_CONVERSATION_META_RE = re.compile(
    r"^\s*(?:ich\s+habe\s+\d+\s+fragen(?:\s+an\s+dich)?|"
    r"ich\s+h[aä]tte\s+eine\s+frage|kannst\s+du\s+mir\s+helfen)\s*[!.?]*\s*$",
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
    if _SMALLTALK_RE.fullmatch(text) or _CONVERSATION_META_RE.fullmatch(text):
        return True
    prefix = _SMALLTALK_PREFIX_RE.match(text)
    if not prefix:
        return False
    return bool(_SOCIAL_REMAINDER_RE.fullmatch(text[prefix.end() :]))


_DOMAIN_KNOWLEDGE_RE = re.compile(
    r"\b(dichtung(?:en|stechnik)?|dichtungs\w*|dichtungsart|dichtungsmedium|"
    r"hydraulikmedium|medium|medien|fluid|betriebsstoff|dichtstelle|"
    r"wellendichtung|wellendichtring|radialwellendicht(?:ung|ring)|rwdr|"
    r"o-?ring(?:e|s)?|gleitringdichtung|gleitdichtung|glrd|mechanical\s+seal|hydraulikdichtung|"
    r"werkstoff\w*|material\w*|compound\w*|elastomer|thermoplast|nut|dichtlippe|"
    r"gegenlauffl(?:a|ä)che|schmierung|tribologie)\b",
    re.IGNORECASE,
)

_KNOWLEDGE_REQUEST_RE = re.compile(
    r"\b(?:"
    r"was\s+(?:ist|sind|bedeutet)|"
    r"was\s+zeichnet\b.{0,80}\baus\b|"
    r"erkl(?:a|ä|ae)r\w*|beschreib\w*|definier\w*|"
    r"definition|grundlagen|details|infos?|informationen|[uü]berblick|eigenschaften|"
    r"wie\s+(?:funktioniert|funktionieren|muss|müssen|muessen|sollte|sollten|"
    r"l[aä]sst|laesst|wird|werden|kann|k[oö]nnen)|"
    r"warum|weshalb|wodurch|wof[uü]r|wann\s+(?:wird|werden|verwendet|setzt)|"
    r"welche\w*\s+(?:auswirkung\w*|einfluss)\s+hat\b|"
    r"wie\s+(?:beeinfluss\w*|wirkt\s+sich)\b|"
    r"welche\w*\s+(?:arten|typen|eigenschaften|vorteile|nachteile)\b|"
    r"welche\w*\s+(?:werkstoff)?klasse\s+(?:ist|sind)\b|"
    r"welche\w*\s+(?:[\wäöüß/-]+\s+){0,3}gibt\s+es\b|"
    r"(?:gib|gebe)\s+mir\s+(?:bitte\s+)?(?:infos?|informationen|details|einen?\s+[uü]berblick)|"
    r"(?:kannst|k[oö]nntest|w[uü]rdest)\s+du\s+(?:mir\s+)?(?:erkl(?:a|ä|ae)ren|sagen|zeigen)|"
    r"ist\s+(?:ein\w*\s+)?[\wäöüß/-]+\s+ein\w*\b|"
    r"ist\s+[\wäöüß/-]+\s+(?:gegen|in)\s+(?:[\wäöüß/-]+\s+){0,5}(?:best[aä]ndig|resistent)\b|"
    r"(?:jetzt|nun)?\s*bitte\s+(?:[uü]ber|ueber)\s+"
    r")",
    re.IGNORECASE,
)

_BARE_MATERIAL_FAMILY_DEFINITION_RE = re.compile(
    r"^\s*(?:wof[uü]r\s+steht|was\s+bedeutet|was\s+hei[sß]t)\s+"
    r"(?:(?:die|der|das)\s+)?"
    r"(?:(?:(?:werkstoff|material)[- ]?(?:bezeichnung|k[uü]rzel)|"
    r"abk[uü]rzung|k[uü]rzel)\s+)?"
    r"(?P<family>[\wäöüß-]+)\s*[?!.]*\s*$",
    re.IGNORECASE,
)

_CASE_GUIDANCE_REQUEST_RE = re.compile(
    r"\b(?:was|welche\w*)\s+(?:angaben|daten|informationen)?\s*"
    r"(?:brauchst|ben[oö]tigst)\s+du\b",
    re.IGNORECASE,
)

_CASE_PROCESS_GUIDANCE_RE = re.compile(
    r"\b(?:wie\s+(?:gehen\s+wir|sollen\s+wir|starte\s+ich|fange\s+ich)\s+"
    r"(?:dabei|damit|vor|an)|wo\s+(?:fangen\s+wir|soll\s+ich)\s+"
    r"(?:(?:am\s+besten|zuerst)\s+)?(?:an|starten))\b",
    re.IGNORECASE,
)

_CASE_COLLABORATIVE_START_RE = re.compile(
    r"\b(?:"
    r"(?:neue[rs]?\s+)?dichtungsfall\s+(?:gemeinsam\s+)?strukturieren|"
    r"(?:neue[rs]?\s+)?dichtungsfall\b.{0,80}\b(?:informationen|angaben|daten)\s+relevant|"
    r"dichtungsl[oö]sung\b.{0,80}\b(?:was\s+du\s+(?:wissen|brauchen)|was\s+relevant)"
    r")\b",
    re.IGNORECASE,
)

_CASE_APPLICATION_DETAIL_RE = re.compile(
    r"\b(?:pumpe|r[uü]hrwerk|mischer|welle|stange|geh[aä]use|motor|maschine|anlage|"
    r"getriebe|ventil|zylinder|flansch|armatur|kompressor|turbine|spindel|"
    r"reaktor|bioreaktor)\w*\b",
    re.IGNORECASE,
)

_CASE_MOTION_DETAIL_RE = re.compile(
    r"\b(rotierend\w*|oszillierend\w*|hubbeweg\w*|drehend\w*|wechselnde\w*\s+drehzahl)\b",
    re.IGNORECASE,
)

_SAFETY_CASE_RE = re.compile(
    r"\b(atex|sauerstoff|explosionsschutz|ex[- ]?bereich|wasserstoff|pharma|sip)\b",
    re.IGNORECASE,
)

_MANUFACTURER_IDENTIFIER_RE = re.compile(
    r"\b(?:genaue[nr]?\s+)?(?:compound|mischungs?|werkstoff)[- ]?(?:nummer|nr\.?|"
    r"bezeichnung|code)\b|\b(?:hersteller|lieferant)\w*[^?!.]{0,60}\b(?:compound|"
    r"mischung|werkstoff)\b",
    re.IGNORECASE,
)

_CASE_DEVELOPMENT_RE = re.compile(
    r"\bich\s+(?:m[oö]chte|will|w[uü]rde\s+gern|plane)\s+"
    r"(?:[\wäöüß/-]+\s+){0,8}"
    r"(?:entwickeln|planen|konzipieren|erarbeiten|erstellen|ausw[aä]hlen|"
    r"auswaehlen|auslegen|finden)\b",
    re.IGNORECASE,
)

# 2026-07-19 (case-intake fix): a pure discussion/help-INTENT opener — "ich möchte eine
# Dichtungslösung besprechen", "ich brauche Hilfe bei ...", "können wir über ... sprechen", "ich
# habe eine (Dichtungs-)Frage", "ich habe ein Dichtungsproblem". Deliberately narrow: only phrasing
# that expresses INTENT to discuss/get help, never a phrasing that itself asks a question or states
# a fact (that stays on _KNOWLEDGE_REQUEST_RE / the deterministic engineering signals, both checked
# independently at the call site — this regex alone never decides a route).
_CASE_OPENING_RE = re.compile(
    r"\b(?:"
    r"ich\s+m[oö]chte\s+(?:[\wäöüß/-]+\s+){0,6}(?:besprechen|bereden|reden|sprechen)|"
    r"ich\s+m[oö]chte\s+(?:[\wäöüß/-]+\s+){0,8}"
    r"(?:entwickeln|planen|konzipieren|erarbeiten|erstellen|ausw[aä]hlen|auswaehlen|auslegen|finden)|"
    r"ich\s+(?:will|w[uü]rde\s+gern|plane)\s+(?:[\wäöüß/-]+\s+){0,8}"
    r"(?:entwickeln|planen|konzipieren|erarbeiten|erstellen|ausw[aä]hlen|auswaehlen|auslegen|finden)|"
    r"ich\s+(?:brauche|ben[oö]tige)\s+hilfe\s+(?:bei|mit)|"
    r"k[oö]nnen\s+wir\s+(?:[\wäöüß/-]+\s+){0,6}(?:reden|sprechen)|"
    r"ich\s+habe\s+eine[ns]?\s+(?:dichtungs)?frage|"
    r"ich\s+habe\s+ein\s+dichtungsproblem|"
    r"(?:was|welche\w*)\s+(?:angaben|daten|informationen)?\s*"
    r"(?:brauchst|ben[oö]tigst)\s+du\s+(?:von\s+mir|daf[uü]r|dazu|noch)?|"
    r"wie\s+(?:gehen\s+wir|sollen\s+wir|starte\s+ich|fange\s+ich)\s+"
    r"(?:dabei|damit|vor|an)"
    r")\b",
    re.IGNORECASE,
)

# CASE_INTAKE_INVITE feeds the matched question straight to an L3-bypassed LLM call (see
# pipeline.py's case_intake_prompt_active/skip_l3_for_route) because its OUTPUT is a fully static,
# content-free invitation — but that reasoning only holds if the INPUT is genuinely just the
# opening phrase. _CASE_OPENING_RE.search() alone would also match inside an arbitrarily long
# message, letting unrelated (and unverified, since L3 is skipped) trailing content ride along
# under the guise of a harmless opener. Mirror _is_smalltalk_shape's discipline: cap the overall
# length and require the matched phrase to cover all but a short lead-in/trail-off of the message,
# so there is no room to smuggle a second instruction next to the trigger phrase. Anything wider
# falls through to the existing, more conservative branches below (domain-knowledge or
# ambiguous/full-pipeline) exactly as before this change.
_CASE_OPENING_MAX_LEN = 200
_CASE_OPENING_SURROUNDING_MAX_LEN = 65


def _is_case_opening_shape(question: str) -> bool:
    text = (question or "").strip()
    if not text or len(text) > _CASE_OPENING_MAX_LEN:
        return False
    match = _CASE_OPENING_RE.search(text)
    if not match:
        return False
    surrounding = len(text[: match.start()]) + len(text[match.end() :])
    return surrounding <= _CASE_OPENING_SURROUNDING_MAX_LEN


def has_explicit_knowledge_request(question: str) -> bool:
    """Return whether the utterance actually asks to learn or retrieve information.

    A sealing-domain noun is an entity, not a speech act.  Keeping this predicate separate makes
    that boundary auditable and reusable by deterministic routing, semantic-policy validation and
    regression tests.  Guidance requests such as ``was brauchst du von mir?`` intentionally do not
    match: they initiate/continue case work instead of requesting a Fachkarten answer.
    """

    text = question or ""
    guidance = _CASE_GUIDANCE_REQUEST_RE.search(text)
    if guidance:
        # "Welche Informationen brauchst du?" contains the lexical noun ``Informationen`` but is
        # not a knowledge request.  Remove only that guidance clause before testing the remainder,
        # so a genuine mixed turn ("Erkläre PTFE; was brauchst du für den Fall?") retains both acts.
        text = text[: guidance.start()] + text[guidance.end() :]
    collaborative_start = _CASE_COLLABORATIVE_START_RE.search(text)
    if collaborative_start:
        text = text[: collaborative_start.start()] + text[collaborative_start.end() :]
    return bool(_KNOWLEDGE_REQUEST_RE.search(text))


def _is_exact_named_material_family(
    family: str, material_terms: tuple[str, ...] = ()
) -> bool:
    """Recognise one exact reviewed family token, never a prefix or grade code."""

    normalized = (family or "").strip().casefold()
    return bool(
        is_exact_material_alias(family)
        or any(normalized == (term or "").strip().casefold() for term in material_terms)
    )


def requests_case_guidance(question: str) -> bool:
    """Whether the user asks how to start/continue the governed case workflow."""

    text = question or ""
    return bool(
        _CASE_GUIDANCE_REQUEST_RE.search(text)
        or _CASE_PROCESS_GUIDANCE_RE.search(text)
        or _CASE_COLLABORATIVE_START_RE.search(text)
    )


# A possessive/deictic reference makes even an explanation-shaped question case-bound: "Erklaere
# meine Auslegung" is not the same route as "Erklaere die Auslegung". Numeric operating values,
# failures, suitability requests and other hard signals are handled independently below.
_CONCRETE_CASE_REFERENCE_RE = re.compile(
    r"\b(mein(?:e|er|es|en|em)?|unser(?:e|er|es|en|em)?|bei\s+uns|"
    r"in\s+(?:meiner|unserer)\s+(?:anlage|maschine|pumpe|anwendung)|"
    r"f[uü]r\s+(?:meine|meinen|meiner|unsere|unseren|unserer)\s+"
    r"(?:anlage|maschine|pumpe|anwendung)|"
    r"(?:dieser|diese|dieses|vorliegende[rs]?)\s+(?:fall|anwendung|anlage|maschine|pumpe))\b",
    re.IGNORECASE,
)

_SHORT_MATERIAL_CONTEXT_RE = re.compile(
    r"\b(werkstoff|material|elastomer|kautschuk|gummi|dichtung|o-?ring(?:e|s)?|"
    r"details|informationen|[uü]berblick|eigenschaften)\b",
    re.IGNORECASE,
)


def requests_calculation(question: str) -> bool:
    """Whether the user explicitly asks for a kernel quantity or calculation context."""
    return bool(
        _CALC_QUANTITY_RE.search(question or "")
        and _EXPLICIT_CALC_SPEECH_RE.search(question or "")
    )


_CONTEXTUAL_CALC_REFERENCE_RE = re.compile(
    r"\b(?:sie|ihn|ihm|er|der\s+wert|das\s+ergebnis|jetzt|genau)\b",
    re.IGNORECASE,
)
_CALC_PARAMETER_REPLY_RE = re.compile(
    r"^\s*[+-]?\d+(?:[.,]\d+)?\s*(?:mm|cm|m|bar|u\s*/\s*min|1\s*/\s*min|rpm)?"
    r"(?:\s*(?:und|,|;|/)\s*[+-]?\d+(?:[.,]\d+)?\s*"
    r"(?:mm|cm|m|bar|u\s*/\s*min|1\s*/\s*min|rpm)?)*\s*[.!]?\s*$",
    re.IGNORECASE,
)


def resolve_calculation_followup(
    question: str, previous_turns: tuple[object, ...]
) -> str | None:
    """Resolve an explicit value follow-up to one recent user-authored kernel quantity.

    The resolver restores only the *name* of a reviewed calculation.  It never copies assistant
    text, invents a unit or supplies a numeric input.  Ambiguous histories therefore stay
    unresolved and continue through the ordinary clarification path.
    """

    text = (question or "").strip()
    if requests_calculation(text):
        return None
    explicit_reference = bool(
        _EXPLICIT_CALC_SPEECH_RE.search(text)
        and _CONTEXTUAL_CALC_REFERENCE_RE.search(text)
    )
    parameter_followup = bool(_CALC_PARAMETER_REPLY_RE.fullmatch(text))
    if not (explicit_reference or parameter_followup):
        return None

    quantities: list[str] = []
    inspected = 0
    for turn in reversed(previous_turns):
        if getattr(turn, "role", None) != "user":
            continue
        inspected += 1
        prior_text = str(getattr(turn, "text", "") or "")
        if not requests_calculation(prior_text):
            if inspected >= 4:
                break
            continue
        for match in _CALC_QUANTITY_RE.finditer(prior_text):
            token = match.group(0).casefold()
            canonical = (
                "Umfangsgeschwindigkeit"
                if "umfangsgeschwindigkeit" in token
                else ("PV-Wert" if token.startswith("pv") else "Verpressung")
            )
            if canonical not in quantities:
                quantities.append(canonical)
        if inspected >= 4:
            break

    if len(quantities) != 1:
        return None
    if explicit_reference:
        suffix = f"Verbindlich aufgelöste Rechengröße: {quantities[0]}."
    else:
        suffix = (
            "Verbindlicher Kontext: Eingaben für die angeforderte Berechnung der "
            f"{quantities[0]}."
        )
    return f"{text}\n{suffix}"


def requests_solution(question: str) -> bool:
    """Whether the user explicitly asks the current engineering turn to develop a solution.

    This is a bounded conversation-goal signal only.  Evidence, calculation and execution policy
    remain the sole authorities for what the answer may claim.
    """

    return bool(_SOLUTION_REQUEST_RE.search(question or ""))


def _has_material_topic(question: str, material_terms: tuple[str, ...] = ()) -> bool:
    """Recognise a material subject from the stable core vocabulary plus the live knowledge catalog.

    The catalog terms are injected by ``build_pipeline``. This removes the old architectural ceiling
    where adding an AEM/ACM/CR card did not make its subject routable until somebody also remembered to
    extend this module's regex. ``tag_matches`` keeps matching word-boundary safe.
    """
    if _MATERIAL_NAME_RE.search(question or ""):
        return True
    tokens = query_tokens(question or "")
    normalized = (question or "").lower()
    for term in material_terms:
        if not term:
            continue
        if len(term) <= 2:
            # Short engineering symbols (CR, AU, EU, WC) are valid, but case-insensitive matching
            # would turn ordinary words/acronyms such as "EU" into material questions. Require the
            # canonical uppercase spelling for these inherently ambiguous two-letter terms.
            if re.search(rf"\b{re.escape(term.upper())}\b", question or "") and (
                (question or "").strip().upper() == term.upper()
                or _SHORT_MATERIAL_CONTEXT_RE.search(question or "")
            ):
                return True
        elif tag_matches(term, tokens, normalized):
            return True
    return False


def has_material_anchor(question: str, *, material_terms: tuple[str, ...] = ()) -> bool:
    """Public material-namespace boundary for validating semantic model output."""

    return _has_material_topic(question, material_terms)


def _has_case_detail(question: str, material_terms: tuple[str, ...] = ()) -> bool:
    """Whether an opener already contains a fact/candidate the intake reply must not ignore."""

    text = question or ""
    return bool(
        _has_material_topic(text, material_terms)
        or extract_medium_facts(text)
        or detected_seal_subjects(text)
        or _CASE_APPLICATION_DETAIL_RE.search(text)
        or _ENGINEERING_VALUE_RE.search(text)
    )


def _has_operating_detail(question: str, material_terms: tuple[str, ...] = ()) -> bool:
    """Whether a case-start message already contains an operating fact.

    Generic words such as ``Dichtung`` or ``Dichtungsfall`` are intentionally not
    facts.  A material, medium, application component, value/unit or concrete
    possessive case reference is.  This distinction lets process-guidance turns
    enter intake while preventing a stated operating condition from being ignored.
    """

    text = question or ""
    return bool(
        _has_material_topic(text, material_terms)
        or extract_medium_facts(text)
        or _CASE_APPLICATION_DETAIL_RE.search(text)
        or _ENGINEERING_VALUE_RE.search(text)
    )


def has_domain_anchor(question: str, *, material_terms: tuple[str, ...] = ()) -> bool:
    """Conservative lexical/entity anchor for validating semantic model output."""

    text = question or ""
    return bool(
        _DOMAIN_KNOWLEDGE_RE.search(text)
        or _has_material_topic(text, material_terms)
        or extract_medium_facts(text)
        or _CASE_APPLICATION_DETAIL_RE.search(text)
        or _ENGINEERING_VALUE_RE.search(text)
        or _LEAKAGE_RE.search(text)
        or _RFQ_RE.search(text)
        or _META_INSTRUCTION_RE.search(text)
    )


def is_explicit_knowledge_overview(
    question: str, *, material_terms: tuple[str, ...] = ()
) -> bool:
    """Recognise an educational overview even when it names design axes.

    ``Verpressung`` and ``Auslegung`` are both engineering-case signals and normal chapter names in
    an expert explanation. Only the latter interpretation is selected here: the user must explicitly
    ask for an explanation/overview, name a sealing-domain subject, and avoid a concrete-case
    reference. All hard signals remain active and therefore still force the full pipeline.
    """

    text = question or ""
    if not (has_explicit_knowledge_request(text) or _COMPARISON_RE.search(text)):
        return False
    if not (
        _DOMAIN_KNOWLEDGE_RE.search(text) or _has_material_topic(text, material_terms)
    ):
        return False
    if _CONCRETE_CASE_REFERENCE_RE.search(text):
        return False
    return not any(
        (
            _ENGINEERING_VALUE_RE.search(text),
            _RFQ_RE.search(text),
            _SUITABILITY_QUESTION_RE.search(text),
            _META_INSTRUCTION_RE.search(text),
            _RESISTANCE_CLAIM_RE.search(text),
            is_alternativen_request(text),
        )
    )


def resolve_comparison_followup(
    question: str,
    previous_turns: tuple[object, ...],
    *,
    material_terms: tuple[str, ...] = (),
    comparison_intent: bool = False,
) -> MaterialComparisonFollowup | None:
    """Resolve contextual comparisons against recent user-authored subjects.

    Supported subject namespaces are materials, seal types and media.  Raw
    transcript text never crosses this boundary: only canonical entities from
    the shared domain vocabularies survive.  Assistant messages are ignored.

    A contextual comparison has exactly two safe outcomes:

    * two provable, same-type subjects -> an explicit canonical request;
    * anything else -> a deterministic clarification, never generation.
    """
    text = (question or "").strip()
    if not comparison_intent and not _COMPARISON_RE.search(text):
        return None

    def subject_groups(value: str) -> dict[str, tuple[str, ...]]:
        groups = {
            "material": detected_material_subjects(
                value, material_terms=material_terms
            ),
            "seal_type": detected_seal_subjects(value),
            "medium": extract_media(value),
        }
        return {kind: subjects for kind, subjects in groups.items() if subjects}

    current_groups = subject_groups(text)
    current_count = sum(len(subjects) for subjects in current_groups.values())
    # ``unterscheiden`` is also ordinary diagnostic language ("Welche Ursache
    # würdest du zuerst unterscheiden?").  Context resolution is allowed only
    # when the current turn names a governed subject, explicitly refers to a
    # pair, or the semantic router independently classified a comparison.
    contextual_pair = bool(
        re.search(
            r"\b(?:beide|die\s+beiden|untereinander|im\s+vergleich|"
            r"unterschied(?:e)?\s+zwischen|unterscheidet\s+(?:es|sich)\s+von|"
            r"was\s+unterscheidet\s+(?:sie|beide)|wie\s+unterscheiden\s+sie\s+sich|"
            r"gegen[uü]ber|vs\.?|versus)\b",
            text,
            re.IGNORECASE,
        )
    )
    if not comparison_intent and current_count == 0 and not contextual_pair:
        return None
    # A self-contained educational comparison can name categories outside the
    # canonical material/seal/media vocabularies (for example static versus
    # dynamic seals).  It belongs to the ordinary knowledge route, not to the
    # contextual-reference resolver.
    if (
        not comparison_intent
        and current_count == 0
        and has_explicit_knowledge_request(text)
        and _DOMAIN_KNOWLEDGE_RE.search(text)
    ):
        return None
    # A self-contained comparison already names both sides and needs no context
    # resolution.  Cross-type comparisons remain on the ordinary route, where
    # the answer planner can decide whether the request is meaningful.
    if current_count >= 2:
        return None
    # A comparison with no explicitly named side is itself a contextual request
    # ("Was ist der Unterschied?", "Welcher ist besser?", "vergleiche beide").
    # This also covers natural paraphrases without a pronoun.  With no provable
    # pair below, the result is a clarification rather than a guessed answer.
    if current_count == 1 and len(current_groups) != 1:
        return None

    expected_type = next(iter(current_groups), None)
    recent_blocks: list[tuple[str, tuple[str, ...]]] = []
    inspected = 0
    for turn in reversed(previous_turns):
        if getattr(turn, "role", None) != "user":
            continue
        inspected += 1
        prior_text = str(getattr(turn, "text", "") or "")
        groups = subject_groups(prior_text)
        if not groups:
            if _DOMAIN_KNOWLEDGE_RE.search(prior_text):
                break
            if inspected >= 4:
                break
            continue
        if len(groups) != 1:
            recent_blocks.append(("mixed", tuple()))
            break
        kind, subjects = next(iter(groups.items()))
        if expected_type is not None and kind != expected_type:
            break
        expected_type = expected_type or kind
        recent_blocks.append((kind, subjects))
        if inspected >= 4:
            break

    candidates: list[str] = []
    # Restore chronological order while preserving the order inside one turn.
    for kind, subjects in reversed(recent_blocks):
        if kind == "mixed" or (expected_type is not None and kind != expected_type):
            continue
        for subject in subjects:
            if subject not in candidates:
                candidates.append(subject)
    for subjects in current_groups.values():
        for subject in subjects:
            if subject not in candidates:
                candidates.append(subject)

    if len(candidates) == 2 and expected_type is not None:
        pair = tuple(candidates)
        return MaterialComparisonFollowup(
            resolved_question=(
                f"{text}\nVerbindlich aufgelöste Vergleichsgegenstände "
                f"({expected_type}): {pair[0]} und {pair[1]}."
            ),
            subjects=pair,
            subject_type=expected_type,
        )

    type_label = {
        "material": "Werkstoffe",
        "seal_type": "Dichtungsarten",
        "medium": "Medien",
    }.get(expected_type or "", "Gegenstände")
    if len(candidates) == 1:
        clarification = (
            f"Ich kann im bisherigen Gespräch nur {candidates[0]} eindeutig "
            f"zuordnen. Welche zweite Position möchtest du damit vergleichen?"
        )
    elif len(candidates) > 2:
        clarification = (
            f"Im bisherigen Gespräch sind mehr als zwei mögliche {type_label} "
            f"genannt: {', '.join(candidates)}. Bitte nenne genau die zwei, "
            "die ich vergleichen soll."
        )
    else:
        clarification = (
            f"Welche zwei {type_label} möchtest du vergleichen? Bitte nenne "
            "beide ausdrücklich, damit ich keinen falschen Bezug herstelle."
        )
    return MaterialComparisonFollowup(
        resolved_question="",
        subjects=tuple(candidates),
        subject_type=expected_type or "unknown",
        status="needs_clarification",
        clarification=clarification,
    )


# Compatibility name for older call sites/tests.  The resolver now handles all
# governed comparison subject types, not only materials.
resolve_material_comparison_followup = resolve_comparison_followup


def detect_engineering_signals(
    question: str,
    *,
    case_state_nonempty: bool = False,
    decode_result: dict | None = None,
    diagnosis: dict | None = None,
    gegencheck_verdict: dict | None = None,
    material_terms: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Every deterministic engineering signal that fires, by name. Pre-computed pipeline values
    (``decode_result``/``diagnosis``/``gegencheck_verdict``/``case_state_nonempty``) are accepted
    as optional hints so the caller (``Pipeline.run``) never pays for a second lookup/matrix query
    — they default to "absent" so this function is fully usable with just a question string in
    tests. A single positive signal is enough to force the full pipeline; the returned tuple's
    length is Stage 1's ``deterministic_signal_count``."""
    signals: list[str] = []
    explicit_knowledge_overview = is_explicit_knowledge_overview(
        question, material_terms=material_terms
    )
    leakage_target = bool(_LEAKAGE_TARGET_RE.search(question))
    observed_failure = bool(
        _LEAKAGE_RE.search(question)
        and (not leakage_target or _OBSERVED_FAILURE_RE.search(question))
    )
    if decode_result:
        signals.append("designation_or_dimensions")
    if (
        diagnosis is not None
        and not explicit_knowledge_overview
        and (not leakage_target or observed_failure)
    ):
        signals.append("recognized_failure_symptom")
    if gegencheck_verdict is not None:
        signals.append("material_and_medium_known")
    if case_state_nonempty:
        signals.append("case_state_nonempty")
    if is_alternativen_request(question):
        signals.append("manufacturer_alternatives_request")
    if _ENGINEERING_VALUE_RE.search(question):
        signals.append("engineering_value_with_unit")
    if _COMPRESSION_RE.search(question) and not explicit_knowledge_overview:
        signals.append("compression_or_interference_language")
    if _RFQ_RE.search(question):
        signals.append("rfq_language")
    if observed_failure and (
        not explicit_knowledge_overview
        or _OBSERVED_FAILURE_ASSERTION_RE.search(question)
    ):
        signals.append("leakage_or_failure_language")
    elif leakage_target and not explicit_knowledge_overview:
        signals.append("dynamic_leakage_target")
    process_guidance_without_facts = bool(
        requests_case_guidance(question)
        and not _has_operating_detail(question, material_terms)
    )
    if (
        _CASE_LANGUAGE_RE.search(question)
        or (
            _DESIGN_TOPIC_RE.search(question)
            and not explicit_knowledge_overview
            and not _is_case_opening_shape(question)
        )
    ) and not process_guidance_without_facts:
        signals.append("replacement_or_case_language")
    if _SUITABILITY_QUESTION_RE.search(question) and has_domain_anchor(
        question, material_terms=material_terms
    ):
        signals.append("suitability_or_recommendation_request")
    bare_family_definition = _BARE_MATERIAL_FAMILY_DEFINITION_RE.fullmatch(
        question or ""
    )
    definitional_family_request = bool(
        bare_family_definition
        and _is_exact_named_material_family(
            bare_family_definition.group("family"), material_terms
        )
    )
    if _MANUFACTURER_IDENTIFIER_RE.search(question) and not definitional_family_request:
        signals.append("manufacturer_identifier_request")
    if _META_INSTRUCTION_RE.search(question):
        signals.append("meta_or_directive_language")
    if requests_calculation(question):
        signals.append("kinematic_or_calc_term")
    if _RESISTANCE_CLAIM_RE.search(question):
        signals.append("resistance_or_suitability_claim")

    # Material/medium: a BARE mention of either alone is a knowledge-question profile ("was ist
    # PTFE?") and must NOT force the full pipeline — only the two TOGETHER in one message reflect
    # a described operating situation, not a definition request.
    has_material = bool(extract_seal_spec(question)) or _has_material_topic(
        question, material_terms
    )
    has_medium = bool(extract_medium_facts(question))
    if has_material and has_medium:
        signals.append("material_and_medium_in_message")

    has_application = bool(_CASE_APPLICATION_DETAIL_RE.search(question))
    if (
        not explicit_knowledge_overview
        and has_application
        and (
            has_medium
            or _CASE_MOTION_DETAIL_RE.search(question)
            or _SAFETY_CASE_RE.search(question)
        )
    ):
        signals.append("application_operating_context")

    # Comparative-suitability language about a material is the L3 trap catalog's sharpest edge
    # (unauthorized comparative-ranking claims) — force the full path even with no medium stated.
    comparison_subjects = detected_seal_subjects(question)
    if _COMPARISON_RE.search(question) and (
        _has_material_topic(question, material_terms) or len(comparison_subjects) >= 2
    ):
        signals.append("comparison_with_material")

    return tuple(signals)


def _forced_route(question: str, signals: tuple[str, ...]) -> RouteName:
    """Pick the most specific label among the always-full-pipeline routes. This choice is
    OBSERVABILITY ONLY in Phase 2B — every one of these routes gets byte-identical treatment
    (the current full pipeline); the label only makes telemetry/dashboards readable."""
    if _RFQ_RE.search(question):
        return RouteName.RFQ_MANUFACTURER_BRIEF
    if (
        "recognized_failure_symptom" in signals
        or "leakage_or_failure_language" in signals
    ):
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
    material_terms: tuple[str, ...] = (),
) -> RouteDecision:
    """The full two-stage gate. ``intent`` is the soft ``understand()`` classification — pass
    ``None`` when it is unavailable (understand disabled, or not yet resolved); doing so is always
    safe because a missing intent maps to ``unsupported_or_ambiguous`` (forced full pipeline)."""
    if is_adjacent_out_of_scope_request(question):
        return RouteDecision(
            route=RouteName.UNSUPPORTED_OR_AMBIGUOUS,
            reason="adjacent_component_selection_out_of_scope",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=0,
        )

    # Current-turn signals always win. Existing case state is evaluated only AFTER a self-contained
    # knowledge topic has had a chance to route, so an old case cannot hijack "Was ist NBR?".
    signals = detect_engineering_signals(
        question,
        case_state_nonempty=False,
        decode_result=decode_result,
        diagnosis=diagnosis,
        gegencheck_verdict=gegencheck_verdict,
        material_terms=material_terms,
    )
    if signals:
        return RouteDecision(
            route=_forced_route(question, signals),
            reason=f"deterministic_signals:{','.join(signals)}",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=len(signals),
        )

    if has_explicit_knowledge_request(question) and (
        _CASE_DEVELOPMENT_RE.search(question) or requests_case_guidance(question)
    ):
        return RouteDecision(
            route=RouteName.ENGINEERING_CASE,
            reason="mixed_case_and_knowledge_request",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=1,
        )

    case_start_request = _is_case_opening_shape(question) or requests_case_guidance(
        question
    )
    if (
        not has_explicit_knowledge_request(question)
        and case_start_request
        and _has_operating_detail(question, material_terms)
    ):
        return RouteDecision(
            route=RouteName.ENGINEERING_CASE,
            reason="case_opening_with_case_details",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=1,
        )

    # 2026-07-19 (case-intake fix): zero Stage-1 signals, no existing case, no material topic, a
    # narrow discussion/help-INTENT opener shape, and NOT itself a knowledge request ("was ist...").
    # Additive and strictly narrower than the domain-knowledge branch below: a message that ALSO
    # looks like a knowledge request (_KNOWLEDGE_REQUEST_RE) still falls through to
    # general_sealing_knowledge/material_knowledge exactly as before this change. Uses
    # _is_case_opening_shape (not a bare .search()) so a long message cannot ride an L3-bypassed
    # route just by containing the trigger phrase somewhere in it -- see that function's docstring.
    if (
        not case_state_nonempty
        and not signals
        and case_start_request
        and not has_explicit_knowledge_request(question)
    ):
        return RouteDecision(
            route=RouteName.CASE_INTAKE_INVITE,
            reason="case_opening_zero_signal",
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    # Entity detection never grants a knowledge route on its own.  The current utterance must also
    # carry an explicit educational/factual speech act (or the soft intent below must classify it as
    # one).  This prevents "Dichtungslösung entwickeln – was brauchst du?" from launching RAG merely
    # because ``dichtungs\w*`` occurred in the sentence.
    if _has_material_topic(question, material_terms) and has_explicit_knowledge_request(
        question
    ):
        return RouteDecision(
            route=RouteName.MATERIAL_KNOWLEDGE,
            reason=(
                f"intent={intent.value}"
                if intent in (Intent.WISSENSFRAGE, Intent.FAKTFRAGE)
                else "explicit_material_knowledge_request"
            ),
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    if _DOMAIN_KNOWLEDGE_RE.search(question) and has_explicit_knowledge_request(
        question
    ):
        return RouteDecision(
            route=RouteName.GENERAL_SEALING_KNOWLEDGE,
            reason="explicit_domain_knowledge_request",
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    if case_state_nonempty:
        return RouteDecision(
            route=RouteName.ENGINEERING_CASE,
            reason="existing_case_context",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=1,
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

    if intent == Intent.GESPRAECH and _is_smalltalk_shape(question):
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
            if _has_material_topic(question, material_terms)
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
    material_terms: tuple[str, ...] = (),
) -> RouteDecision:
    """LLM-free production router.

    The same conservative engineering signals as :func:`classify_route` force
    the full path. Only narrow, explicit smalltalk and domain-knowledge shapes
    receive a cheaper route; anything else is ambiguous and therefore full.
    """
    if is_adjacent_out_of_scope_request(question):
        return RouteDecision(
            route=RouteName.UNSUPPORTED_OR_AMBIGUOUS,
            reason="deterministic_adjacent_component_selection_out_of_scope",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=0,
        )

    signals = detect_engineering_signals(
        question,
        case_state_nonempty=False,
        decode_result=decode_result,
        diagnosis=diagnosis,
        gegencheck_verdict=gegencheck_verdict,
        material_terms=material_terms,
    )
    if signals:
        return RouteDecision(
            route=_forced_route(question, signals),
            reason=f"deterministic_signals:{','.join(signals)}",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=len(signals),
        )
    if has_explicit_knowledge_request(question) and (
        _CASE_DEVELOPMENT_RE.search(question) or requests_case_guidance(question)
    ):
        return RouteDecision(
            route=RouteName.ENGINEERING_CASE,
            reason="deterministic_mixed_case_and_knowledge_request",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=1,
        )
    case_start_request = _is_case_opening_shape(question) or requests_case_guidance(
        question
    )
    if (
        not has_explicit_knowledge_request(question)
        and case_start_request
        and _has_operating_detail(question, material_terms)
    ):
        return RouteDecision(
            route=RouteName.ENGINEERING_CASE,
            reason="deterministic_case_opening_with_case_details",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=1,
        )
    # 2026-07-19 (case-intake fix): see the identical block + rationale in classify_route() above.
    if (
        not case_state_nonempty
        and not signals
        and case_start_request
        and not has_explicit_knowledge_request(question)
    ):
        return RouteDecision(
            route=RouteName.CASE_INTAKE_INVITE,
            reason="deterministic_case_opening_zero_signal",
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    if _has_material_topic(question, material_terms) and has_explicit_knowledge_request(
        question
    ):
        return RouteDecision(
            route=RouteName.MATERIAL_KNOWLEDGE,
            reason="deterministic_explicit_material_knowledge_request",
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    if _DOMAIN_KNOWLEDGE_RE.search(question) and has_explicit_knowledge_request(
        question
    ):
        return RouteDecision(
            route=RouteName.GENERAL_SEALING_KNOWLEDGE,
            reason="deterministic_explicit_domain_knowledge_request",
            confidence=1.0,
            forced_full_pipeline=False,
            deterministic_signal_count=0,
        )
    if case_state_nonempty:
        return RouteDecision(
            route=RouteName.ENGINEERING_CASE,
            reason="existing_case_context",
            confidence=1.0,
            forced_full_pipeline=True,
            deterministic_signal_count=1,
        )
    if _is_smalltalk_shape(question):
        return RouteDecision(
            route=RouteName.SMALLTALK_NAVIGATION,
            reason="deterministic_smalltalk_shape",
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
