"""Wissens-Beitrag store — a user OPTS to share their worked-out situation + the real-world OUTCOME back
to sealingAI to improve the knowledge base. STRUCTURAL FIREWALL: a contribution is an untrusted DRAFT in
the owner/expert REVIEW QUEUE; it NEVER feeds the trust spine / grounding / produktspec automatically. The
only path into knowledge is the review gate (→ a field_validated Fachkarte, herstellerblind, or an eval-
trap). Anonymous contributions carry no identity (tenant_ref='anon', no subject); the structured case-state
is technical (physics, not PII). Mirrors the lead store (build-spec §3)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import V2Contribution


@dataclass(frozen=True)
class Contribution:
    anonym: bool
    tenant_ref: (
        str  # 'anon' when anonymous; else the originating tenant (provenance only)
    )
    subject_ref: str  # '' when anonymous; else the user subject (for owner follow-up)
    situation: str
    case_state_json: list
    recommendation: str
    outcome: str  # the real-world result — the field_validated gold
    created_at: str
    status: str = "neu"  # neu | reviewed | promoted | rejected
    review_note: str = ""
    id: int = 0


def _to_domain(r: V2Contribution) -> Contribution:
    return Contribution(
        id=r.id,
        anonym=r.anonym,
        tenant_ref=r.tenant_ref,
        subject_ref=r.subject_ref,
        situation=r.situation,
        case_state_json=list(r.case_state_json or []),
        recommendation=r.recommendation,
        outcome=r.outcome,
        created_at=r.created_at,
        status=r.status,
        review_note=r.review_note,
    )


class ContributionStore(Protocol):
    def store(self, c: Contribution) -> int: ...
    def list_all(self) -> tuple[Contribution, ...]: ...
    def set_status(
        self, contribution_id: int, status: str, review_note: str
    ) -> bool: ...


class InProcessContributionStore:
    def __init__(self) -> None:
        self._items: list[Contribution] = []

    def store(self, c: Contribution) -> int:
        new_id = len(self._items) + 1
        self._items.append(replace(c, id=new_id))
        return new_id

    def list_all(self) -> tuple[Contribution, ...]:
        return tuple(reversed(self._items))

    def set_status(self, contribution_id: int, status: str, review_note: str) -> bool:
        for i, c in enumerate(self._items):
            if c.id == contribution_id:
                self._items[i] = replace(c, status=status, review_note=review_note)
                return True
        return False


class PostgresContributionStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def store(self, c: Contribution) -> int:
        with self._sf() as s:
            row = V2Contribution(
                anonym=c.anonym,
                tenant_ref=c.tenant_ref,
                subject_ref=c.subject_ref,
                situation=c.situation,
                case_state_json=list(c.case_state_json),
                recommendation=c.recommendation,
                outcome=c.outcome,
                created_at=c.created_at,
                status=c.status,
                review_note=c.review_note,
            )
            s.add(row)
            s.commit()
            return row.id

    def list_all(self) -> tuple[Contribution, ...]:
        with self._sf() as s:
            rows = s.scalars(
                select(V2Contribution).order_by(V2Contribution.id.desc())
            ).all()
            return tuple(_to_domain(r) for r in rows)

    def set_status(self, contribution_id: int, status: str, review_note: str) -> bool:
        with self._sf() as s:
            row = s.get(V2Contribution, contribution_id)
            if row is None:
                return False
            row.status = status
            row.review_note = review_note
            s.commit()
            return True


def build_contribution_store(settings) -> ContributionStore:
    if getattr(settings, "database_url", None):
        from sealai_v2.db.engine import make_engine, make_sessionmaker

        return PostgresContributionStore(
            make_sessionmaker(make_engine(settings.database_url))
        )
    return InProcessContributionStore()
