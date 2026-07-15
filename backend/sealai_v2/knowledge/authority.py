"""Request-bound Postgres authority for technical knowledge.

Postgres is the only authority. Qdrant can propose claim IDs, but it cannot mint or extend an
authority epoch. An epoch combines a monotonic transactionally bumped sequence with the exact
currently usable claim set for the request tenant (plus the global knowledge tenant). Including
the effective claim set means a review expiry changes the epoch at the first request after expiry
even when no scheduler has updated a row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
from typing import Callable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from sealai_v2.db.models import V2KnowledgeAuthorityEpoch, V2KnowledgeClaim

AUTHORITY_SCOPE = "knowledge"
GLOBAL_KNOWLEDGE_TENANT = "sealai"
_HUMAN_REVIEW_ORIGINS = frozenset({"human_api", "human_seed"})


class KnowledgeAuthorityUnavailable(RuntimeError):
    """The Postgres authority cannot be proven; serving must fail closed."""


class KnowledgeAuthorityChanged(RuntimeError):
    """Authority changed while a request was in flight; no response may be served."""


@dataclass(frozen=True)
class AuthorityEpoch:
    tenant_id: str
    sequence: int
    value: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _human_actor(value: str | None) -> bool:
    actor = (value or "").strip().lower()
    return bool(actor) and not any(
        marker in actor
        for marker in ("codex", "llm", "model", "agent", "release-bootstrap")
    )


def _approved_is_current(row: V2KnowledgeClaim, *, at: datetime) -> bool:
    expiry = _parse_timestamp(row.review_expires_at)
    return bool(
        row.review_status == "approved"
        and row.review_origin in _HUMAN_REVIEW_ORIGINS
        and row.sources_json
        and row.evidence_json
        and row.applicability_json
        and row.reviewed_at
        and _human_actor(row.reviewed_by)
        and expiry is not None
        and expiry > at
        and row.uncertainty
        in {"bounded", "conditional", "conflicted", "not_sufficiently_supported"}
        and row.transferability
        in {
            "source_specific",
            "family_level_orientation",
            "application_dependent",
            "not_assessed",
        }
    )


def bump_authority_epoch(session: Session, *, now: str) -> int:
    """Bump the epoch inside the caller's claim-lifecycle transaction."""

    row = session.scalar(
        select(V2KnowledgeAuthorityEpoch)
        .where(V2KnowledgeAuthorityEpoch.scope == AUTHORITY_SCOPE)
        .with_for_update()
    )
    if row is None:
        row = V2KnowledgeAuthorityEpoch(
            scope=AUTHORITY_SCOPE, sequence=1, updated_at=now
        )
        session.add(row)
    else:
        row.sequence += 1
        row.updated_at = now
    session.flush()
    return row.sequence


class PostgresKnowledgeAuthority:
    """Reads a canonical tenant-bound epoch from Postgres and rechecks it on demand."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._sf = session_factory
        self._clock = clock

    def capture(self, *, tenant_id: str) -> AuthorityEpoch:
        if not tenant_id.strip():
            raise KnowledgeAuthorityUnavailable(
                "knowledge authority tenant is required"
            )
        try:
            with self._sf() as session:
                epoch_row = session.get(V2KnowledgeAuthorityEpoch, AUTHORITY_SCOPE)
                if epoch_row is None:
                    raise KnowledgeAuthorityUnavailable(
                        "knowledge authority epoch is not initialized"
                    )
                claims = session.scalars(
                    select(V2KnowledgeClaim).where(
                        V2KnowledgeClaim.tenant_id.in_(
                            {tenant_id, GLOBAL_KNOWLEDGE_TENANT}
                        ),
                        V2KnowledgeClaim.active.is_(True),
                        V2KnowledgeClaim.review_status.in_(("approved", "draft")),
                    )
                ).all()
                at = self._clock()
                usable = [
                    row
                    for row in claims
                    if row.review_status == "draft" or _approved_is_current(row, at=at)
                ]
                material = {
                    "schema": 1,
                    "scope": AUTHORITY_SCOPE,
                    "tenant": tenant_id,
                    "sequence": epoch_row.sequence,
                    "claims": [
                        [
                            row.tenant_id,
                            row.id,
                            row.version,
                            row.review_status,
                            row.authority_fingerprint,
                            row.review_expires_at or "",
                        ]
                        for row in sorted(
                            usable, key=lambda item: (item.tenant_id, item.id)
                        )
                    ],
                }
        except KnowledgeAuthorityUnavailable:
            raise
        except SQLAlchemyError as exc:
            raise KnowledgeAuthorityUnavailable(
                "Postgres knowledge authority is unavailable"
            ) from exc
        canonical = json.dumps(
            material, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        return AuthorityEpoch(
            tenant_id=tenant_id,
            sequence=epoch_row.sequence,
            value=f"sha256:{sha256(canonical.encode()).hexdigest()}",
        )

    def assert_current(self, captured: AuthorityEpoch) -> None:
        current = self.capture(tenant_id=captured.tenant_id)
        if not hmac.compare_digest(current.value, captured.value):
            raise KnowledgeAuthorityChanged(
                "knowledge authority changed while request was in flight"
            )


@dataclass(frozen=True)
class RequestAuthorityGuard:
    """Immutable request binding with an explicit just-before-serve recheck."""

    store: PostgresKnowledgeAuthority
    captured: AuthorityEpoch

    @classmethod
    def bind(
        cls, store: PostgresKnowledgeAuthority, *, tenant_id: str
    ) -> "RequestAuthorityGuard":
        return cls(store=store, captured=store.capture(tenant_id=tenant_id))

    def recheck_before_serve(self) -> None:
        self.store.assert_current(self.captured)
