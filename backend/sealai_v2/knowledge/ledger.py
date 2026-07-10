"""Authoritative technical-knowledge ledger.

Postgres owns document revisions, claim lifecycle and review history. Qdrant is
only a rebuildable projection fed through ``V2KnowledgeOutbox``. This module is
the single write boundary for technical knowledge; request handlers and ops
commands must not write the vector index directly.
"""

from __future__ import annotations

from dataclasses import dataclass
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
from sealai_v2.knowledge.fachkarten import FachkartenCatalog

GLOBAL_KNOWLEDGE_TENANT = "sealai"
_ID_NAMESPACE = uuid.UUID("32288829-9179-5be3-8864-3a5858e78cc6")
_REVIEW_STATES = frozenset({"draft", "approved", "rejected"})


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
    *, tenant_id: str, card_id: str, document_id: str, content_sha256: str
) -> str:
    return str(
        uuid.uuid5(
            _ID_NAMESPACE,
            f"{tenant_id}|{card_id}|{document_id}|{content_sha256}",
        )
    )


def _review_status(seed_status: str) -> str:
    return "approved" if seed_status == "reviewed" else "draft"


def _quelle(row: V2KnowledgeClaim) -> str:
    label = (
        "reviewed"
        if row.review_status == "approved"
        else "draft - vorlaeufig, gegen Hersteller verifizieren"
    )
    provenance = ", ".join(row.provenance_json or [])
    return f"Fachkarte {row.card_id} ({label}; {provenance})"


def _claim_payload(row: V2KnowledgeClaim, document: V2KnowledgeDocument) -> dict:
    return {
        "claim_id": row.id,
        "card_id": row.card_id,
        "card_version": row.card_version,
        "document_id": row.document_id,
        "document_version": document.version,
        "document_sha256": document.content_sha256,
        "review_state": ("reviewed" if row.review_status == "approved" else "draft"),
        "review_status": row.review_status,
        "claim_text": row.text,
        "claim_kind": row.kind,
        "sources": list(row.sources_json or []),
        "provenance": list(row.provenance_json or []),
        "scope": dict(row.scope_json or {}),
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
                        card_id=card.id,
                        document_id=doc.id,
                        content_sha256=claim_hash,
                    )
                    provenance = list(
                        dict.fromkeys((*card.provenance, *claim.provenance))
                    )
                    incoming[claim_id] = (
                        card,
                        claim,
                        order,
                        claim_hash,
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
                provenance,
            ) in incoming.items():
                desired_status = _review_status(claim.review_state)
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
                        kind=claim.kind,
                        review_status=desired_status,
                        scope_json=card.scope,
                        sources_json=list(claim.sources),
                        provenance_json=provenance,
                        active=True,
                        version=1,
                        qdrant_sync_state="pending",
                        created_at=now,
                        updated_at=now,
                        reviewed_at=now if desired_status == "approved" else None,
                        reviewed_by=actor if desired_status == "approved" else None,
                    )
                    session.add(row)
                    if desired_status == "approved":
                        session.add(
                            V2KnowledgeReview(
                                claim_id=row.id,
                                tenant_id=row.tenant_id,
                                from_status="unreviewed",
                                to_status="approved",
                                actor=actor,
                                note="Imported from reviewed source artifact",
                                evidence_json=list(claim.sources),
                                created_at=now,
                            )
                        )
                    session.flush()
                    _enqueue(session, row, event_type="upsert", now=now, document=doc)
                    created += 1
                    enqueued += 1
                    continue

                # Automated draft ingestion may never downgrade a human-approved
                # claim when an identical source revision is processed again.
                if row.review_status == "approved" and desired_status == "draft":
                    desired_status = "approved"
                desired = {
                    "card_version": card.version,
                    "claim_order": order,
                    "text": _normalise_text(claim.text),
                    "kind": claim.kind,
                    "review_status": desired_status,
                    "scope_json": card.scope,
                    "sources_json": list(claim.sources),
                    "provenance_json": provenance,
                    "active": True,
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
                row.qdrant_sync_state = "pending"
                _enqueue(session, row, event_type="upsert", now=now, document=doc)
                enqueued += 1

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
                    V2KnowledgeClaim.review_status != "rejected",
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
            }

    def review_claim(
        self,
        *,
        tenant_id: str,
        claim_id: str,
        to_status: str,
        actor: str,
        now: str,
        note: str = "",
        evidence: tuple[str, ...] = (),
    ) -> dict:
        if to_status not in _REVIEW_STATES:
            raise KnowledgeLedgerError(f"invalid review status: {to_status}")
        if to_status == "approved" and not evidence:
            raise KnowledgeLedgerError("approving a claim requires review evidence")
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
            if previous == to_status:
                document = session.get(V2KnowledgeDocument, row.document_id)
                return _claim_payload(row, document)
            row.review_status = to_status
            row.active = to_status != "rejected"
            row.version += 1
            row.updated_at = now
            row.reviewed_at = now
            row.reviewed_by = actor
            row.qdrant_sync_state = "pending"
            if to_status == "approved":
                row.sources_json = list(
                    dict.fromkeys([*(row.sources_json or []), *evidence])
                )
            session.add(
                V2KnowledgeReview(
                    claim_id=row.id,
                    tenant_id=row.tenant_id,
                    from_status=previous,
                    to_status=to_status,
                    actor=actor,
                    note=note,
                    evidence_json=list(evidence),
                    created_at=now,
                )
            )
            document = session.get(V2KnowledgeDocument, row.document_id)
            _enqueue(
                session,
                row,
                event_type="delete" if to_status == "rejected" else "upsert",
                now=now,
                document=document,
            )
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
            session.commit()
            return len(rows)


def build_knowledge_ledger(settings) -> PostgresKnowledgeLedger:
    if not settings.database_url:
        raise KnowledgeLedgerError(
            "technical knowledge requires SEALAI_V2_DATABASE_URL; "
            "Qdrant is not a source of truth"
        )
    from sealai_v2.db.engine import make_engine, make_sessionmaker

    return PostgresKnowledgeLedger(
        make_sessionmaker(make_engine(settings.database_url))
    )


def payload_fingerprint(payload: dict) -> str:
    """Stable helper used by tests and operational reconciliation reports."""
    return _digest(json.dumps(payload, sort_keys=True, separators=(",", ":")))
