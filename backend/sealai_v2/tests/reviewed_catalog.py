"""Explicit review overlay for synthetic quarantine fixtures in hermetic tests.

The production seed now carries the owner's human review. This helper preserves
it and only promotes any source-backed quarantine fixture introduced by a test.
"""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from sealai_v2.knowledge.fachkarten import FachkartenCatalog, load_fachkarten

_REVIEWED_AT = "2026-07-11T00:00:00Z"
_REVIEW_EXPIRES_AT = "2099-07-11T00:00:00Z"


@lru_cache(maxsize=1)
def independently_reviewed_test_catalog() -> FachkartenCatalog:
    source = load_fachkarten()
    cards = []
    for card in source.cards:
        claims = tuple(
            replace(
                claim,
                review_state="reviewed",
                reviewed_by="test-domain-reviewer:fixture",
                reviewed_at=_REVIEWED_AT,
                review_expires_at=_REVIEW_EXPIRES_AT,
            )
            if claim.quarantined and claim.sources
            else claim
            for claim in card.claims
        )
        cards.append(
            replace(
                card,
                claims=claims,
                review_state="reviewed"
                if any(claim.reviewed for claim in claims)
                else "draft",
            )
        )
    return FachkartenCatalog(
        cards=tuple(cards),
        version=source.version,
        source="test-only human review overlay",
    )
