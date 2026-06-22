"""Deterministic token/tag matching primitives (pure — no I/O, build-spec §3 keeps ``core`` I/O-free).

Promoted from ``knowledge/matrix.py`` so the §4 compatibility matrix AND the L3 trap topic-gate share
ONE matcher (DRY): the matrix scopes a cell to a query, the verifier scopes a trap's
``correct_recommendation`` to the question. Word-boundary / phrase / prefix matching tuned for German
compounds (e.g. ``'mineralöl' ⊂ 'mineralölen'``). No behaviour change vs. the matrix's prior
``_query_tokens``/``_tag_matches``.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[^0-9a-zA-ZäöüßÄÖÜ]+")


def query_tokens(text: str) -> set[str]:
    """Lowercase the text and split into alnum/umlaut tokens (drops punctuation/whitespace)."""
    return {t for t in _TOKEN_RE.split(text.lower()) if t}


def tag_matches(tag: str, q_tokens: set[str], q_norm: str) -> bool:
    """Word-boundary match (NOT raw substring — German compounds make substring too greedy, e.g.
    'heiß' ⊂ 'heißdampf'). A multi-word/hyphen phrase matches as a substring (phrases are distinctive);
    a single word matches exactly, or — for tags ≥6 chars — as a prefix of a query token (inflection,
    e.g. 'mineralöl' ⊂ 'mineralölen', 'schnelldrehend' ⊂ 'schnelldrehende')."""
    tag = tag.strip().lower()
    if not tag:
        return False
    if " " in tag or "-" in tag:
        return tag in q_norm
    if tag in q_tokens:
        return True
    if len(tag) >= 6:
        return any(tok.startswith(tag) for tok in q_tokens if len(tok) >= 6)
    return False
