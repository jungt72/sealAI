"""M8-C — deterministic detector for the L1-parametric-computation trap class.

Fires iff a draft ASSERTS a precise value for a kern-owned quantity (the reviewed calc registry:
umfangsgeschwindigkeit / pv_wert / verpressung_prozent) that the deterministic kern did NOT
compute — or that contradicts the kern's value. Defense-in-depth: this is the enforcement layer
behind the L1 prompt rule (prevention) and beside the TRAP-L1-PARAMETRIC-CALC catalog entry (the
LLM critic catches paraphrases this regex core cannot).

Boundary (the owner zero-FP review package, decision 4):
- FIRES only with an ASSERTION signature in the sentence (=, ≈, ~, beträgt, ergibt, liegt bei,
  errechnet/resultiert) — bare mentions never fire.
- EXEMPT: a value matching a kern-computed value (≤2 % — referencing/rounding is not recomputing);
  a RANGE + verify-caveat (typical-knowledge statements, the ``is_precision_overapplication``
  precedent); the symbolic formula without plugged result (v = π·d·n/60000); units/numbers outside
  the quantity lexicon (%, m/s etc. only count in their quantity's sentence context).
- German number forms: decimal comma; a dot form ("10.472") is interpreted BOTH as decimal and
  thousands and is exempt if EITHER reading matches the kern (conservative anti-FP).

Known boundary (documented, covered by the catalog/LLM side): a plugged formula without a stated
result ("v = π·50·4000/60000") is not deterministically detectable here.

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
# range + caveat → typical-knowledge exemption (mirrors l3_verifier.is_precision_overapplication)
_RANGE_RE = re.compile(
    r"\d[\d.\s'’]*\s*(?:[–—-]|…|\.{2,3}|\bbis\b)\s*\+?\s*\d", re.IGNORECASE
)
_CAVEAT_RE = re.compile(
    r"typisch|richtwert|üblich|faustwert|orientier|datenblatt|verifizier|herstellerangabe",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
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
    for sentence in _SENTENCE_SPLIT.split(text):
        low = sentence.lower()
        if not low.strip():
            continue
        if _RANGE_RE.search(sentence) and _CAVEAT_RE.search(sentence):
            continue  # typical-range knowledge with caveat — not parametric computation
        if not _ASSERTION_RE.search(sentence):
            continue  # bare mention without an assertion never fires
        for calc_id, (tokens, unit_re, symbol_re) in _QUANTITIES.items():
            if not any(t in low for t in tokens):
                continue
            candidates = re.findall(
                rf"({_NUM})\s*(?:{unit_re})", sentence, re.IGNORECASE
            )
            if symbol_re:
                candidates += re.findall(
                    rf"{symbol_re}\s*({_NUM})", sentence, re.IGNORECASE
                )
            for num in candidates:
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
