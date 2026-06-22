"""``PostgresConversationMemory`` — durable layers 1-3 (build-spec §3/§7).

Implements the ``ConversationMemory`` Protocol (``recall`` + ``record_turn``) AND the wider
user-control + history surface the API uses (``history``/``sessions``/``case_state``/``edit_fact``/
``delete_fact``/``set_derived``/``derived_facts``/``clear``) — a faithful drop-in for
``InProcessConversationMemory`` with identical semantics: a bounded working window, full history,
last-value-wins case-state (re-stamped to the current exchange), and a SEPARATE derived channel.

Sync (the Protocol is sync). Tenant scope (P0) is enforced on every read/write — the same fail-closed
guard as the in-process store, so a cross-tenant read can never hit another tenant's state.
"""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.contracts import DerivedFact, MemoryView, RememberedFact, Turn
from sealai_v2.db.models import V2Derived, V2Fact, V2Message, V2Session
from sealai_v2.security.tenant import TenantContext, require_tenant


def _require(tenant_id: str, session_id: str) -> None:
    """Fail-closed scope guard (P0) — mirrors ``memory.store._require`` exactly."""
    require_tenant(TenantContext(tenant_id))  # raises on empty/blank tenant
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is mandatory (memory is per-session)")


def _ser_derived(d: DerivedFact) -> dict:
    return asdict(d)


def _deser_derived(raw: dict) -> DerivedFact:
    return DerivedFact(
        calc_id=raw["calc_id"],
        name=raw["name"],
        value=raw["value"],
        unit=raw["unit"],
        formula=raw.get("formula", ""),
        parent_fields=tuple(raw.get("parent_fields", ())),
        input_origins=tuple(raw.get("input_origins", ())),
        provenance=raw.get("provenance", "kernel_computed"),
    )


class PostgresConversationMemory:
    def __init__(self, session_factory: sessionmaker, *, window_turns: int = 6) -> None:
        self._window_turns = max(1, window_turns)
        self._sf = session_factory

    # --- hot path (pipeline-facing Protocol) ---

    def recall(self, *, tenant_id: str, session_id: str) -> MemoryView:
        _require(tenant_id, session_id)
        with self._sf() as s:
            msgs = (
                s.execute(
                    select(V2Message)
                    .where(
                        V2Message.tenant_id == tenant_id,
                        V2Message.session_id == session_id,
                    )
                    .order_by(V2Message.idx)
                )
                .scalars()
                .all()
            )
            facts = (
                s.execute(
                    select(V2Fact).where(
                        V2Fact.tenant_id == tenant_id, V2Fact.session_id == session_id
                    )
                )
                .scalars()
                .all()
            )
        if not msgs and not facts:
            return MemoryView()  # fresh session → true no-op
        window = tuple(
            Turn(role=m.role, text=m.text, index=m.idx)
            for m in msgs[-(self._window_turns * 2) :]
        )
        case_state = tuple(
            RememberedFact(
                feld=f.feld,
                wert=f.wert,
                provenance=f.provenance,
                as_of_turn=f.as_of_turn,
            )
            for f in facts
        )
        return MemoryView(window=window, case_state=case_state)

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
        with self._sf.begin() as s:
            sess = s.get(V2Session, (tenant_id, session_id))
            if sess is None:
                sess = V2Session(tenant_id=tenant_id, session_id=session_id, turns=0)
                s.add(sess)
            sess.turns += 1
            # next idx = current message count (messages are append-only per session; only
            # ``clear`` removes them, wholesale) — mirrors ``len(st.messages)`` in-process.
            n = s.execute(
                select(func.count())
                .select_from(V2Message)
                .where(
                    V2Message.tenant_id == tenant_id,
                    V2Message.session_id == session_id,
                )
            ).scalar_one()
            s.add(
                V2Message(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    idx=n,
                    role="user",
                    text=question,
                )
            )
            s.add(
                V2Message(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    idx=n + 1,
                    role="assistant",
                    text=answer,
                )
            )
            for f in facts:
                # last value wins; re-stamp staleness to the current exchange (conservative merge).
                self._upsert_fact(
                    s, tenant_id, session_id, f.feld, f.wert, f.provenance, sess.turns
                )

    # --- history (layer 3) + session listing ---

    def history(self, *, tenant_id: str, session_id: str) -> tuple[Turn, ...]:
        _require(tenant_id, session_id)
        with self._sf() as s:
            msgs = (
                s.execute(
                    select(V2Message)
                    .where(
                        V2Message.tenant_id == tenant_id,
                        V2Message.session_id == session_id,
                    )
                    .order_by(V2Message.idx)
                )
                .scalars()
                .all()
            )
        return tuple(Turn(role=m.role, text=m.text, index=m.idx) for m in msgs)

    def sessions(self, *, tenant_id: str) -> tuple[str, ...]:
        require_tenant(TenantContext(tenant_id))
        with self._sf() as s:
            rows = s.execute(
                select(V2Session.session_id)
                .where(V2Session.tenant_id == tenant_id)
                .order_by(V2Session.session_id)
            ).all()
        return tuple(r[0] for r in rows)

    # --- user control (build-spec §7: view / edit / delete / clear) ---

    def case_state(
        self, *, tenant_id: str, session_id: str
    ) -> tuple[RememberedFact, ...]:
        _require(tenant_id, session_id)
        with self._sf() as s:
            facts = (
                s.execute(
                    select(V2Fact).where(
                        V2Fact.tenant_id == tenant_id, V2Fact.session_id == session_id
                    )
                )
                .scalars()
                .all()
            )
        return tuple(
            RememberedFact(
                feld=f.feld,
                wert=f.wert,
                provenance=f.provenance,
                as_of_turn=f.as_of_turn,
            )
            for f in facts
        )

    def edit_fact(
        self,
        *,
        tenant_id: str,
        session_id: str,
        feld: str,
        wert: str,
        provenance: str = "user-edited",
    ) -> None:
        _require(tenant_id, session_id)
        with self._sf.begin() as s:
            sess = s.get(V2Session, (tenant_id, session_id))
            turns = sess.turns if sess is not None else 0
            self._upsert_fact(s, tenant_id, session_id, feld, wert, provenance, turns)

    def delete_fact(self, *, tenant_id: str, session_id: str, feld: str) -> None:
        _require(tenant_id, session_id)
        with self._sf.begin() as s:
            s.execute(
                delete(V2Fact).where(
                    V2Fact.tenant_id == tenant_id,
                    V2Fact.session_id == session_id,
                    V2Fact.feld == feld,
                )
            )

    # --- M8 derived slice (kernel_computed values — a SEPARATE, backend-only channel) ---

    def set_derived(
        self, *, tenant_id: str, session_id: str, derived: tuple[DerivedFact, ...]
    ) -> None:
        """Wholesale replace the derived slice from a fresh recompute — a stale kernel value can
        never persist. Backend-only: no client path reaches it."""
        _require(tenant_id, session_id)
        payload = [_ser_derived(d) for d in derived]
        with self._sf.begin() as s:
            row = s.get(V2Derived, (tenant_id, session_id))
            if row is None:
                s.add(
                    V2Derived(
                        tenant_id=tenant_id, session_id=session_id, slice_json=payload
                    )
                )
            else:
                row.slice_json = payload

    def derived_facts(
        self, *, tenant_id: str, session_id: str
    ) -> tuple[DerivedFact, ...]:
        _require(tenant_id, session_id)
        with self._sf() as s:
            row = s.get(V2Derived, (tenant_id, session_id))
            payload = list(row.slice_json) if row is not None else []
        return tuple(_deser_derived(r) for r in payload)

    def clear(self, *, tenant_id: str, session_id: str) -> None:
        _require(tenant_id, session_id)
        with self._sf.begin() as s:
            for model in (V2Message, V2Fact, V2Derived, V2Session):
                s.execute(
                    delete(model).where(
                        model.tenant_id == tenant_id, model.session_id == session_id
                    )
                )

    # --- internal ---

    @staticmethod
    def _upsert_fact(
        s,
        tenant_id: str,
        session_id: str,
        feld: str,
        wert: str,
        provenance: str,
        as_of_turn: int,
    ) -> None:
        row = s.get(V2Fact, (tenant_id, session_id, feld))
        if row is None:
            s.add(
                V2Fact(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    feld=feld,
                    wert=wert,
                    provenance=provenance,
                    as_of_turn=as_of_turn,
                )
            )
        else:
            row.wert = wert
            row.provenance = provenance
            row.as_of_turn = as_of_turn
