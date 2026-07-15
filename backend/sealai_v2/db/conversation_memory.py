"""``PostgresConversationMemory`` — durable layers 1-3 (build-spec §3/§7).

Implements the ``ConversationMemory`` Protocol (``recall`` + ``record_turn``) AND the wider
user-control + history surface the API uses (``history``/``sessions``/``case_state``/``edit_fact``/
``delete_fact``/``set_derived``/``derived_facts``/``clear``) — a faithful drop-in for
``InProcessConversationMemory`` with identical semantics: a bounded working window, full history,
last-value-wins case-state (re-stamped to the current exchange), and a SEPARATE derived channel.

Sync (the Protocol is sync). Tenant scope (P0) is enforced on every read/write — the same fail-closed
guard as the in-process store, so a cross-tenant read can never hit another tenant's state.

"Fälle"-Sidebar (Patch A): ``record_turn`` gains an optional ``now`` (ISO-8601 string, caller-
supplied — no DB-side clock read here) to stamp ``V2Session.created_at``/``title`` on the FIRST
turn and bump ``updated_at`` on every turn. ``sessions()`` now returns ``SessionSummary`` tuples
(``case_id``/``title``/``created_at``/``updated_at``) instead of bare id strings, so a "Fälle" list
UI has display-ready metadata without a per-session follow-up fetch.
"""

from __future__ import annotations

from dataclasses import asdict

from dataclasses import replace

from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.contracts import (
    ArtifactCaseSnapshot,
    CaseRevisionConflict,
    ConversationAccessDenied,
    DerivedFact,
    MemoryView,
    RememberedFact,
    SessionSummary,
    Turn,
)
from sealai_v2.core.case_state import CaseStateV2
from sealai_v2.db.models import V2Derived, V2Fact, V2Message, V2Session
from sealai_v2.security.tenant import TenantContext, require_tenant

_TITLE_MAX_LEN = 60


def _remembered_fact(row: V2Fact) -> RememberedFact:
    return RememberedFact(
        feld=row.feld,
        wert=row.wert,
        provenance=row.provenance,
        as_of_turn=row.as_of_turn,
        unit=row.unit,
        status=row.status,
        source_ref=row.source_ref,
        observed_at=row.observed_at,
        document_id=row.document_id,
        document_version=row.document_version,
        page=row.page,
        bbox=tuple(row.bbox) if row.bbox is not None else None,
        confidence=row.confidence,
    )


def _require(tenant_id: str, session_id: str) -> None:
    """Fail-closed scope guard (P0) — mirrors ``memory.store._require`` exactly."""
    require_tenant(TenantContext(tenant_id))  # raises on empty/blank tenant
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is mandatory (memory is per-session)")


def _ser_derived(d: DerivedFact) -> dict:
    return asdict(d)


def _title_from_question(question: str) -> str:
    """The "Fälle"-Sidebar title heuristic (Patch A): first ~60 chars of the first user message,
    whitespace-normalized — no LLM call, matches ChatGPT's own convention. Truncation never lands
    mid-word where avoidable (trims back to the last space within the limit)."""
    normalized = " ".join(question.split())
    if len(normalized) <= _TITLE_MAX_LEN:
        return normalized
    cut = normalized[:_TITLE_MAX_LEN]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut + "…"


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

    @staticmethod
    def _assert_owner(
        session_row: V2Session | None,
        owner_subject: str,
        *,
        allow_missing: bool = False,
    ) -> None:
        if not owner_subject:
            return
        if session_row is None:
            if allow_missing:
                return
            raise ConversationAccessDenied("conversation not found")
        if (
            session_row.owner_subject != owner_subject
            or session_row.ownership_state != "owned"
        ):
            raise ConversationAccessDenied("conversation not found")

    def assert_session_access(
        self, *, tenant_id: str, session_id: str, owner_subject: str
    ) -> None:
        _require(tenant_id, session_id)
        with self._sf() as s:
            self._assert_owner(s.get(V2Session, (tenant_id, session_id)), owner_subject)

    @staticmethod
    def _orphan_payload_exists(session, tenant_id: str, session_id: str) -> bool:
        """Detect legacy child rows before a new owner-bound parent could be created.

        A caller may create a genuinely new case, but it must never implicitly claim orphaned
        messages/facts/derived state. Those rows stay inaccessible until GATE-07 quarantine and a
        separately reviewed mapping.
        """

        return any(
            session.scalar(
                select(model)
                .where(
                    model.tenant_id == tenant_id,
                    model.session_id == session_id,
                )
                .limit(1)
            )
            is not None
            for model in (V2Message, V2Fact, V2Derived)
        )

    # --- hot path (pipeline-facing Protocol) ---

    def recall(
        self, *, tenant_id: str, session_id: str, owner_subject: str = ""
    ) -> MemoryView:
        _require(tenant_id, session_id)
        with self._sf() as s:
            session_row = s.get(V2Session, (tenant_id, session_id))
            self._assert_owner(session_row, owner_subject, allow_missing=True)
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
        if owner_subject and session_row is None and (msgs or facts):
            raise ConversationAccessDenied("conversation not found")
        if not msgs and not facts:
            return MemoryView()  # fresh session → true no-op
        window = tuple(
            Turn(role=m.role, text=m.text, index=m.idx)
            for m in msgs[-(self._window_turns * 2) :]
        )
        case_state = tuple(_remembered_fact(f) for f in facts)
        revision = session_row.case_revision if session_row is not None else 0
        return MemoryView(
            window=window,
            case_state=case_state,
            case_state_v2=CaseStateV2.from_remembered_facts(
                case_id=session_id, revision=revision, facts=case_state
            ),
        )

    def artifact_snapshot(
        self,
        *,
        tenant_id: str,
        session_id: str,
        owner_subject: str,
        expected_case_revision: int,
    ) -> ArtifactCaseSnapshot:
        """Read a complete turn under a shared row lock; never mutates the case."""

        _require(tenant_id, session_id)
        with self._sf.begin() as session:
            session_row = session.scalar(
                select(V2Session)
                .where(
                    V2Session.tenant_id == tenant_id,
                    V2Session.session_id == session_id,
                    V2Session.owner_subject == owner_subject,
                    V2Session.ownership_state == "owned",
                )
                .with_for_update(read=True)
            )
            if session_row is None:
                raise ConversationAccessDenied("conversation not found")
            if session_row.case_revision != expected_case_revision:
                raise CaseRevisionConflict(
                    f"expected case revision {expected_case_revision}, "
                    f"got {session_row.case_revision}"
                )
            rows = session.scalars(
                select(V2Message)
                .where(
                    V2Message.tenant_id == tenant_id,
                    V2Message.session_id == session_id,
                )
                .order_by(V2Message.idx.desc())
                .limit(2)
            ).all()
            if len(rows) != 2:
                raise ConversationAccessDenied("conversation not found")
            answer, question = rows
            if question.role != "user" or answer.role != "assistant":
                raise ConversationAccessDenied("conversation has no complete turn")
            return ArtifactCaseSnapshot(
                case_id=session_id,
                case_revision=session_row.case_revision,
                message_index=answer.idx,
                question=question.text,
                answer=answer.text,
            )

    def record_turn(
        self,
        *,
        tenant_id: str,
        session_id: str,
        question: str,
        answer: str,
        facts: tuple[RememberedFact, ...] = (),
        now: str | None = None,
        expected_case_revision: int | None = None,
        owner_subject: str = "",
    ) -> None:
        _require(tenant_id, session_id)
        with self._sf.begin() as s:
            sess = s.scalar(
                select(V2Session)
                .where(
                    V2Session.tenant_id == tenant_id,
                    V2Session.session_id == session_id,
                )
                .with_for_update()
            )
            if sess is None:
                if owner_subject and self._orphan_payload_exists(
                    s, tenant_id, session_id
                ):
                    raise ConversationAccessDenied("conversation not found")
                if expected_case_revision not in (None, 0):
                    raise CaseRevisionConflict(
                        f"expected case revision {expected_case_revision}, got 0"
                    )
                sess = V2Session(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    turns=0,
                    case_revision=0,
                    owner_subject=owner_subject or None,
                    ownership_state="owned",
                    created_at=now,
                    title=_title_from_question(question) if now else None,
                )
                s.add(sess)
            else:
                self._assert_owner(sess, owner_subject)
            if (
                expected_case_revision is not None
                and sess.case_revision != expected_case_revision
            ):
                raise CaseRevisionConflict(
                    f"expected case revision {expected_case_revision}, got {sess.case_revision}"
                )
            if now is not None:
                sess.updated_at = now
            sess.turns += 1
            if facts:
                sess.case_revision += 1
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
                    s,
                    tenant_id,
                    session_id,
                    replace(f, as_of_turn=sess.turns),
                )

    def merge_facts(
        self,
        *,
        tenant_id: str,
        session_id: str,
        facts: tuple[RememberedFact, ...],
        expected_case_revision: int | None = None,
        owner_subject: str = "",
    ) -> int:
        _require(tenant_id, session_id)
        with self._sf.begin() as s:
            sess = s.scalar(
                select(V2Session)
                .where(
                    V2Session.tenant_id == tenant_id,
                    V2Session.session_id == session_id,
                )
                .with_for_update()
            )
            actual = sess.case_revision if sess is not None else 0
            self._assert_owner(sess, owner_subject, allow_missing=True)
            if expected_case_revision is not None and actual != expected_case_revision:
                raise CaseRevisionConflict(
                    f"expected case revision {expected_case_revision}, got {actual}"
                )
            if sess is None:
                if owner_subject and self._orphan_payload_exists(
                    s, tenant_id, session_id
                ):
                    raise ConversationAccessDenied("conversation not found")
                sess = V2Session(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    turns=0,
                    case_revision=0,
                    owner_subject=owner_subject or None,
                    ownership_state="owned",
                )
                s.add(sess)
            if facts:
                sess.case_revision += 1
                for fact in facts:
                    self._upsert_fact(
                        s,
                        tenant_id,
                        session_id,
                        replace(fact, as_of_turn=sess.turns),
                    )
            return sess.case_revision

    # --- history (layer 3) + session listing ---

    def history(
        self, *, tenant_id: str, session_id: str, owner_subject: str = ""
    ) -> tuple[Turn, ...]:
        _require(tenant_id, session_id)
        with self._sf() as s:
            session_row = s.get(V2Session, (tenant_id, session_id))
            self._assert_owner(session_row, owner_subject, allow_missing=True)
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
            if owner_subject and session_row is None and msgs:
                raise ConversationAccessDenied("conversation not found")
        return tuple(Turn(role=m.role, text=m.text, index=m.idx) for m in msgs)

    def sessions(
        self, *, tenant_id: str, owner_subject: str = ""
    ) -> tuple[SessionSummary, ...]:
        require_tenant(TenantContext(tenant_id))
        with self._sf() as s:
            query = select(V2Session).where(V2Session.tenant_id == tenant_id)
            if owner_subject:
                query = query.where(
                    V2Session.owner_subject == owner_subject,
                    V2Session.ownership_state == "owned",
                )
            rows = s.scalars(
                query.order_by(
                    V2Session.updated_at.desc().nullslast(), V2Session.session_id
                )
            ).all()
        return tuple(
            SessionSummary(
                case_id=r.session_id,
                title=r.title,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        )

    # --- user control (build-spec §7: view / edit / delete / clear) ---

    def case_state(
        self, *, tenant_id: str, session_id: str, owner_subject: str = ""
    ) -> tuple[RememberedFact, ...]:
        _require(tenant_id, session_id)
        with self._sf() as s:
            session_row = s.get(V2Session, (tenant_id, session_id))
            self._assert_owner(session_row, owner_subject, allow_missing=True)
            facts = (
                s.execute(
                    select(V2Fact).where(
                        V2Fact.tenant_id == tenant_id, V2Fact.session_id == session_id
                    )
                )
                .scalars()
                .all()
            )
            if owner_subject and session_row is None and facts:
                raise ConversationAccessDenied("conversation not found")
        return tuple(_remembered_fact(f) for f in facts)

    def edit_fact(
        self,
        *,
        tenant_id: str,
        session_id: str,
        feld: str,
        wert: str,
        provenance: str = "user-edited",
        owner_subject: str = "",
    ) -> None:
        _require(tenant_id, session_id)
        with self._sf.begin() as s:
            sess = s.scalar(
                select(V2Session)
                .where(
                    V2Session.tenant_id == tenant_id,
                    V2Session.session_id == session_id,
                )
                .with_for_update()
            )
            if sess is None:
                if owner_subject and self._orphan_payload_exists(
                    s, tenant_id, session_id
                ):
                    raise ConversationAccessDenied("conversation not found")
                sess = V2Session(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    turns=0,
                    case_revision=0,
                    owner_subject=owner_subject or None,
                    ownership_state="owned",
                )
                s.add(sess)
            else:
                self._assert_owner(sess, owner_subject)
            self._upsert_fact(
                s,
                tenant_id,
                session_id,
                RememberedFact(
                    feld=feld,
                    wert=wert,
                    provenance=provenance,
                    as_of_turn=sess.turns,
                    status="confirmed",
                ),
            )
            sess.case_revision += 1

    def delete_fact(
        self, *, tenant_id: str, session_id: str, feld: str, owner_subject: str = ""
    ) -> None:
        _require(tenant_id, session_id)
        with self._sf.begin() as s:
            sess = s.scalar(
                select(V2Session)
                .where(
                    V2Session.tenant_id == tenant_id,
                    V2Session.session_id == session_id,
                )
                .with_for_update()
            )
            self._assert_owner(sess, owner_subject)
            result = s.execute(
                delete(V2Fact).where(
                    V2Fact.tenant_id == tenant_id,
                    V2Fact.session_id == session_id,
                    V2Fact.feld == feld,
                )
            )
            if result.rowcount and sess is not None:
                sess.case_revision += 1

    # --- M8 derived slice (kernel_computed values — a SEPARATE, backend-only channel) ---

    def set_derived(
        self,
        *,
        tenant_id: str,
        session_id: str,
        derived: tuple[DerivedFact, ...],
        owner_subject: str = "",
    ) -> None:
        """Wholesale replace the derived slice from a fresh recompute — a stale kernel value can
        never persist. Backend-only: no client path reaches it."""
        _require(tenant_id, session_id)
        payload = [_ser_derived(d) for d in derived]
        with self._sf.begin() as s:
            self._assert_owner(s.get(V2Session, (tenant_id, session_id)), owner_subject)
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
        self, *, tenant_id: str, session_id: str, owner_subject: str = ""
    ) -> tuple[DerivedFact, ...]:
        _require(tenant_id, session_id)
        with self._sf() as s:
            session_row = s.get(V2Session, (tenant_id, session_id))
            self._assert_owner(session_row, owner_subject, allow_missing=True)
            row = s.get(V2Derived, (tenant_id, session_id))
            if owner_subject and session_row is None and row is not None:
                raise ConversationAccessDenied("conversation not found")
            payload = list(row.slice_json) if row is not None else []
        return tuple(_deser_derived(r) for r in payload)

    def clear(
        self, *, tenant_id: str, session_id: str, owner_subject: str = ""
    ) -> None:
        _require(tenant_id, session_id)
        with self._sf.begin() as s:
            self._assert_owner(s.get(V2Session, (tenant_id, session_id)), owner_subject)
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
        fact: RememberedFact,
    ) -> None:
        values = {
            "wert": fact.wert,
            "provenance": fact.provenance,
            "as_of_turn": fact.as_of_turn,
            "unit": fact.unit,
            "status": fact.status,
            "source_ref": fact.source_ref,
            "observed_at": fact.observed_at,
            "document_id": fact.document_id,
            "document_version": fact.document_version,
            "page": fact.page,
            "bbox": list(fact.bbox) if fact.bbox is not None else None,
            "confidence": fact.confidence,
        }
        row = s.get(V2Fact, (tenant_id, session_id, fact.feld))
        if row is None:
            s.add(
                V2Fact(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    feld=fact.feld,
                    **values,
                )
            )
        else:
            for key, value in values.items():
                setattr(row, key, value)
