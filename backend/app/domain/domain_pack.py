"""DomainPack — the seal-domain extension point (Blueprint §3.3, §10.1).

A DomainPack declares everything the governed core needs to treat one seal
domain (today: RWDR) without hardcoding per-type branches in the core. RWDR is
the **only** implementation; the protocol exists now so new seal types land as a
pack, never as another core `if seal_type == …` branch (Rule of Three §3.5 — the
registry *extraction* waits for pack #2, the protocol does not).

Only methods with a real RWDR implementation today are declared here — no
speculative stubs. Deliberately **omitted** (no clean pack-level implementation
exists yet; add when one does, surfaced in the P1-1 audit):
  * ``failure_modes`` — failure modes live on ApplicationPattern
    (`app/services/application_pattern_service.py`), a different axis, not a
    seal-type pack concern.
  * ``risk_flags`` — RWDR review flags are computed per case in
    `rwdr_mvp_brief` (`engineering_review_flags`), not a static pack catalog.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DomainPack(Protocol):
    """A seal-domain pack. RWDR is the only implementation today."""

    #: Stable domain id (== ``engineering_path`` / calc-id prefix), e.g. "rwdr".
    pack_id: str

    #: RFQ output template id for this domain.
    rfq_template_id: str

    def classification_signals(self) -> tuple[frozenset[str], frozenset[str]]:
        """``(seal_type values, seal_family values)`` that select this pack."""
        ...

    def required_fields(self) -> tuple[str, ...]:
        """The seal-system required-field set for this domain."""
        ...

    def state_gate_required_fields(self) -> tuple[str, ...]:
        """Per-type EXTRA inputs the governed state gate demands beyond the base
        preselection set (medium / pressure / temperature / sealing_type).

        Distinct from ``required_fields`` (the SealSystemState set) — this is the
        state-gate type-sensitive delta consumed by the reducer readiness
        assessment (P1-4 PR1)."""
        ...

    def calculations(self) -> tuple[str, ...]:
        """Calculation ids owned by this domain (e.g. ``rwdr_*``)."""
        ...

    def owns_calc_id(self, calc_id: str) -> bool:
        """True when ``calc_id`` belongs to this domain (calc/risk routing)."""
        ...
