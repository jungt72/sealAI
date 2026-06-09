"""In-process memory store — layers 1-3 (build-spec §7) + the trivial layer-4 seam.

A pure, dependency-free measurement/CI instrument (mirrors the fake LLM client + the in-process
retriever). It validates the memory MECHANISM and the P0 tenant invariant, NOT durable scale —
Redis (working window/live case-state), Postgres (history/snapshot) and Qdrant (cross-session
retrieval) adapters are the deferred production path behind the same Protocols (build-spec §3,
M3 lazy-adapter pattern). No network, no LLM, no I/O.

Tenant scope is a MANDATORY repository-layer parameter (P0): every read/write is keyed by
``(tenant_id, session_id)`` and fails closed on an empty tenant/session. A cross-tenant read can
never hit another tenant's state — a durable leak is the worst case (build-spec §7 discipline).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sealai_v2.core.contracts import MemoryView, RememberedFact, Turn
from sealai_v2.security.tenant import TenantContext, require_tenant


@dataclass
class _SessionState:
    """One session's mutable state: the message log (L1 window / L3 history) + the structured
    case-state (L2, keyed by ``feld``, last value wins) + a completed-exchange counter."""

    messages: list[Turn] = field(default_factory=list)
    facts: dict[str, RememberedFact] = field(default_factory=dict)
    turns: int = 0


def _require(tenant_id: str, session_id: str) -> None:
    """Fail-closed scope guard (P0). Reuses the canonical tenant guard; session is per-thread."""
    require_tenant(TenantContext(tenant_id))  # raises TenantScopeError on empty/blank tenant
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is mandatory (memory is per-session)")


class InProcessConversationMemory:
    """Implements the ``ConversationMemory`` Protocol (recall + record_turn) and adds the
    user-control + history surface (view/edit/delete/clear/list) — build-spec §7 disciplines."""

    def __init__(self, window_turns: int = 6) -> None:
        # window_turns = number of recent EXCHANGES kept verbatim in the L1 window (each = 2 msgs).
        self._window_turns = max(1, window_turns)
        self._store: dict[tuple[str, str], _SessionState] = {}

    def _state(self, tenant_id: str, session_id: str) -> _SessionState:
        return self._store.setdefault((tenant_id, session_id), _SessionState())

    # --- hot path (pipeline-facing Protocol) ---

    def recall(self, *, tenant_id: str, session_id: str) -> MemoryView:
        _require(tenant_id, session_id)
        st = self._store.get((tenant_id, session_id))
        if st is None:
            return MemoryView()  # fresh session → true no-op
        window = tuple(st.messages[-(self._window_turns * 2) :])
        return MemoryView(window=window, case_state=tuple(st.facts.values()))

    def record_turn(
        self,
        *,
        tenant_id: str,
        session_id: str,
        question: str,
        answer: str,
        facts: tuple[RememberedFact, ...] = (),
    ) -> None:
        _require(tenant_id, session_id)
        st = self._state(tenant_id, session_id)
        st.turns += 1
        st.messages.append(Turn(role="user", text=question, index=len(st.messages)))
        st.messages.append(Turn(role="assistant", text=answer, index=len(st.messages)))
        for f in facts:
            # last value wins; re-stamp staleness to the current exchange (conservative merge).
            st.facts[f.feld] = RememberedFact(
                feld=f.feld, wert=f.wert, provenance=f.provenance, as_of_turn=st.turns
            )

    # --- history (layer 3) + session listing ---

    def history(self, *, tenant_id: str, session_id: str) -> tuple[Turn, ...]:
        _require(tenant_id, session_id)
        st = self._store.get((tenant_id, session_id))
        return tuple(st.messages) if st else ()

    def sessions(self, *, tenant_id: str) -> tuple[str, ...]:
        require_tenant(TenantContext(tenant_id))
        return tuple(s for (t, s) in self._store if t == tenant_id)

    # --- user control (build-spec §7: view / edit / delete / clear) ---

    def case_state(self, *, tenant_id: str, session_id: str) -> tuple[RememberedFact, ...]:
        _require(tenant_id, session_id)
        st = self._store.get((tenant_id, session_id))
        return tuple(st.facts.values()) if st else ()

    def edit_fact(self, *, tenant_id: str, session_id: str, feld: str, wert: str) -> None:
        _require(tenant_id, session_id)
        st = self._state(tenant_id, session_id)
        # a user edit is a stronger provenance than a distilled claim (honesty: reflect the source).
        st.facts[feld] = RememberedFact(
            feld=feld, wert=wert, provenance="user-edited", as_of_turn=st.turns
        )

    def delete_fact(self, *, tenant_id: str, session_id: str, feld: str) -> None:
        _require(tenant_id, session_id)
        st = self._store.get((tenant_id, session_id))
        if st:
            st.facts.pop(feld, None)

    def clear(self, *, tenant_id: str, session_id: str) -> None:
        _require(tenant_id, session_id)
        self._store.pop((tenant_id, session_id), None)


class InProcessCrossSessionMemory:
    """Trivial layer-4 impl (build-spec §7.4). The SEAM is complete; the LOGIC is DEFERRED — the
    cross-session sub-gate is the highest-stakes memory surface (durable cross-session isolation +
    curation + relevance retrieval). ``relevant_facts`` returns nothing (no curation, no relevance,
    no Qdrant); ``remember_durable`` stores tenant-scoped facts but nothing is injected back yet.
    Opens the door without taking on that surface before its dedicated review."""

    def __init__(self) -> None:
        self._durable: dict[str, list[RememberedFact]] = {}

    def relevant_facts(
        self, *, tenant_id: str, query: str, k: int = 5
    ) -> tuple[RememberedFact, ...]:
        require_tenant(TenantContext(tenant_id))  # P0 even while inert
        return ()  # DEFERRED: relevance retrieval is the cross-session sub-gate

    def remember_durable(
        self, *, tenant_id: str, facts: tuple[RememberedFact, ...]
    ) -> None:
        require_tenant(TenantContext(tenant_id))
        # stored tenant-scoped (P0) but intentionally never injected back yet.
        self._durable.setdefault(tenant_id, []).extend(facts)
