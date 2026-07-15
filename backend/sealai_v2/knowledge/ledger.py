"""Authoritative technical-knowledge ledger.

Postgres owns document revisions, claim lifecycle and review history. Qdrant is
only a rebuildable projection fed through ``V2KnowledgeOutbox``. This module is
the single write boundary for technical knowledge; request handlers and ops
commands must not write the vector index directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import unicodedata
import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import (
    V2KnowledgeClaim,
    V2KnowledgeDocument,
    V2KnowledgeOutbox,
    V2KnowledgeReview,
)
from sealai_v2.knowledge.authority import bump_authority_epoch
from sealai_v2.knowledge.fachkarten import FachkartenCatalog

GLOBAL_KNOWLEDGE_TENANT = "sealai"
_ID_NAMESPACE = uuid.UUID("32288829-9179-5be3-8864-3a5858e78cc6")
_REVIEW_STATES = frozenset({"draft", "reviewed", "approved", "quarantined", "rejected"})
_HUMAN_REVIEW_ORIGINS = frozenset({"human_api", "human_seed"})
_UNCERTAINTY_STATES = frozenset(
    {"bounded", "conditional", "conflicted", "not_sufficiently_supported"}
)
_TRANSFERABILITY_STATES = frozenset(
    {
        "source_specific",
        "family_level_orientation",
        "application_dependent",
        "not_assessed",
    }
)


class KnowledgeLedgerError(RuntimeError):
    pass


class KnowledgeClaimNotFound(LookupError):
    pass


@dataclass(frozen=True)
class KnowledgeDocumentInput:
    tenant_id: str
    source_type: str
    source_id: str
    source_uri: str
    object_key: str
    title: str
    content: bytes
    authority: str


@dataclass(frozen=True)
class LedgerWriteResult:
    document_id: str
    document_version: int
    claims_total: int
    claims_created: int
    claims_updated: int
    claims_retired: int
    outbox_enqueued: int


class KnowledgeLedger(Protocol):
    def replace_catalog(
        self,
        document: KnowledgeDocumentInput,
        catalog: FachkartenCatalog,
        *,
        now: str,
        actor: str,
    ) -> LedgerWriteResult: ...

    def resolve_claims(
        self, claim_ids: tuple[str, ...], *, tenant_id: str
    ) -> dict[str, dict]: ...

    def list_claims(
        self, *, tenant_id: str, statuses: tuple[str, ...], limit: int
    ) -> tuple[dict, ...]: ...


def _normalise_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _digest(value: bytes | str) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return sha256(raw).hexdigest()


def _document_id(document: KnowledgeDocumentInput, content_sha256: str) -> str:
    key = (
        f"{document.tenant_id}|{document.source_type}|{document.source_id}|"
        f"{content_sha256}"
    )
    return str(uuid.uuid5(_ID_NAMESPACE, key))


def _claim_id(
    *,
    tenant_id: str,
    source_type: str,
    source_id: str,
    card_id: str,
    content_sha256: str,
) -> str:
    """Identify a logical claim independently from its document revision.

    The normalized claim text remains part of the identity, so changed wording
    requires a fresh review. Unrelated catalog revisions and source-link repairs
    no longer rotate every claim ID or orphan append-only human reviews.
    """

    return str(
        uuid.uuid5(
            _ID_NAMESPACE,
            f"{tenant_id}|{source_type}|{source_id}|{card_id}|{content_sha256}",
        )
    )


def _canonical_authority_value(value):
    if isinstance(value, dict):
        return {
            str(key): _canonical_authority_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        items = [_canonical_authority_value(item) for item in value]
        return sorted(
            items,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    return value


def _authority_fingerprint(card, claim, *, content_sha256: str) -> str:
    """Hash import-controlled fields that delimit a human review's validity."""

    contract = _canonical_authority_value(
        {
            "schema_version": 1,
            "card_id": card.id,
            "card_version": card.version,
            "content_sha256": content_sha256,
            "kind": claim.kind,
            "scope": _claim_scope(card, claim),
            "sources": list(claim.sources),
            "evidence": list(claim.evidence),
            "applicability": _claim_applicability(card, claim),
            "declared_uncertainty": claim.uncertainty,
            "declared_transferability": claim.transferability,
            "conflicts": list(claim.conflicts),
        }
    )
    return _digest(
        json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _review_status(claim) -> str:
    if claim.reviewed:
        return "approved"
    if claim.quarantined:
        return "quarantined"
    return "draft"


def _normalise_evidence(
    evidence: tuple[str | dict, ...] | list[str | dict],
    *,
    document_id: str = "",
    document_version: int | None = None,
) -> list[dict]:
    records: list[dict] = []
    for item in evidence:
        if isinstance(item, str):
            citation = item.strip()
            record = {"citation": citation}
        elif isinstance(item, dict):
            record = dict(item)
            citation = str(
                record.get("citation")
                or record.get("source")
                or record.get("reference")
                or ""
            ).strip()
            record["citation"] = citation
        else:
            raise KnowledgeLedgerError("review evidence must be a string or object")
        if not citation:
            raise KnowledgeLedgerError("review evidence requires a citation")
        record.setdefault("source_type", "technical_reference")
        if document_id:
            record.setdefault("document_id", document_id)
        if document_version is not None:
            record.setdefault("document_version", document_version)
        records.append(record)
    return records


def _parse_timestamp(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeLedgerError(f"invalid {field} timestamp") from exc
    if parsed.tzinfo is None:
        raise KnowledgeLedgerError(f"{field} must include a timezone")
    return parsed


def _validate_review_expiry(value: str, *, now: str) -> None:
    expiry = _parse_timestamp(value, field="review expiry")
    reviewed_at = _parse_timestamp(now, field="review")
    if expiry <= reviewed_at:
        raise KnowledgeLedgerError("review expiry must be in the future")


def _human_review_actor(value: str | None) -> bool:
    actor = (value or "").strip().lower()
    if not actor:
        return False
    return not any(
        marker in actor
        for marker in ("codex", "llm", "model", "agent", "release-bootstrap")
    )


def _approved_claim_is_current(
    row: V2KnowledgeClaim, *, at: datetime | None = None
) -> bool:
    if row.review_status != "approved":
        return False
    if not (
        row.review_origin in _HUMAN_REVIEW_ORIGINS
        and row.sources_json
        and row.evidence_json
        and row.applicability_json
        and row.reviewed_at
        and _human_review_actor(row.reviewed_by)
        and row.review_expires_at
        and row.uncertainty in _UNCERTAINTY_STATES
        and row.transferability in _TRANSFERABILITY_STATES
    ):
        return False
    try:
        expiry = _parse_timestamp(row.review_expires_at, field="review expiry")
    except KnowledgeLedgerError:
        return False
    return expiry > (at or datetime.now(timezone.utc))


def _human_review_is_preservable(row: V2KnowledgeClaim) -> bool:
    if row.review_origin not in _HUMAN_REVIEW_ORIGINS or not _human_review_actor(
        row.reviewed_by
    ):
        return False
    if row.review_status == "approved":
        return _approved_claim_is_current(row)
    if row.review_status == "reviewed":
        return bool(
            row.evidence_json
            and row.applicability_json
            and row.review_expires_at
            and row.uncertainty in _UNCERTAINTY_STATES
            and row.transferability in _TRANSFERABILITY_STATES
        )
    return row.review_status in {"quarantined", "rejected"}


def _claim_applicability(card, claim) -> dict:
    applicability = {
        key: list(value) if isinstance(value, (list, tuple)) else value
        for key, value in card.scope.items()
    }
    applicability.update(dict(claim.applicability or {}))
    return applicability


def _claim_uncertainty(claim, review_status: str) -> str:
    if claim.uncertainty:
        return claim.uncertainty
    return (
        "conditional" if review_status == "approved" else "not_sufficiently_supported"
    )


def _claim_transferability(claim) -> str:
    if claim.transferability:
        return claim.transferability
    if claim.kind == "example_value":
        return "source_specific"
    if claim.kind in {
        "system_dependent",
        "qualification_required",
        "regulatory_status",
        "safety_caution",
        "safety_nogo",
    }:
        return "application_dependent"
    return "family_level_orientation"


def _projection_event(review_status: str) -> str:
    # A completed review is intentionally not authority. The first reviewer
    # removes any former draft projection; only the separate approver may put
    # the reviewed claim back into the rebuildable Qdrant index.
    return "upsert" if review_status in {"approved", "draft"} else "delete"


def _quelle(row: V2KnowledgeClaim) -> str:
    labels = {
        "approved": "reviewed",
        "reviewed": "reviewed - wartet auf unabhaengige Freigabe",
        "draft": "draft - vorlaeufig, gegen Hersteller verifizieren",
        "quarantined": "quarantined - nicht zur Ausgabe freigegeben",
        "rejected": "rejected",
    }
    label = labels.get(row.review_status, row.review_status)
    provenance = ", ".join(row.provenance_json or [])
    return f"Fachkarte {row.card_id} ({label}; {provenance})"


def _claim_scope(card, claim) -> dict:
    """Persist claim-level answer metadata inside the existing JSON scope column.

    This keeps the authoritative ledger schema stable while making facets part of the versioned
    claim projection. Reserved underscore keys are removed again before normal retrieval matching.
    """
    return {
        **card.scope,
        "_answer_facets": list(claim.answer_facets),
        "_subject_type": card.subject_type,
    }


def _claim_payload(row: V2KnowledgeClaim, document: V2KnowledgeDocument) -> dict:
    scope = dict(row.scope_json or {})
    answer_facets = list(scope.pop("_answer_facets", ()) or ())
    subject_type = str(scope.pop("_subject_type", "general") or "general")
    return {
        "claim_id": row.id,
        "card_id": row.card_id,
        "card_version": row.card_version,
        "document_id": row.document_id,
        "document_version": document.version,
        "document_sha256": document.content_sha256,
        "review_state": {
            "approved": "reviewed",
            "reviewed": "reviewed_pending_approval",
            "draft": "draft",
            "quarantined": "quarantined",
            "rejected": "rejected",
        }.get(row.review_status, "quarantined"),
        "review_status": row.review_status,
        "claim_text": row.text,
        "authority_fingerprint": row.authority_fingerprint,
        "claim_kind": row.kind,
        "answer_facets": answer_facets,
        "subject_type": subject_type,
        "sources": list(row.sources_json or []),
        "evidence": list(row.evidence_json or []),
        "applicability": dict(row.applicability_json or {}),
        "uncertainty": row.uncertainty,
        "transferability": row.transferability,
        "conflicts": list(row.conflicts_json or []),
        "reviewed_at": row.reviewed_at,
        "reviewed_by": row.reviewed_by,
        "review_origin": row.review_origin,
        "review_expires_at": row.review_expires_at,
        "change_reason": row.change_reason,
        "provenance": list(row.provenance_json or []),
        "scope": scope,
        "tenant_id": row.tenant_id,
        "version": row.version,
        "quelle": _quelle(row),
    }


def _enqueue(
    session,
    row: V2KnowledgeClaim,
    *,
    event_type: str,
    now: str,
    document: V2KnowledgeDocument | None = None,
) -> None:
    session.add(
        V2KnowledgeOutbox(
            claim_id=row.id,
            tenant_id=row.tenant_id,
            event_type=event_type,
            payload=(
                _claim_payload(row, document)
                if event_type == "upsert" and document is not None
                else {"claim_id": row.id}
            ),
            created_at=now,
        )
    )


class PostgresKnowledgeLedger:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def replace_catalog(
        self,
        document: KnowledgeDocumentInput,
        catalog: FachkartenCatalog,
        *,
        now: str,
        actor: str,
    ) -> LedgerWriteResult:
        if not document.tenant_id.strip():
            raise KnowledgeLedgerError("knowledge tenant_id is mandatory")
        if not document.source_type.strip() or not document.source_id.strip():
            raise KnowledgeLedgerError("knowledge source_type/source_id are mandatory")
        if not document.content:
            raise KnowledgeLedgerError("knowledge source content is empty")

        content_hash = _digest(document.content)
        doc_id = _document_id(document, content_hash)
        created = updated = retired = enqueued = 0

        with self._sf() as session:
            doc = session.get(V2KnowledgeDocument, doc_id)
            if doc is None:
                previous_documents = session.scalars(
                    select(V2KnowledgeDocument)
                    .where(
                        V2KnowledgeDocument.tenant_id == document.tenant_id,
                        V2KnowledgeDocument.source_type == document.source_type,
                        V2KnowledgeDocument.source_id == document.source_id,
                    )
                    .with_for_update()
                ).all()
                latest_version = max(
                    (item.version for item in previous_documents), default=0
                )
                for previous in previous_documents:
                    if previous.status == "active":
                        previous.status = "superseded"
                        previous.valid_to = now
                doc = V2KnowledgeDocument(
                    id=doc_id,
                    tenant_id=document.tenant_id,
                    source_type=document.source_type,
                    source_id=document.source_id,
                    source_uri=document.source_uri,
                    object_key=document.object_key,
                    title=document.title,
                    content_sha256=content_hash,
                    version=latest_version + 1,
                    authority=document.authority,
                    status="active",
                    valid_from=now,
                    created_at=now,
                )
                session.add(doc)
                session.flush()

            source_doc_ids = select(V2KnowledgeDocument.id).where(
                V2KnowledgeDocument.tenant_id == document.tenant_id,
                V2KnowledgeDocument.source_type == document.source_type,
                V2KnowledgeDocument.source_id == document.source_id,
            )
            existing_rows = session.scalars(
                select(V2KnowledgeClaim)
                .where(
                    V2KnowledgeClaim.tenant_id == document.tenant_id,
                    V2KnowledgeClaim.document_id.in_(source_doc_ids),
                    V2KnowledgeClaim.active.is_(True),
                )
                .with_for_update()
            ).all()

            incoming: dict[str, tuple] = {}
            for card in catalog.cards:
                for order, claim in enumerate(card.claims):
                    claim_hash = _digest(_normalise_text(claim.text))
                    claim_id = _claim_id(
                        tenant_id=document.tenant_id,
                        source_type=document.source_type,
                        source_id=document.source_id,
                        card_id=card.id,
                        content_sha256=claim_hash,
                    )
                    if claim_id in incoming:
                        raise KnowledgeLedgerError(
                            f"duplicate logical claim identity on card {card.id}: "
                            f"{claim_hash}"
                        )
                    provenance = list(
                        dict.fromkeys((*card.provenance, *claim.provenance))
                    )
                    incoming[claim_id] = (
                        card,
                        claim,
                        order,
                        claim_hash,
                        _authority_fingerprint(card, claim, content_sha256=claim_hash),
                        provenance,
                    )

            incoming_ids = set(incoming)
            for row in existing_rows:
                if row.id in incoming_ids:
                    continue
                row.active = False
                row.version += 1
                row.updated_at = now
                row.qdrant_sync_state = "pending"
                _enqueue(session, row, event_type="delete", now=now)
                retired += 1
                enqueued += 1

            for claim_id, (
                card,
                claim,
                order,
                claim_hash,
                authority_fingerprint,
                provenance,
            ) in incoming.items():
                desired_status = _review_status(claim)
                evidence = _normalise_evidence(
                    list(claim.evidence or claim.sources),
                    document_id=doc.id,
                    document_version=doc.version,
                )
                applicability = _claim_applicability(card, claim)
                uncertainty = _claim_uncertainty(claim, desired_status)
                transferability = _claim_transferability(claim)
                conflicts = list(claim.conflicts)
                review_expires_at = (
                    claim.review_expires_at if desired_status == "approved" else None
                )
                change_reason = claim.change_reason or "catalog_import"
                row = session.get(V2KnowledgeClaim, claim_id)
                if row is None:
                    row = V2KnowledgeClaim(
                        id=claim_id,
                        tenant_id=document.tenant_id,
                        card_id=card.id,
                        card_version=card.version,
                        document_id=doc.id,
                        claim_order=order,
                        text=_normalise_text(claim.text),
                        content_sha256=claim_hash,
                        authority_fingerprint=authority_fingerprint,
                        kind=claim.kind,
                        review_status=desired_status,
                        scope_json=_claim_scope(card, claim),
                        sources_json=list(claim.sources),
                        evidence_json=evidence,
                        applicability_json=applicability,
                        uncertainty=uncertainty,
                        transferability=transferability,
                        conflicts_json=conflicts,
                        review_expires_at=review_expires_at,
                        review_origin=(
                            "human_seed"
                            if desired_status == "approved"
                            else "policy_import"
                            if desired_status == "quarantined"
                            else "unreviewed"
                        ),
                        change_reason=change_reason,
                        provenance_json=provenance,
                        active=True,
                        version=1,
                        qdrant_sync_state="pending",
                        created_at=now,
                        updated_at=now,
                        reviewed_at=(
                            claim.reviewed_at
                            if desired_status == "approved"
                            else now
                            if desired_status != "draft"
                            else None
                        ),
                        reviewed_by=(
                            claim.reviewed_by
                            if desired_status == "approved"
                            else actor
                            if desired_status != "draft"
                            else None
                        ),
                    )
                    session.add(row)
                    if desired_status in {"approved", "quarantined"}:
                        session.add(
                            V2KnowledgeReview(
                                claim_id=row.id,
                                tenant_id=row.tenant_id,
                                from_status="unreviewed",
                                to_status=desired_status,
                                actor=actor,
                                note=(
                                    "Imported from evidenced reviewed source artifact"
                                    if desired_status == "approved"
                                    else "Declared reviewed but quarantined because the human review contract is incomplete"
                                ),
                                evidence_json=evidence,
                                created_at=now,
                            )
                        )
                    session.flush()
                    _enqueue(
                        session,
                        row,
                        event_type=_projection_event(desired_status),
                        now=now,
                        document=doc,
                    )
                    created += 1
                    enqueued += 1
                    continue

                previous_status = row.review_status
                authority_changed = row.authority_fingerprint != authority_fingerprint
                prior_human_review = _human_review_is_preservable(row)
                if (
                    authority_changed
                    and prior_human_review
                    and desired_status != "approved"
                ):
                    desired_status = "quarantined"
                preserve_human_review = not authority_changed and prior_human_review
                if preserve_human_review:
                    desired_status = row.review_status
                    evidence = list(row.evidence_json or [])
                    applicability = dict(row.applicability_json or applicability)
                    uncertainty = row.uncertainty
                    transferability = row.transferability
                    conflicts = list(row.conflicts_json or [])
                    review_expires_at = row.review_expires_at
                    change_reason = row.change_reason or "human_review_preserved"
                    claim_sources = list(row.sources_json or [])
                    reviewed_at = row.reviewed_at
                    reviewed_by = row.reviewed_by
                    review_origin = row.review_origin
                else:
                    claim_sources = list(claim.sources)
                    reviewed_at = (
                        claim.reviewed_at if desired_status == "approved" else None
                    )
                    reviewed_by = (
                        claim.reviewed_by if desired_status == "approved" else None
                    )
                    review_origin = (
                        "human_seed"
                        if desired_status == "approved"
                        else "policy_import"
                        if desired_status in {"quarantined", "rejected"}
                        else "unreviewed"
                    )
                    if (
                        not authority_changed
                        and row.review_status == desired_status
                        and row.review_origin == "policy_import"
                    ):
                        reviewed_at = row.reviewed_at
                        reviewed_by = row.reviewed_by
                desired = {
                    "card_version": card.version,
                    "document_id": doc.id,
                    "claim_order": order,
                    "text": _normalise_text(claim.text),
                    "content_sha256": claim_hash,
                    "authority_fingerprint": authority_fingerprint,
                    "kind": claim.kind,
                    "review_status": desired_status,
                    "scope_json": _claim_scope(card, claim),
                    "sources_json": claim_sources,
                    "evidence_json": evidence,
                    "applicability_json": applicability,
                    "uncertainty": uncertainty,
                    "transferability": transferability,
                    "conflicts_json": conflicts,
                    "review_expires_at": review_expires_at,
                    "review_origin": review_origin,
                    "change_reason": change_reason,
                    "provenance_json": provenance,
                    "active": desired_status != "rejected",
                    "reviewed_at": reviewed_at,
                    "reviewed_by": reviewed_by,
                }
                changed = any(
                    getattr(row, key) != value for key, value in desired.items()
                )
                if not changed and row.qdrant_sync_state in {"pending", "synced"}:
                    continue
                for key, value in desired.items():
                    setattr(row, key, value)
                if changed:
                    row.version += 1
                    row.updated_at = now
                    updated += 1
                if previous_status != desired_status or (
                    authority_changed and prior_human_review
                ):
                    row.reviewed_at = (
                        claim.reviewed_at if desired_status == "approved" else now
                    )
                    row.reviewed_by = (
                        claim.reviewed_by if desired_status == "approved" else actor
                    )
                    row.review_origin = (
                        "human_seed"
                        if desired_status == "approved"
                        else "policy_import"
                    )
                    session.add(
                        V2KnowledgeReview(
                            claim_id=row.id,
                            tenant_id=row.tenant_id,
                            from_status=previous_status,
                            to_status=desired_status,
                            actor=actor,
                            note=(
                                "Authority contract changed; prior human review invalidated"
                                if authority_changed
                                else "Automated evidence-policy reconciliation"
                                if desired_status == "quarantined"
                                else "Catalog review-state reconciliation"
                            ),
                            evidence_json=evidence,
                            created_at=now,
                        )
                    )
                row.qdrant_sync_state = "pending"
                _enqueue(
                    session,
                    row,
                    event_type=_projection_event(desired_status),
                    now=now,
                    document=doc,
                )
                enqueued += 1

            if created or updated or retired:
                bump_authority_epoch(session, now=now)
            session.commit()
            return LedgerWriteResult(
                document_id=doc.id,
                document_version=doc.version,
                claims_total=len(incoming),
                claims_created=created,
                claims_updated=updated,
                claims_retired=retired,
                outbox_enqueued=enqueued,
            )

    def resolve_claims(
        self, claim_ids: tuple[str, ...], *, tenant_id: str
    ) -> dict[str, dict]:
        ids = tuple(dict.fromkeys(item for item in claim_ids if item))
        if not ids:
            return {}
        allowed_tenants = {tenant_id, GLOBAL_KNOWLEDGE_TENANT}
        with self._sf() as session:
            rows = session.scalars(
                select(V2KnowledgeClaim).where(
                    V2KnowledgeClaim.id.in_(ids),
                    V2KnowledgeClaim.tenant_id.in_(allowed_tenants),
                    V2KnowledgeClaim.active.is_(True),
                    V2KnowledgeClaim.review_status.in_(("approved", "draft")),
                )
            ).all()
            documents = {
                document.id: document
                for document in session.scalars(
                    select(V2KnowledgeDocument).where(
                        V2KnowledgeDocument.id.in_({row.document_id for row in rows})
                    )
                ).all()
            }
            return {
                row.id: _claim_payload(row, documents[row.document_id])
                for row in rows
                if row.document_id in documents
                and (row.review_status == "draft" or _approved_claim_is_current(row))
            }

    def list_claims(
        self, *, tenant_id: str, statuses: tuple[str, ...], limit: int = 100
    ) -> tuple[dict, ...]:
        invalid = set(statuses) - _REVIEW_STATES
        if invalid:
            raise KnowledgeLedgerError(f"invalid review states: {sorted(invalid)}")
        bounded_limit = max(1, min(int(limit), 500))
        with self._sf() as session:
            rows = session.scalars(
                select(V2KnowledgeClaim)
                .where(
                    V2KnowledgeClaim.tenant_id == tenant_id,
                    V2KnowledgeClaim.active.is_(True),
                    V2KnowledgeClaim.review_status.in_(statuses),
                )
                .order_by(V2KnowledgeClaim.card_id, V2KnowledgeClaim.claim_order)
                .limit(bounded_limit)
            ).all()
            documents = {
                document.id: document
                for document in session.scalars(
                    select(V2KnowledgeDocument).where(
                        V2KnowledgeDocument.id.in_({row.document_id for row in rows})
                    )
                ).all()
            }
            return tuple(
                _claim_payload(row, documents[row.document_id])
                for row in rows
                if row.document_id in documents
            )

    def review_claim(
        self,
        *,
        tenant_id: str,
        claim_id: str,
        to_status: str,
        actor: str,
        now: str,
        note: str = "",
        evidence: tuple[str | dict, ...] = (),
        applicability: dict | None = None,
        uncertainty: str | None = None,
        transferability: str | None = None,
        review_expires_at: str | None = None,
        conflicts: tuple[str, ...] = (),
        change_reason: str = "",
    ) -> dict:
        if to_status not in _REVIEW_STATES:
            raise KnowledgeLedgerError(f"invalid review status: {to_status}")
        if not _human_review_actor(actor):
            raise KnowledgeLedgerError(
                "knowledge review requires an authenticated human actor"
            )
        evidence_records = _normalise_evidence(list(evidence))
        if to_status == "reviewed":
            if not evidence_records:
                raise KnowledgeLedgerError("reviewing a claim requires review evidence")
            if not applicability:
                raise KnowledgeLedgerError("reviewing a claim requires applicability")
            if uncertainty not in _UNCERTAINTY_STATES:
                raise KnowledgeLedgerError(
                    "reviewing a claim requires a controlled uncertainty state"
                )
            if transferability not in _TRANSFERABILITY_STATES:
                raise KnowledgeLedgerError(
                    "reviewing a claim requires a controlled transferability state"
                )
            if not review_expires_at:
                raise KnowledgeLedgerError(
                    "reviewing a claim requires a review expiry timestamp"
                )
            _validate_review_expiry(review_expires_at, now=now)
        with self._sf() as session:
            row = session.scalar(
                select(V2KnowledgeClaim)
                .where(
                    V2KnowledgeClaim.id == claim_id,
                    V2KnowledgeClaim.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            if row is None:
                raise KnowledgeClaimNotFound(claim_id)
            previous = row.review_status
            metadata_change = bool(
                evidence_records
                or applicability
                or uncertainty
                or transferability
                or review_expires_at
                or conflicts
                or change_reason
            )
            if to_status == "approved":
                if previous != "reviewed":
                    raise KnowledgeLedgerError(
                        "approval requires a completed independent review"
                    )
                if actor == row.reviewed_by:
                    raise KnowledgeLedgerError(
                        "reviewer and approver must be different human actors"
                    )
                if metadata_change:
                    raise KnowledgeLedgerError(
                        "approver cannot alter the independently reviewed contract"
                    )
                if not (
                    row.evidence_json
                    and row.applicability_json
                    and row.review_expires_at
                    and row.uncertainty in _UNCERTAINTY_STATES
                    and row.transferability in _TRANSFERABILITY_STATES
                ):
                    raise KnowledgeLedgerError(
                        "approval requires a complete independently reviewed contract"
                    )
                _validate_review_expiry(row.review_expires_at, now=now)
            elif to_status == "reviewed" and previous not in {
                "draft",
                "quarantined",
            }:
                raise KnowledgeLedgerError(
                    "review requires a draft or quarantined claim"
                )
            if previous == to_status and not metadata_change:
                document = session.get(V2KnowledgeDocument, row.document_id)
                return _claim_payload(row, document)
            row.review_status = to_status
            row.active = to_status != "rejected"
            row.version += 1
            row.updated_at = now
            # Approval records its actor in the append-only transition log but
            # preserves the first reviewer's identity on the claim. This makes
            # the two-person invariant durable and queryable after approval.
            if to_status != "approved":
                row.reviewed_at = now
                row.reviewed_by = actor
            row.review_origin = "human_api"
            row.qdrant_sync_state = "pending"
            if to_status == "reviewed":
                citations = [item["citation"] for item in evidence_records]
                row.sources_json = list(
                    dict.fromkeys([*(row.sources_json or []), *citations])
                )
                row.evidence_json = evidence_records
                row.applicability_json = dict(applicability or {})
                row.uncertainty = uncertainty or "not_sufficiently_supported"
                row.transferability = transferability or "not_assessed"
                row.conflicts_json = list(conflicts)
                row.review_expires_at = review_expires_at
                row.change_reason = change_reason or note or "manual_review"
            session.add(
                V2KnowledgeReview(
                    claim_id=row.id,
                    tenant_id=row.tenant_id,
                    from_status=previous,
                    to_status=to_status,
                    actor=actor,
                    note=note,
                    evidence_json=evidence_records,
                    created_at=now,
                )
            )
            document = session.get(V2KnowledgeDocument, row.document_id)
            _enqueue(
                session,
                row,
                event_type=_projection_event(to_status),
                now=now,
                document=document,
            )
            bump_authority_epoch(session, now=now)
            session.commit()
            return _claim_payload(row, document)

    def retire_card(
        self,
        *,
        tenant_id: str,
        card_id: str,
        actor: str,
        now: str,
        note: str,
    ) -> int:
        """Retire every active claim on a card with an auditable delete projection."""
        with self._sf() as session:
            rows = session.scalars(
                select(V2KnowledgeClaim)
                .where(
                    V2KnowledgeClaim.tenant_id == tenant_id,
                    V2KnowledgeClaim.card_id == card_id,
                    V2KnowledgeClaim.active.is_(True),
                )
                .with_for_update()
            ).all()
            for row in rows:
                previous = row.review_status
                row.review_status = "rejected"
                row.active = False
                row.version += 1
                row.updated_at = now
                row.reviewed_at = now
                row.reviewed_by = actor
                row.review_origin = "policy_import"
                row.qdrant_sync_state = "pending"
                session.add(
                    V2KnowledgeReview(
                        claim_id=row.id,
                        tenant_id=row.tenant_id,
                        from_status=previous,
                        to_status="rejected",
                        actor=actor,
                        note=note,
                        evidence_json=[],
                        created_at=now,
                    )
                )
                _enqueue(session, row, event_type="delete", now=now)
            if rows:
                bump_authority_epoch(session, now=now)
            session.commit()
            return len(rows)


def build_knowledge_ledger(settings) -> PostgresKnowledgeLedger:
    if not settings.database_url:
        raise KnowledgeLedgerError(
            "technical knowledge requires SEALAI_V2_DATABASE_URL; "
            "Qdrant is not a source of truth"
        )
    from sealai_v2.db.engine import make_api_sessionmaker

    return PostgresKnowledgeLedger(make_api_sessionmaker(settings))


def payload_fingerprint(payload: dict) -> str:
    """Stable helper used by tests and operational reconciliation reports."""
    return _digest(json.dumps(payload, sort_keys=True, separators=(",", ":")))
