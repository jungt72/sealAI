"""Governed contribution store with bounded keyset reads and withdrawal quarantine.

Every new contribution is tenant/actor owned, content-bounded, explicitly untrusted, and held in a
review quarantine. Anonymous mode hides the subject from the owner-facing provenance field; the
one-way owner reference remains so only the submitting actor can withdraw it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.api.pagination import KeysetPage, encode_cursor
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.models import (
    V2ApiLifecycleEvent,
    V2ApiLifecycleReceipt,
    V2Contribution,
)
from sealai_v2.security.lifecycle_control import (
    idempotency_key_hash,
    identity_scope_refs,
)
from sealai_v2.security.lifecycle_receipts import (
    LifecycleReceipt,
    sign_lifecycle_transition,
)

_VISIBLE_STATES = ("quarantined", "review_quarantined")
_COMPATIBILITY_PAGE_LIMIT = 100


class LifecycleTransitionConflict(RuntimeError):
    pass


class LifecycleTransitionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Contribution:
    admission_request_id: str
    anonym: bool
    tenant_ref: str
    subject_ref: str
    owner_subject_ref: str
    situation: str
    case_state_json: list
    recommendation: str
    outcome: str
    policy_authority_ref: str
    purpose_version: str
    consent_version: str
    rights_basis: str
    license_id: str
    provenance: str
    document_type: str
    pii_classification: str
    prompt_trust: str
    prompt_injection_signal: bool
    content_bytes: int
    created_at: str
    retention_review_after: str | None = None
    lifecycle_state: str = "quarantined"
    quarantine_reason: str = "intake_review_required"
    status: str = "pending"
    review_note: str = ""
    withdrawn_at: str | None = None
    id: int = 0


def _to_domain(row: V2Contribution) -> Contribution:
    return Contribution(
        id=row.id,
        admission_request_id=row.admission_request_id or "",
        anonym=row.anonym,
        tenant_ref=row.tenant_ref,
        subject_ref=row.subject_ref,
        owner_subject_ref=row.owner_subject_ref or "",
        situation=row.situation,
        case_state_json=list(row.case_state_json or []),
        recommendation=row.recommendation,
        outcome=row.outcome,
        policy_authority_ref=row.policy_authority_ref or "",
        purpose_version=row.purpose_version or "",
        consent_version=row.consent_version or "",
        rights_basis=row.rights_basis or "",
        license_id=row.license_id or "",
        provenance=row.provenance or "",
        document_type=row.document_type or "",
        pii_classification=row.pii_classification or "",
        prompt_trust=row.prompt_trust or "",
        prompt_injection_signal=bool(row.prompt_injection_signal),
        lifecycle_state=row.lifecycle_state or "legacy_unresolved",
        quarantine_reason=row.quarantine_reason or "",
        content_bytes=int(row.content_bytes or 0),
        retention_review_after=row.retention_review_after,
        withdrawn_at=row.withdrawn_at,
        created_at=row.created_at,
        status=row.status,
        review_note=row.review_note,
    )


def _receipt_from_row(row: V2ApiLifecycleReceipt, *, replay: bool) -> LifecycleReceipt:
    return LifecycleReceipt(
        receipt_id=row.receipt_id,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        reason_code=row.reason_code,
        policy_authority_ref=row.policy_authority_ref,
        lifecycle_state=row.lifecycle_state,
        issued_at=row.issued_at,
        receipt_digest=row.receipt_digest,
        replay=replay,
    )


def _validate_new_contribution(c: Contribution) -> None:
    required = (
        c.admission_request_id,
        c.tenant_ref,
        c.owner_subject_ref,
        c.policy_authority_ref,
        c.purpose_version,
        c.consent_version,
        c.rights_basis,
        c.license_id,
        c.provenance,
        c.document_type,
        c.pii_classification,
    )
    if any(not value.strip() for value in required):
        raise ValueError("new contribution is missing governance authority")
    if c.prompt_trust != "untrusted" or c.lifecycle_state != "quarantined":
        raise ValueError("new contribution must enter the untrusted quarantine")
    if c.content_bytes <= 0:
        raise ValueError("new contribution content size must be positive")


class ContributionStore(Protocol):
    def store(self, contribution: Contribution) -> int: ...

    def page(
        self, *, before_id: int | None, limit: int
    ) -> KeysetPage[Contribution]: ...

    def get_owned(
        self, contribution_id: int, identity: VerifiedIdentity
    ) -> Contribution | None: ...

    def withdraw(
        self,
        contribution_id: int,
        identity: VerifiedIdentity,
        *,
        idempotency_key: str,
        reason_code: str,
        now: datetime | None = None,
    ) -> LifecycleReceipt | None: ...

    def set_status(
        self, contribution_id: int, status: str, review_note: str
    ) -> bool: ...


class InProcessContributionStore:
    def __init__(
        self,
        *,
        receipt_secret: str | None = None,
        policy_authority_ref: str | None = None,
    ) -> None:
        self._items: list[Contribution] = []
        self._receipts: dict[tuple[int, str], LifecycleReceipt] = {}
        self._lock = threading.RLock()
        self._receipt_secret = receipt_secret
        self._policy_authority_ref = policy_authority_ref

    def store(self, contribution: Contribution) -> int:
        _validate_new_contribution(contribution)
        with self._lock:
            existing = next(
                (
                    item
                    for item in self._items
                    if item.admission_request_id == contribution.admission_request_id
                ),
                None,
            )
            if existing is not None:
                return existing.id
            new_id = len(self._items) + 1
            self._items.append(replace(contribution, id=new_id))
            return new_id

    def page(self, *, before_id: int | None, limit: int) -> KeysetPage[Contribution]:
        if not 1 <= limit <= 100:
            raise ValueError("contribution page limit must be between 1 and 100")
        with self._lock:
            rows = sorted(self._items, key=lambda item: item.id, reverse=True)
            rows = [
                item
                for item in rows
                if item.lifecycle_state in _VISIBLE_STATES
                and (before_id is None or item.id < before_id)
            ][: limit + 1]
            has_more = len(rows) > limit
            selected = tuple(rows[:limit])
            return KeysetPage(
                selected,
                encode_cursor(selected[-1].id) if has_more and selected else None,
            )

    def list_all(self) -> tuple[Contribution, ...]:
        """Bounded compatibility helper for older hermetic tests; API routes use ``page``."""
        return self.page(before_id=None, limit=_COMPATIBILITY_PAGE_LIMIT).items

    def get_owned(
        self, contribution_id: int, identity: VerifiedIdentity
    ) -> Contribution | None:
        _, actor_ref = identity_scope_refs(identity)
        with self._lock:
            return next(
                (
                    item
                    for item in self._items
                    if item.id == contribution_id
                    and item.tenant_ref == identity.tenant_id
                    and item.owner_subject_ref == actor_ref
                ),
                None,
            )

    def withdraw(
        self,
        contribution_id: int,
        identity: VerifiedIdentity,
        *,
        idempotency_key: str,
        reason_code: str,
        now: datetime | None = None,
    ) -> LifecycleReceipt | None:
        if not self._receipt_secret or not self._policy_authority_ref:
            raise LifecycleTransitionUnavailable(
                "withdrawal receipt authority unavailable"
            )
        tenant_ref, actor_ref = identity_scope_refs(identity)
        idem_hash = idempotency_key_hash("contribution.withdraw", idempotency_key)
        key = (contribution_id, idem_hash)
        with self._lock:
            prior = self._receipts.get(key)
            if prior is not None:
                if prior.reason_code != reason_code:
                    raise LifecycleTransitionConflict("idempotency key payload changed")
                return replace(prior, replay=True)
            for index, item in enumerate(self._items):
                if (
                    item.id != contribution_id
                    or item.tenant_ref != identity.tenant_id
                    or item.owner_subject_ref != actor_ref
                ):
                    continue
                if item.lifecycle_state == "withdrawn_quarantined":
                    raise LifecycleTransitionConflict("contribution already withdrawn")
                transition = sign_lifecycle_transition(
                    secret=self._receipt_secret,
                    action="contribution.withdraw",
                    idempotency_key=idempotency_key,
                    resource_type="contribution",
                    resource_id=str(contribution_id),
                    tenant_id=identity.tenant_id,
                    tenant_ref=tenant_ref,
                    actor_ref=actor_ref,
                    event_type="withdrawal",
                    from_state=item.lifecycle_state,
                    to_state="withdrawn_quarantined",
                    reason_code=reason_code,
                    policy_authority_ref=self._policy_authority_ref,
                    now=now,
                )
                self._items[index] = replace(
                    item,
                    lifecycle_state="withdrawn_quarantined",
                    quarantine_reason=reason_code,
                    withdrawn_at=transition.receipt.issued_at,
                    status="withdrawn",
                )
                self._receipts[key] = transition.receipt
                return transition.receipt
        return None

    def set_status(self, contribution_id: int, status: str, review_note: str) -> bool:
        with self._lock:
            for index, contribution in enumerate(self._items):
                if contribution.id != contribution_id:
                    continue
                if contribution.lifecycle_state not in _VISIBLE_STATES:
                    return False
                self._items[index] = replace(
                    contribution,
                    status=status,
                    lifecycle_state="review_quarantined",
                    review_note=review_note,
                )
                return True
        return False


class PostgresContributionStore:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        receipt_secret: str | None = None,
        policy_authority_ref: str | None = None,
    ) -> None:
        self._sf = session_factory
        self._receipt_secret = receipt_secret
        self._policy_authority_ref = policy_authority_ref

    def store(self, contribution: Contribution) -> int:
        _validate_new_contribution(contribution)
        with self._sf() as session:
            existing_id = session.scalar(
                select(V2Contribution.id).where(
                    V2Contribution.admission_request_id
                    == contribution.admission_request_id
                )
            )
            if existing_id is not None:
                return int(existing_id)
            row = V2Contribution(
                admission_request_id=contribution.admission_request_id,
                anonym=contribution.anonym,
                tenant_ref=contribution.tenant_ref,
                subject_ref=contribution.subject_ref,
                owner_subject_ref=contribution.owner_subject_ref,
                situation=contribution.situation,
                case_state_json=list(contribution.case_state_json),
                recommendation=contribution.recommendation,
                outcome=contribution.outcome,
                policy_authority_ref=contribution.policy_authority_ref,
                purpose_version=contribution.purpose_version,
                consent_version=contribution.consent_version,
                rights_basis=contribution.rights_basis,
                license_id=contribution.license_id,
                provenance=contribution.provenance,
                document_type=contribution.document_type,
                pii_classification=contribution.pii_classification,
                prompt_trust=contribution.prompt_trust,
                prompt_injection_signal=contribution.prompt_injection_signal,
                lifecycle_state=contribution.lifecycle_state,
                quarantine_reason=contribution.quarantine_reason,
                content_bytes=contribution.content_bytes,
                retention_review_after=contribution.retention_review_after,
                withdrawn_at=contribution.withdrawn_at,
                created_at=contribution.created_at,
                status=contribution.status,
                review_note=contribution.review_note,
            )
            session.add(row)
            session.commit()
            return row.id

    def page(self, *, before_id: int | None, limit: int) -> KeysetPage[Contribution]:
        if not 1 <= limit <= 100:
            raise ValueError("contribution page limit must be between 1 and 100")
        with self._sf() as session:
            query = select(V2Contribution).where(
                V2Contribution.lifecycle_state.in_(_VISIBLE_STATES),
                V2Contribution.owner_subject_ref.is_not(None),
                V2Contribution.policy_authority_ref.is_not(None),
            )
            if before_id is not None:
                query = query.where(V2Contribution.id < before_id)
            rows = session.scalars(
                query.order_by(V2Contribution.id.desc()).limit(limit + 1)
            ).all()
            has_more = len(rows) > limit
            selected = tuple(_to_domain(row) for row in rows[:limit])
            return KeysetPage(
                selected,
                encode_cursor(selected[-1].id) if has_more and selected else None,
            )

    def list_all(self) -> tuple[Contribution, ...]:
        """Bounded compatibility helper; production routes use keyset pagination."""
        return self.page(before_id=None, limit=_COMPATIBILITY_PAGE_LIMIT).items

    def get_owned(
        self, contribution_id: int, identity: VerifiedIdentity
    ) -> Contribution | None:
        _, actor_ref = identity_scope_refs(identity)
        with self._sf() as session:
            row = session.scalar(
                select(V2Contribution).where(
                    V2Contribution.id == contribution_id,
                    V2Contribution.tenant_ref == identity.tenant_id,
                    V2Contribution.owner_subject_ref == actor_ref,
                )
            )
            return _to_domain(row) if row is not None else None

    def withdraw(
        self,
        contribution_id: int,
        identity: VerifiedIdentity,
        *,
        idempotency_key: str,
        reason_code: str,
        now: datetime | None = None,
    ) -> LifecycleReceipt | None:
        if not self._receipt_secret or not self._policy_authority_ref:
            raise LifecycleTransitionUnavailable(
                "withdrawal receipt authority unavailable"
            )
        tenant_ref, actor_ref = identity_scope_refs(identity)
        idem_hash = idempotency_key_hash("contribution.withdraw", idempotency_key)
        with self._sf() as session, session.begin():
            prior = session.scalar(
                select(V2ApiLifecycleReceipt).where(
                    V2ApiLifecycleReceipt.resource_type == "contribution",
                    V2ApiLifecycleReceipt.resource_id == str(contribution_id),
                    V2ApiLifecycleReceipt.idempotency_key_hash == idem_hash,
                )
            )
            if prior is not None:
                if prior.reason_code != reason_code:
                    raise LifecycleTransitionConflict("idempotency key payload changed")
                return _receipt_from_row(prior, replay=True)
            row = session.scalar(
                select(V2Contribution)
                .where(
                    V2Contribution.id == contribution_id,
                    V2Contribution.tenant_ref == identity.tenant_id,
                    V2Contribution.owner_subject_ref == actor_ref,
                )
                .with_for_update()
            )
            if row is None:
                return None
            if row.lifecycle_state == "withdrawn_quarantined":
                raise LifecycleTransitionConflict("contribution already withdrawn")
            transition = sign_lifecycle_transition(
                secret=self._receipt_secret,
                action="contribution.withdraw",
                idempotency_key=idempotency_key,
                resource_type="contribution",
                resource_id=str(contribution_id),
                tenant_id=identity.tenant_id,
                tenant_ref=tenant_ref,
                actor_ref=actor_ref,
                event_type="withdrawal",
                from_state=row.lifecycle_state or "legacy_unresolved",
                to_state="withdrawn_quarantined",
                reason_code=reason_code,
                policy_authority_ref=self._policy_authority_ref,
                now=now,
            )
            row.lifecycle_state = "withdrawn_quarantined"
            row.quarantine_reason = reason_code
            row.withdrawn_at = transition.receipt.issued_at
            row.status = "withdrawn"
            session.add(
                V2ApiLifecycleReceipt(
                    receipt_id=transition.receipt.receipt_id,
                    resource_type=transition.receipt.resource_type,
                    resource_id=transition.receipt.resource_id,
                    tenant_ref=transition.tenant_ref,
                    actor_ref=transition.actor_ref,
                    idempotency_key_hash=transition.idempotency_hash,
                    reason_code=transition.receipt.reason_code,
                    policy_authority_ref=transition.receipt.policy_authority_ref,
                    lifecycle_state=transition.receipt.lifecycle_state,
                    issued_at=transition.receipt.issued_at,
                    receipt_digest=transition.receipt.receipt_digest,
                )
            )
            session.add(V2ApiLifecycleEvent(**transition.event.__dict__))
            return transition.receipt

    def set_status(self, contribution_id: int, status: str, review_note: str) -> bool:
        with self._sf() as session:
            row = session.get(V2Contribution, contribution_id)
            if row is None or row.lifecycle_state not in _VISIBLE_STATES:
                return False
            row.status = status
            row.lifecycle_state = "review_quarantined"
            row.review_note = review_note
            session.commit()
            return True


def build_contribution_store(settings) -> ContributionStore:
    secret = (
        settings.api_lifecycle_receipt_hmac_secret.get_secret_value()
        if getattr(settings, "api_lifecycle_receipt_hmac_secret", None) is not None
        else None
    )
    policy_ref = getattr(settings, "api_lifecycle_policy_authority_ref", None)
    if getattr(settings, "database_url", None):
        from sealai_v2.db.engine import make_api_sessionmaker

        return PostgresContributionStore(
            make_api_sessionmaker(settings),
            receipt_secret=secret,
            policy_authority_ref=policy_ref,
        )
    return InProcessContributionStore(
        receipt_secret=secret,
        policy_authority_ref=policy_ref,
    )
