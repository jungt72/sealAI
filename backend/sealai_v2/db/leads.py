"""Tenant-owned RFQ lead store with bounded keyset reads and cancellation quarantine."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.api.pagination import KeysetPage, encode_cursor
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.contributions import (
    LifecycleTransitionConflict,
    LifecycleTransitionUnavailable,
)
from sealai_v2.db.models import V2ApiLifecycleEvent, V2ApiLifecycleReceipt, V2Lead
from sealai_v2.security.lifecycle_control import (
    idempotency_key_hash,
    identity_scope_refs,
)
from sealai_v2.security.lifecycle_receipts import (
    LifecycleReceipt,
    sign_lifecycle_transition,
)

_VISIBLE_STATE = "active"
_ADMIN_VISIBLE_STATES = (
    _VISIBLE_STATE,
    "review_quarantined",
    "retention_quarantined",
    "cancelled_quarantined",
)
_COMPATIBILITY_PAGE_LIMIT = 100


@dataclass(frozen=True)
class Lead:
    partner_id: str
    firmenname: str
    lead_email: str
    tenant_id: str
    session_id: str
    briefing_title: str
    briefing_body: str
    created_at: str
    admission_request_id: str = ""
    briefing_provenance: tuple[str, ...] = ()
    briefing_wissensstand: str = ""
    briefing_risk_flags: tuple[str, ...] = ()
    policy_authority_ref: str = ""
    purpose_version: str = ""
    consent_version: str = ""
    handoff_confirmed: bool = False
    pii_classification: str = "unknown"
    prompt_trust: str = "untrusted"
    prompt_injection_signal: bool = False
    owner_subject: str = ""
    case_id: str = ""
    case_revision: int | None = None
    status: str = "neu"
    lifecycle_state: str = _VISIBLE_STATE
    content_bytes: int = 0
    retention_review_after: str | None = None
    cancelled_at: str | None = None
    cancellation_reason: str | None = None
    id: int = 0


def _normalized_new_lead(lead: Lead, *, require_governance: bool) -> Lead:
    if (
        not lead.tenant_id.strip()
        or not lead.owner_subject.strip()
        or not lead.case_id.strip()
        or lead.case_revision is None
        or lead.case_revision < 0
    ):
        raise ValueError(
            "new leads require exact tenant, owner, case, and non-negative revision"
        )
    if lead.lifecycle_state not in {_VISIBLE_STATE, "review_quarantined"}:
        raise ValueError("new leads must enter active or review quarantine")
    if require_governance and (
        not lead.admission_request_id
        or not lead.policy_authority_ref
        or not lead.purpose_version
        or not lead.consent_version
        or not lead.handoff_confirmed
        or lead.prompt_trust != "untrusted"
    ):
        raise ValueError("new lead is missing governance authority")
    content_bytes = lead.content_bytes or len(
        (lead.briefing_title + "\n" + lead.briefing_body).encode("utf-8")
    )
    if content_bytes <= 0:
        raise ValueError("new lead content size must be positive")
    return replace(lead, content_bytes=content_bytes)


def _to_domain(row: V2Lead) -> Lead:
    return Lead(
        id=row.id,
        admission_request_id=row.admission_request_id or "",
        partner_id=row.partner_id,
        firmenname=row.firmenname,
        lead_email=row.lead_email,
        tenant_id=row.tenant_id,
        session_id=row.session_id,
        briefing_title=row.briefing_title,
        briefing_body=row.briefing_body,
        created_at=row.created_at,
        briefing_provenance=tuple(row.briefing_provenance_json or []),
        briefing_wissensstand=row.briefing_wissensstand or "",
        briefing_risk_flags=tuple(row.briefing_risk_flags_json or []),
        policy_authority_ref=row.policy_authority_ref or "",
        purpose_version=row.purpose_version or "",
        consent_version=row.consent_version or "",
        handoff_confirmed=bool(row.handoff_confirmed),
        pii_classification=row.pii_classification or "unknown",
        prompt_trust=row.prompt_trust or "",
        prompt_injection_signal=bool(row.prompt_injection_signal),
        owner_subject=row.owner_subject or "",
        case_id=row.case_id or "",
        case_revision=row.case_revision,
        status=row.status,
        lifecycle_state=row.lifecycle_state or "legacy_unresolved",
        content_bytes=int(row.content_bytes or 0),
        retention_review_after=row.retention_review_after,
        cancelled_at=row.cancelled_at,
        cancellation_reason=row.cancellation_reason,
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


class LeadStore(Protocol):
    def store(self, lead: Lead) -> int: ...

    def page(
        self,
        *,
        partner_id: str | None,
        before_id: int | None,
        limit: int,
        include_quarantined: bool = False,
    ) -> KeysetPage[Lead]: ...

    def get_owned(self, lead_id: int, identity: VerifiedIdentity) -> Lead | None: ...

    def cancel_owned(
        self,
        lead_id: int,
        identity: VerifiedIdentity,
        *,
        idempotency_key: str,
        reason_code: str,
        now: datetime | None = None,
    ) -> LifecycleReceipt | None: ...

    def quarantine_due(self, *, before: str, limit: int = 100) -> int: ...


class InProcessLeadStore:
    """Explicit CI/eval store; production construction never falls back after DB configuration."""

    def __init__(
        self,
        *,
        receipt_secret: str | None = None,
        policy_authority_ref: str | None = None,
        enforce_governance: bool = False,
    ) -> None:
        self._leads: list[Lead] = []
        self._receipts: dict[tuple[int, str], LifecycleReceipt] = {}
        self._lock = threading.RLock()
        self._receipt_secret = receipt_secret
        self._policy_authority_ref = policy_authority_ref
        self._enforce_governance = enforce_governance

    def store(self, lead: Lead) -> int:
        normalized = _normalized_new_lead(
            lead, require_governance=self._enforce_governance
        )
        with self._lock:
            existing = next(
                (
                    item
                    for item in self._leads
                    if item.admission_request_id
                    and item.admission_request_id == normalized.admission_request_id
                ),
                None,
            )
            if existing is not None:
                return existing.id
            new_id = len(self._leads) + 1
            self._leads.append(replace(normalized, id=new_id))
            return new_id

    def page(
        self,
        *,
        partner_id: str | None,
        before_id: int | None,
        limit: int,
        include_quarantined: bool = False,
    ) -> KeysetPage[Lead]:
        if not 1 <= limit <= 100:
            raise ValueError("lead page limit must be between 1 and 100")
        with self._lock:
            rows = sorted(self._leads, key=lambda item: item.id, reverse=True)
            rows = [
                item
                for item in rows
                if (
                    item.lifecycle_state in _ADMIN_VISIBLE_STATES
                    if include_quarantined
                    else item.lifecycle_state == _VISIBLE_STATE
                )
                and (partner_id is None or item.partner_id == partner_id)
                and (before_id is None or item.id < before_id)
            ][: limit + 1]
            has_more = len(rows) > limit
            selected = tuple(rows[:limit])
            return KeysetPage(
                selected,
                encode_cursor(selected[-1].id) if has_more and selected else None,
            )

    def list_for_partner(self, partner_id: str) -> tuple[Lead, ...]:
        """Bounded compatibility helper; API routes use ``page``."""
        return self.page(
            partner_id=partner_id, before_id=None, limit=_COMPATIBILITY_PAGE_LIMIT
        ).items

    def list_all(self) -> tuple[Lead, ...]:
        """Bounded compatibility helper; API routes use ``page``."""
        return self.page(
            partner_id=None, before_id=None, limit=_COMPATIBILITY_PAGE_LIMIT
        ).items

    def get_owned(self, lead_id: int, identity: VerifiedIdentity) -> Lead | None:
        with self._lock:
            return next(
                (
                    lead
                    for lead in self._leads
                    if lead.id == lead_id
                    and lead.tenant_id == identity.tenant_id
                    and lead.owner_subject == identity.subject
                ),
                None,
            )

    def cancel_owned(
        self,
        lead_id: int,
        identity: VerifiedIdentity,
        *,
        idempotency_key: str,
        reason_code: str,
        now: datetime | None = None,
    ) -> LifecycleReceipt | None:
        if not self._receipt_secret or not self._policy_authority_ref:
            raise LifecycleTransitionUnavailable(
                "lead cancellation authority unavailable"
            )
        tenant_ref, actor_ref = identity_scope_refs(identity)
        idem_hash = idempotency_key_hash("lead.cancel", idempotency_key)
        key = (lead_id, idem_hash)
        with self._lock:
            prior = self._receipts.get(key)
            if prior is not None:
                if prior.reason_code != reason_code:
                    raise LifecycleTransitionConflict("idempotency key payload changed")
                return replace(prior, replay=True)
            for index, lead in enumerate(self._leads):
                if (
                    lead.id != lead_id
                    or lead.tenant_id != identity.tenant_id
                    or lead.owner_subject != identity.subject
                ):
                    continue
                if lead.lifecycle_state != _VISIBLE_STATE:
                    raise LifecycleTransitionConflict("lead is not cancellable")
                transition = sign_lifecycle_transition(
                    secret=self._receipt_secret,
                    action="lead.cancel",
                    idempotency_key=idempotency_key,
                    resource_type="lead",
                    resource_id=str(lead_id),
                    tenant_id=identity.tenant_id,
                    tenant_ref=tenant_ref,
                    actor_ref=actor_ref,
                    event_type="lead_cancellation",
                    from_state=lead.lifecycle_state,
                    to_state="cancelled_quarantined",
                    reason_code=reason_code,
                    policy_authority_ref=self._policy_authority_ref,
                    now=now,
                )
                self._leads[index] = replace(
                    lead,
                    lifecycle_state="cancelled_quarantined",
                    status="cancelled",
                    cancelled_at=transition.receipt.issued_at,
                    cancellation_reason=reason_code,
                )
                self._receipts[key] = transition.receipt
                return transition.receipt
        return None

    def quarantine_due(self, *, before: str, limit: int = 100) -> int:
        """Quarantine due leads; never deletes or silently hides an active row."""
        if not 1 <= limit <= 100:
            raise ValueError("retention batch limit must be between 1 and 100")
        changed = 0
        with self._lock:
            for index, lead in enumerate(self._leads):
                if changed >= limit:
                    break
                if (
                    lead.lifecycle_state == _VISIBLE_STATE
                    and lead.retention_review_after is not None
                    and lead.retention_review_after <= before
                ):
                    self._leads[index] = replace(
                        lead,
                        lifecycle_state="retention_quarantined",
                        status="retention_review",
                        cancellation_reason="retention_review_due",
                    )
                    changed += 1
        return changed


class PostgresLeadStore:
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

    def store(self, lead: Lead) -> int:
        normalized = _normalized_new_lead(lead, require_governance=True)
        with self._sf() as session:
            existing_id = session.scalar(
                select(V2Lead.id).where(
                    V2Lead.admission_request_id == normalized.admission_request_id
                )
            )
            if existing_id is not None:
                return int(existing_id)
            row = V2Lead(
                admission_request_id=normalized.admission_request_id,
                partner_id=normalized.partner_id,
                firmenname=normalized.firmenname,
                lead_email=normalized.lead_email,
                tenant_id=normalized.tenant_id,
                session_id=normalized.session_id,
                owner_subject=normalized.owner_subject,
                case_id=normalized.case_id,
                case_revision=normalized.case_revision,
                ownership_state="owned",
                briefing_title=normalized.briefing_title,
                briefing_body=normalized.briefing_body,
                briefing_provenance_json=list(normalized.briefing_provenance),
                briefing_wissensstand=normalized.briefing_wissensstand,
                briefing_risk_flags_json=list(normalized.briefing_risk_flags),
                policy_authority_ref=normalized.policy_authority_ref,
                purpose_version=normalized.purpose_version,
                consent_version=normalized.consent_version,
                handoff_confirmed=normalized.handoff_confirmed,
                pii_classification=normalized.pii_classification,
                prompt_trust=normalized.prompt_trust,
                prompt_injection_signal=normalized.prompt_injection_signal,
                created_at=normalized.created_at,
                status=normalized.status,
                lifecycle_state=normalized.lifecycle_state,
                content_bytes=normalized.content_bytes,
                retention_review_after=normalized.retention_review_after,
                cancelled_at=normalized.cancelled_at,
                cancellation_reason=normalized.cancellation_reason,
            )
            session.add(row)
            session.commit()
            return row.id

    def page(
        self,
        *,
        partner_id: str | None,
        before_id: int | None,
        limit: int,
        include_quarantined: bool = False,
    ) -> KeysetPage[Lead]:
        if not 1 <= limit <= 100:
            raise ValueError("lead page limit must be between 1 and 100")
        with self._sf() as session:
            lifecycle_filter = (
                V2Lead.lifecycle_state.in_(_ADMIN_VISIBLE_STATES)
                if include_quarantined
                else V2Lead.lifecycle_state == _VISIBLE_STATE
            )
            query = select(V2Lead).where(
                V2Lead.ownership_state == "owned", lifecycle_filter
            )
            if partner_id is not None:
                query = query.where(V2Lead.partner_id == partner_id)
            if before_id is not None:
                query = query.where(V2Lead.id < before_id)
            rows = session.scalars(
                query.order_by(V2Lead.id.desc()).limit(limit + 1)
            ).all()
            has_more = len(rows) > limit
            selected = tuple(_to_domain(row) for row in rows[:limit])
            return KeysetPage(
                selected,
                encode_cursor(selected[-1].id) if has_more and selected else None,
            )

    def list_for_partner(self, partner_id: str) -> tuple[Lead, ...]:
        return self.page(
            partner_id=partner_id, before_id=None, limit=_COMPATIBILITY_PAGE_LIMIT
        ).items

    def list_all(self) -> tuple[Lead, ...]:
        return self.page(
            partner_id=None, before_id=None, limit=_COMPATIBILITY_PAGE_LIMIT
        ).items

    def get_owned(self, lead_id: int, identity: VerifiedIdentity) -> Lead | None:
        with self._sf() as session:
            row = session.scalar(
                select(V2Lead).where(
                    V2Lead.id == lead_id,
                    V2Lead.tenant_id == identity.tenant_id,
                    V2Lead.owner_subject == identity.subject,
                    V2Lead.ownership_state == "owned",
                )
            )
            return _to_domain(row) if row is not None else None

    def cancel_owned(
        self,
        lead_id: int,
        identity: VerifiedIdentity,
        *,
        idempotency_key: str,
        reason_code: str,
        now: datetime | None = None,
    ) -> LifecycleReceipt | None:
        if not self._receipt_secret or not self._policy_authority_ref:
            raise LifecycleTransitionUnavailable(
                "lead cancellation authority unavailable"
            )
        tenant_ref, actor_ref = identity_scope_refs(identity)
        idem_hash = idempotency_key_hash("lead.cancel", idempotency_key)
        with self._sf() as session, session.begin():
            prior = session.scalar(
                select(V2ApiLifecycleReceipt).where(
                    V2ApiLifecycleReceipt.resource_type == "lead",
                    V2ApiLifecycleReceipt.resource_id == str(lead_id),
                    V2ApiLifecycleReceipt.idempotency_key_hash == idem_hash,
                )
            )
            if prior is not None:
                if prior.reason_code != reason_code:
                    raise LifecycleTransitionConflict("idempotency key payload changed")
                return _receipt_from_row(prior, replay=True)
            row = session.scalar(
                select(V2Lead)
                .where(
                    V2Lead.id == lead_id,
                    V2Lead.tenant_id == identity.tenant_id,
                    V2Lead.owner_subject == identity.subject,
                    V2Lead.ownership_state == "owned",
                )
                .with_for_update()
            )
            if row is None:
                return None
            if row.lifecycle_state != _VISIBLE_STATE:
                raise LifecycleTransitionConflict("lead is not cancellable")
            transition = sign_lifecycle_transition(
                secret=self._receipt_secret,
                action="lead.cancel",
                idempotency_key=idempotency_key,
                resource_type="lead",
                resource_id=str(lead_id),
                tenant_id=identity.tenant_id,
                tenant_ref=tenant_ref,
                actor_ref=actor_ref,
                event_type="lead_cancellation",
                from_state=row.lifecycle_state,
                to_state="cancelled_quarantined",
                reason_code=reason_code,
                policy_authority_ref=self._policy_authority_ref,
                now=now,
            )
            row.lifecycle_state = "cancelled_quarantined"
            row.status = "cancelled"
            row.cancelled_at = transition.receipt.issued_at
            row.cancellation_reason = reason_code
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

    def quarantine_due(self, *, before: str, limit: int = 100) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("retention batch limit must be between 1 and 100")
        with self._sf() as session, session.begin():
            rows = session.scalars(
                select(V2Lead)
                .where(
                    V2Lead.ownership_state == "owned",
                    V2Lead.lifecycle_state == _VISIBLE_STATE,
                    V2Lead.retention_review_after.is_not(None),
                    V2Lead.retention_review_after <= before,
                )
                .order_by(V2Lead.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for row in rows:
                row.lifecycle_state = "retention_quarantined"
                row.status = "retention_review"
                row.cancellation_reason = "retention_review_due"
            return len(rows)


def build_lead_store(settings) -> LeadStore:
    secret = (
        settings.api_lifecycle_receipt_hmac_secret.get_secret_value()
        if getattr(settings, "api_lifecycle_receipt_hmac_secret", None) is not None
        else None
    )
    policy_ref = getattr(settings, "api_lifecycle_policy_authority_ref", None)
    if getattr(settings, "database_url", None):
        from sealai_v2.db.engine import make_api_sessionmaker

        return PostgresLeadStore(
            make_api_sessionmaker(settings),
            receipt_secret=secret,
            policy_authority_ref=policy_ref,
        )
    return InProcessLeadStore(
        receipt_secret=secret,
        policy_authority_ref=policy_ref,
    )
