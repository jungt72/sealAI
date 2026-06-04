"""Per-turn declared interaction tier + fail-closed retrieval guard.

P1-2 TEIL B (Gap-Audit S2). Tier discipline used to be contractual only
(`rag_used=False`); nothing stopped a fast Tier-0 route from reaching retrieval.

Tier-0 = the trivial **no-retrieval** routes — GREETING / META_QUESTION / BLOCKED
(owner decision 2026-06-04, strict-safe set). The declared tier rides a contextvar
set deterministically from the route at turn entry; the SINGLE guard at the
retrieval funnel (`rag_orchestrator.hybrid_retrieve`) enforces it fail-closed.

Default = enforced. Kill-switch ``SEALAI_TIER0_RETRIEVAL_GUARD=0`` is incident-only
and always logged (see ops.md) — never a steady state.
"""
from __future__ import annotations

import logging
import os
from contextvars import ContextVar

log = logging.getLogger("app.agent.runtime.turn_tier")

TIER_0 = 0  # no-retrieval fast routes

# Pre-gate classifications declared Tier-0 (must never retrieve).
_TIER_0_CLASSIFICATIONS = frozenset({"GREETING", "META_QUESTION", "BLOCKED"})

# None = tier not declared for this turn → retrieval allowed (only Tier-0 blocks).
_DECLARED_TIER: ContextVar[int | None] = ContextVar("declared_turn_tier", default=None)


class TierViolation(RuntimeError):
    """A Tier-0 turn attempted retrieval — fail-closed enforcement."""


def declared_tier_for_classification(classification: object) -> int:
    """Deterministic route→tier: Tier-0 for the no-retrieval classifications, else 1."""
    name = (
        getattr(classification, "value", None)
        or getattr(classification, "name", None)
        or str(classification)
    )
    return TIER_0 if str(name).upper() in _TIER_0_CLASSIFICATIONS else 1


def set_declared_tier(tier: int | None) -> None:
    _DECLARED_TIER.set(tier)


def clear_declared_tier() -> None:
    _DECLARED_TIER.set(None)


def current_declared_tier() -> int | None:
    return _DECLARED_TIER.get()


def retrieval_guard_enabled() -> bool:
    """Kill-switch. ``SEALAI_TIER0_RETRIEVAL_GUARD`` in {0,false,no,off} disables."""
    raw = (os.getenv("SEALAI_TIER0_RETRIEVAL_GUARD") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def enforce_retrieval_allowed(*, retrieval_kind: str = "rag") -> None:
    """Fail-closed: raise :class:`TierViolation` when the current turn is Tier-0.

    No-op when no tier is declared (unknown → allowed). When the kill-switch is
    off, the would-be violation is logged (never silent) and allowed through.
    """
    if _DECLARED_TIER.get() != TIER_0:
        return
    if not retrieval_guard_enabled():
        log.warning(
            "tier0_retrieval_guard_BYPASS kind=%s tier=0 — SEALAI_TIER0_RETRIEVAL_GUARD is OFF",
            retrieval_kind,
        )
        return
    raise TierViolation(
        f"Tier-0 turn attempted retrieval ({retrieval_kind}); fast routes must not retrieve."
    )
