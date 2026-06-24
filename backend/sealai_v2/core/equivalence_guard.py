"""§9.2 equivalence guard — the single sharpest liability line.

"Teil X = Teil Y" (interchangeable) is the doctrine's most dangerous claim (§9.2). ``EQUIVALENZ_GRENZE``
(``decode_extract``) is the owner-grounded boundary string, but it only ever rode along the decode
struct as a disclaimer — nothing constrained the L1 PROSE from asserting interchangeability. This
module is the deterministic backstop: a CONSERVATIVE scan of the final answer for an *affirmative*
interchangeability assertion (negated forms are the doctrine-correct statement and are skipped). A hit
is hedged down to the owner-grounded boundary. Deliberately narrow — only phrasings that almost never
have a non-equivalence reading — so false-positives stay near zero; the L1 prompt handles the nuance.
"""

from __future__ import annotations

import re

from sealai_v2.core.decode_extract import EQUIVALENZ_GRENZE

EQUIVALENCE_TRAP_ID = "EQUIVALENZ-GRENZE"
EQUIVALENCE_GATE = (
    "confident_wrong"  # one of HARD_GATES — the §9.2 confident-wrong concern
)

# Affirmative part-INTERCHANGEABILITY assertions (German). Narrow by design: each phrasing asserts
# that two parts may be swapped, which §9.2 forbids without a manufacturer release.
_EQUIV_RE = re.compile(
    r"(?:"
    r"1\s*(?::|zu)\s*1\s+austauschbar"
    r"|eins\s+zu\s+eins\s+austauschbar"
    r"|baugleich"
    r"|(?:problemlos|bedenkenlos|ohne\s+weiteres|einfach|direkt|vollst[aä]ndig|voll|uneingeschr[aä]nkt)\s+"
    r"(?:tauschen|austauschen|ersetzen|wechseln|austauschbar|ersetzbar)"
    r"|exakt\s+(?:dasselbe|das\s+gleiche|identisch|gleich)"
    r"|100\s*%\s*(?:identisch|austauschbar|gleich)"
    r"|identisch\s+und\s+austauschbar"
    r")",
    re.IGNORECASE,
)
# Negation cues in the short window BEFORE a match → the SAFE negated form ("nicht 1:1 austauschbar").
_NEG_RE = re.compile(
    r"(?:nicht|kein\w*|nie\w*|selten|nur\s+bedingt|ohne\s+(?:garantie|freigabe|best[aä]tigung))",
    re.IGNORECASE,
)
_NEG_WINDOW = 36


def detect_equivalence_claim(text: str) -> tuple[str, ...]:
    """Return the affirmative interchangeability phrases in ``text`` (empty if none).

    A negated occurrence — the doctrine-correct statement ("nicht 1:1 austauschbar") — is skipped."""
    hits: list[str] = []
    for m in _EQUIV_RE.finditer(text):
        before = text[max(0, m.start() - _NEG_WINDOW) : m.start()]
        if _NEG_RE.search(before):
            continue
        hits.append(m.group(0))
    return tuple(hits)


def equivalence_hedge_text() -> str:
    """The owner-grounded §9.2 boundary as a standalone hedge. Number-free, and will NOT self-trigger
    the detector — its own "1:1 austauschbar" is negated by "nicht automatisch"."""
    return (
        "Zwei Teile mit gleichen Nennmaßen und gleicher Werkstoffklasse sind nicht automatisch "
        "1:1 austauschbar. " + EQUIVALENZ_GRENZE
    )
