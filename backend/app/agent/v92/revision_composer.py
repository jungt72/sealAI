"""Bounded V9.2 revision composer.

This composer is deterministic in the MVP. It only downgrades claims requested
by the adversarial verdict and appends required limits; it never introduces new
technical claims.
"""

from __future__ import annotations

import re

from app.agent.v92.contracts import AdversarialReviewVerdict, FinalAnswerContext


def revise_answer_once(
    draft: str,
    *,
    context: FinalAnswerContext,
    verdict: AdversarialReviewVerdict,
) -> str:
    text = str(draft or "").strip()
    if verdict.decision != "revise" or not text:
        return text

    replacements = (
        (
            re.compile(r"\bist\s+(?:sicher\s+|final\s+|gut\s+)?geeignet\b", re.IGNORECASE),
            "ist als Screening-Hypothese zu pruefen",
        ),
        (
            re.compile(r"\bsind\s+(?:sicher\s+|final\s+|gut\s+)?geeignet\b", re.IGNORECASE),
            "sind als Screening-Hypothesen zu pruefen",
        ),
        (
            re.compile(r"\bfreigegeben|zugelassen|technisch\s+validiert|garantiert\b", re.IGNORECASE),
            "nicht freigegeben",
        ),
        (
            re.compile(r"\bkonform|zertifiziert|normkonform\b", re.IGNORECASE),
            "nur mit Norm-/Review-Nachweis bewertbar",
        ),
        (
            re.compile(r"\bdie\s+ursache\s+ist\b", re.IGNORECASE),
            "eine moegliche Ursache ist",
        ),
    )
    for pattern, replacement in replacements:
        text = pattern.sub(replacement, text)

    required_lines: list[str] = []
    for warning in [*context.required_warnings, *verdict.risk_warnings_to_add]:
        clean = str(warning or "").strip()
        if clean and clean.casefold() not in text.casefold():
            required_lines.append(clean)

    if context.allowed_claim_level != "L6_expert_approved":
        required_lines.append(
            "Das ist keine technische Freigabe, sondern eine begrenzte Einordnung auf dem aktuellen Datenstand."
        )
    if context.stale_items:
        required_lines.append(
            "Stale Berechnungen oder abhaengige Pruefpunkte duerfen nicht als aktuelle Entscheidungsgrundlage verwendet werden."
        )

    deduped: list[str] = []
    seen: set[str] = set()
    for line in required_lines:
        key = line.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(line)
    if deduped:
        text = f"{text}\n\nGrenzen der Aussage:\n" + "\n".join(f"- {line}" for line in deduped)
    return text.strip()
