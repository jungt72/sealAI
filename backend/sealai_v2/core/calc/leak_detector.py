"""M8-C — deterministic detector for the L1-parametric-computation trap class.

Fires iff a draft ASSERTS a precise value for a kern-owned quantity (the reviewed calc registry:
umfangsgeschwindigkeit / pv_wert / verpressung_prozent) that the deterministic kern did NOT
compute — or that contradicts the kern's value. Defense-in-depth: this is the enforcement layer
behind the L1 prompt rule (prevention) and beside the TRAP-L1-PARAMETRIC-CALC catalog entry (the
LLM critic catches paraphrases this regex core cannot).

Boundary (the owner zero-FP review package, decision 4; hardened per owner boundary review
2026-06-11; symbol-form/window hardening per the live staging repro 2026-06-11, branch (b),
owner FIX-FIRST decision):
- FIRES only with an ASSERTION signature in the sentence (=, ≈, ~, beträgt, ergibt, liegt bei,
  errechnet/resultiert) — bare mentions never fire.
- The quantity gate is satisfied by (1) an own word token in the asserting sentence, (2) an own
  word token in the IMMEDIATELY PRECEDING sentence (window-2 — anaphora "Sie beträgt …"), or
  (3) the SYMBOL+UNIT self-trigger: a symbol-form assertion (v = / pv =) together with the
  quantity's unit in the asserting sentence ("v = 16,76 m/s" with the trigger word sentences
  away — the live turn-2 layout). The self-trigger is suppressed when a FOREIGN velocity
  compound (a ``…geschwindigkeit`` word that is not an own token; bare "Geschwindigkeit" is
  generic, never foreign) appears in the ASSERTING sentence itself — the preceding sentence is
  deliberately NOT consulted for the foreign check (owner FOLD 1: FN > FP for a trust-spine
  detector). An own token in the window always wins over the guard.
- EXEMPT: a value matching a kern-computed value (≤2 % — referencing/rounding is not recomputing);
  a value that is PART OF an actual RANGE structure (two numbers / bis / –) in a sentence that
  also carries a verify-caveat (typical-knowledge statements, the ``is_precision_overapplication``
  precedent) — span-scoped: only the range's own values are exempt; a point-value with a caveat
  alone, or a point-value beside someone else's range, still fires; the symbolic formula without
  plugged result (v = π·d·n/60000); units/numbers outside the quantity lexicon (%, m/s etc. only
  count in their quantity's sentence context).
- German number forms: decimal comma; a dot form ("10.472") is interpreted BOTH as decimal and
  thousands and is exempt if EITHER reading matches the kern (conservative anti-FP).

Known boundaries (documented, covered by the catalog/LLM side):
- a plugged formula without a stated result ("v = π·50·4000/60000") is not deterministically
  detectable here;
- an own token >1 sentence back WITHOUT a symbol form does not gate (window-2 reach);
- an own token on a PREVIOUS LINE (markdown header/label line) with a NO-SYMBOL value on the
  next line does not gate — window-2 is deliberately line-bounded (the cross-line grant
  produced the Nutfüllgrad/Shore-A knowledge-range FPs); accepted residual: every observed
  true leak (live repro + all sweep corpora) is symbol-form or same-line, and the symbol+unit
  self-trigger covers the header layout whenever the value line writes "v = …";
- residual (a): a foreign velocity word in the SAME sentence as a symbol-form kern value still
  suppresses (rare mixed-velocity construction → potential miss, accepted FN side);
- residual (b): a foreign-velocity value in symbol-form whose word sits only in the PRECEDING
  sentence fires against an empty kern (mild accepted FP — the zero-FP sweep confirms it does
  not occur on owner-passed answers).

Pure core: no I/O, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sealai_v2.core.contracts import ComputedValue

_NUM = r"\d+(?:[.,]\d+)?"

# kern-owned quantity lexicon: calc_id → (sentence tokens, unit pattern, symbol pattern or None)
_QUANTITIES: dict[str, tuple[tuple[str, ...], str, str | None]] = {
    "umfangsgeschwindigkeit": (
        ("umfangsgeschwindigkeit", "gleitgeschwindigkeit"),
        r"m\s*/\s*s",
        r"\bv\s*[=≈~]",
    ),
    "pv_wert": (("pv-wert", "pv wert"), r"bar\s*[·*x×]\s*m\s*/\s*s", r"\bpv\s*[=≈~]"),
    "verpressung_prozent": (("verpressung",), r"%", None),
}

_ASSERTION_RE = re.compile(
    r"[=≈~]|beträgt|ergibt|liegt bei|errechnet|resultiert", re.IGNORECASE
)
# foreign-velocity context for the symbol+unit self-trigger: any compound …geschwindigkeit that is
# not an own token claims the sentence's velocity symbol/unit for itself (bare "geschwindigkeit"
# is generic, never foreign). Applies per quantity — pv's symbol/unit are not claimed by velocity
# words, so only umfangsgeschwindigkeit carries the guard.
_VELOCITY_COMPOUND_RE = re.compile(r"\b[\wäöüß]*geschwindigkeit", re.IGNORECASE)
_FOREIGN_CONTEXT: dict[str, re.Pattern[str] | None] = {
    "umfangsgeschwindigkeit": _VELOCITY_COMPOUND_RE,
    "pv_wert": None,
    "verpressung_prozent": None,
}
# range + caveat → typical-knowledge exemption (mirrors l3_verifier.is_precision_overapplication).
# The tail consumes the FULL upper-bound number ("8–12", "15-25,5") so the span-scoped containment
# check sees the whole range, not just its first digit.
_RANGE_RE = re.compile(
    r"\d[\d.\s'’]*\s*(?:[–—-]|…|\.{2,3}|\bbis\b)\s*\+?\s*\d[\d.,]*", re.IGNORECASE
)
_CAVEAT_RE = re.compile(
    r"\btyp(?:isch|\.)|richtwert|üblich|faustwert|orientier|datenblatt|verifizier|herstellerangabe",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")  # within-line sentence flow (window-2 scope)
_REL_TOLERANCE = (
    0.02  # referencing the kern value incl. rounding ≤2 % is not recomputing
)


@dataclass(frozen=True)
class LeakFinding:
    calc_id: str
    value_text: str
    excerpt: str


def _readings(num: str) -> tuple[float, ...]:
    """All deterministic readings of a German/render number form (dot = decimal OR thousands)."""
    if "," in num:
        return (float(num.replace(".", "").replace(",", ".")),)
    if "." in num:
        return (
            float(num),
            float(num.replace(".", "")),
        )  # decimal reading + thousands reading
    return (float(num),)


def _matches_kern(num: str, kern_values: tuple[float, ...]) -> bool:
    for reading in _readings(num):
        for kv in kern_values:
            if kv == 0:
                if reading == 0:
                    return True
            elif abs(reading - kv) / abs(kv) <= _REL_TOLERANCE:
                return True
    return False


def _has_foreign_compound(
    pattern: re.Pattern[str], low: str, own_tokens: tuple[str, ...]
) -> bool:
    """A compound match that is not an own token (the bare base word, e.g. 'geschwindigkeit',
    is generic, never foreign) — suppresses the self-trigger in the ASSERTING sentence only."""
    for m in pattern.finditer(low):
        word = m.group(0)
        if word == "geschwindigkeit":
            continue
        if word not in own_tokens:
            return True
    return False


def detect_parametric_leaks(
    text: str, *, computed_values: tuple[ComputedValue, ...] = ()
) -> tuple[LeakFinding, ...]:
    """Scan a draft for asserted values of kern-owned quantities not backed by the kern."""
    if not text.strip():
        return ()
    kern: dict[str, tuple[float, ...]] = {}
    for c in computed_values:
        kern[c.calc_id] = kern.get(c.calc_id, ()) + (c.value,)

    findings: list[LeakFinding] = []
    # window-2 is bounded by LINES: a token carries into the next sentence of the same line's
    # prose flow, never across a newline (list items are separate semantic units — the sweep's
    # FP shape: a 'Verpressung' header line must not claim the next line's 'Nutfüllgrad 75–90 %').
    sentences: list[tuple[str, str]] = []  # (sentence, prev_low within the same line)
    for line in re.split(r"\n+", text):
        prev = ""
        for s in _SENT_SPLIT.split(line):
            if not s.strip():
                continue
            sentences.append((s, prev))
            prev = s.lower()
    for sentence, prev_low in sentences:
        low = sentence.lower()
        if not _ASSERTION_RE.search(sentence):
            continue  # bare mention without an assertion never fires
        # typical-range knowledge with caveat is exempt SPAN-SCOPED (owner hardening 2026-06-11):
        # only values inside an actual range structure are knowledge, not computation — a
        # point-value with a caveat alone, or beside someone else's range, still fires.
        range_spans = (
            [m.span() for m in _RANGE_RE.finditer(sentence)]
            if _CAVEAT_RE.search(sentence)
            else []
        )
        for calc_id, (tokens, unit_re, symbol_re) in _QUANTITIES.items():
            # quantity gate: own token in this sentence, own token one sentence back (window-2),
            # or the symbol+unit self-trigger (live turn-2 layout). Own token always wins; the
            # foreign-velocity guard consults the ASSERTING sentence only (owner FOLD 1, FN > FP).
            token_here = any(t in low for t in tokens)
            token_prev = any(t in prev_low for t in tokens)
            if not token_here and not token_prev:
                if symbol_re is None:
                    continue
                if not re.search(rf"{symbol_re}\s*{_NUM}", sentence, re.IGNORECASE):
                    continue
                if not re.search(unit_re, sentence, re.IGNORECASE):
                    continue
                foreign = _FOREIGN_CONTEXT.get(calc_id)
                if foreign is not None and _has_foreign_compound(foreign, low, tokens):
                    continue  # residual (a): foreign word in the asserting sentence suppresses
            quantity_spans = range_spans
            if not token_here and token_prev and not range_spans:
                # window-granted fragment: the caveat may sit in the granting sentence (the
                # sweep's citation FP — an abbreviation like 'typ.' split the sentence and
                # orphaned the range from its caveat). Span-scoping is unchanged: only the
                # fragment's own RANGE values are blessed, a point value still fires.
                if _CAVEAT_RE.search(prev_low):
                    quantity_spans = [m.span() for m in _RANGE_RE.finditer(sentence)]
            candidates = list(
                re.finditer(rf"({_NUM})\s*(?:{unit_re})", sentence, re.IGNORECASE)
            )
            if symbol_re:
                candidates += list(
                    re.finditer(rf"{symbol_re}\s*({_NUM})", sentence, re.IGNORECASE)
                )
            for m in candidates:
                num = m.group(1)
                start, end = m.span(1)
                if any(s <= start and end <= e for s, e in quantity_spans):
                    continue  # a value of the typical range itself (+ caveat) — knowledge
                if _matches_kern(num, kern.get(calc_id, ())):
                    continue
                findings.append(
                    LeakFinding(
                        calc_id=calc_id,
                        value_text=num,
                        excerpt=sentence.strip()[:200],
                    )
                )
                break  # one finding per quantity per sentence
    return tuple(findings)
