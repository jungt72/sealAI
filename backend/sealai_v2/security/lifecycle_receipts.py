"""Server-signed immutable lifecycle transition receipts."""

from __future__ import annotations

import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from sealai_v2.security.lifecycle_control import idempotency_key_hash


def _iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _digest(secret: bytes, domain: str, payload: dict) -> str:
    message = (
        domain
        + "\x00"
        + json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    ).encode("utf-8")
    return hmac.new(secret, message, sha256).hexdigest()


@dataclass(frozen=True)
class LifecycleReceipt:
    receipt_id: str
    resource_type: str
    resource_id: str
    reason_code: str
    policy_authority_ref: str
    lifecycle_state: str
    issued_at: str
    receipt_digest: str
    replay: bool = False


@dataclass(frozen=True)
class LifecycleEventRecord:
    event_id: str
    receipt_id: str
    resource_type: str
    resource_id: str
    tenant_id: str
    actor_ref: str
    event_type: str
    from_state: str
    to_state: str
    reason_code: str
    policy_authority_ref: str
    created_at: str
    event_digest: str


@dataclass(frozen=True)
class SignedLifecycleTransition:
    receipt: LifecycleReceipt
    event: LifecycleEventRecord
    tenant_ref: str
    actor_ref: str
    idempotency_hash: str


def sign_lifecycle_transition(
    *,
    secret: str,
    action: str,
    idempotency_key: str,
    resource_type: str,
    resource_id: str,
    tenant_id: str,
    tenant_ref: str,
    actor_ref: str,
    event_type: str,
    from_state: str,
    to_state: str,
    reason_code: str,
    policy_authority_ref: str,
    now: datetime | None = None,
) -> SignedLifecycleTransition:
    secret_bytes = secret.encode("utf-8")
    if len(secret_bytes) < 32:
        raise ValueError("lifecycle receipt secret must be at least 32 bytes")
    issued_at = _iso(now or datetime.now(timezone.utc))
    receipt_id = str(uuid.uuid4())
    idem_hash = idempotency_key_hash(action, idempotency_key)
    receipt_payload = {
        "receipt_id": receipt_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "tenant_ref": tenant_ref,
        "actor_ref": actor_ref,
        "idempotency_key_hash": idem_hash,
        "reason_code": reason_code,
        "policy_authority_ref": policy_authority_ref,
        "lifecycle_state": to_state,
        "issued_at": issued_at,
    }
    receipt_digest = _digest(
        secret_bytes, "sealai-api-lifecycle-receipt-v1", receipt_payload
    )
    event_id = str(uuid.uuid4())
    event_payload = {
        "event_id": event_id,
        "receipt_id": receipt_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "tenant_id": tenant_id,
        "actor_ref": actor_ref,
        "event_type": event_type,
        "from_state": from_state,
        "to_state": to_state,
        "reason_code": reason_code,
        "policy_authority_ref": policy_authority_ref,
        "created_at": issued_at,
        "receipt_digest": receipt_digest,
    }
    event_digest = _digest(secret_bytes, "sealai-api-lifecycle-event-v1", event_payload)
    return SignedLifecycleTransition(
        receipt=LifecycleReceipt(
            receipt_id=receipt_id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason_code=reason_code,
            policy_authority_ref=policy_authority_ref,
            lifecycle_state=to_state,
            issued_at=issued_at,
            receipt_digest=receipt_digest,
        ),
        event=LifecycleEventRecord(
            event_id=event_id,
            receipt_id=receipt_id,
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            reason_code=reason_code,
            policy_authority_ref=policy_authority_ref,
            created_at=issued_at,
            event_digest=event_digest,
        ),
        tenant_ref=tenant_ref,
        actor_ref=actor_ref,
        idempotency_hash=idem_hash,
    )
