"""Conservative deterministic extraction of explicitly named sealing types."""

from __future__ import annotations

import re

from sealai_v2.core.contracts import RememberedFact


_TYPE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bRWDR\b", re.IGNORECASE), "RWDR"),
    (
        re.compile(r"\bRadial[-\s]?Wellen?dichtring(?:e|en|s)?\b", re.IGNORECASE),
        "RWDR",
    ),
    (re.compile(r"\bSimmerring(?:e|en|s)?\b", re.IGNORECASE), "RWDR"),
    (re.compile(r"\bWellendichtung(?:en)?\b", re.IGNORECASE), "RWDR"),
    (re.compile(r"\bO[-\s]?Ring(?:e|en|s)?\b", re.IGNORECASE), "O-Ring"),
    (re.compile(r"\bX[-\s]?Ring(?:e|en|s)?\b", re.IGNORECASE), "X-Ring"),
    (re.compile(r"\bV[-\s]?Ring(?:e|en|s)?\b", re.IGNORECASE), "V-Ring"),
    (re.compile(r"\bNutring(?:e|en|s)?\b", re.IGNORECASE), "Nutring"),
    (
        re.compile(
            r"(?<!Radial)(?<!Radial-)(?<!Radial )\bWellendichtring(?:e|en|s)?\b",
            re.IGNORECASE,
        ),
        "Wellendichtring",
    ),
    (
        re.compile(r"\bGleitringdichtung(?:en)?\b", re.IGNORECASE),
        "Gleitringdichtung",
    ),
    (re.compile(r"\bGLRD\b", re.IGNORECASE), "Gleitringdichtung"),
    (re.compile(r"\bMechanical\s+Seal(?:s)?\b", re.IGNORECASE), "Gleitringdichtung"),
)


def extract_seal_type(message: str) -> str | None:
    """Return one explicit canonical type, or ``None`` when absent/ambiguous.

    Synonyms that name the same canonical type are deduplicated. Mentioning two
    different types remains unresolved because negation and comparison must not
    be guessed by a lexical binder.
    """

    found = {
        seal_type for pattern, seal_type in _TYPE_PATTERNS if pattern.search(message)
    }
    return next(iter(found)) if len(found) == 1 else None


def extract_seal_type_facts(message: str) -> tuple[RememberedFact, ...]:
    """Project an explicit type into canonical case state without an LLM call."""

    seal_type = extract_seal_type(message)
    if seal_type is None:
        return ()
    return (
        RememberedFact(
            feld="dichtungstyp",
            wert=seal_type,
            provenance="chat-inline",
        ),
    )
