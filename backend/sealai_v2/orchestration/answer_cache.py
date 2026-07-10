"""Tenant-scoped exact cache for fully validated low-risk answers."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass

from sealai_v2.core.contracts import Answer


def exact_answer_key(*, tenant_id: str, question: str, namespace: str) -> str:
    normalized = " ".join(question.casefold().split())
    material = f"{tenant_id}\x00{namespace}\x00{normalized}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _Entry:
    answer: Answer
    expires_at: float


class InProcessExactAnswerCache:
    """Bounded process-local cache; no cross-tenant or stale-knowledge fallback."""

    def __init__(self, *, max_entries: int = 512, ttl_s: float = 3600.0) -> None:
        self._max_entries = max(1, max_entries)
        self._ttl_s = max(1.0, ttl_s)
        self._entries: OrderedDict[str, _Entry] = OrderedDict()

    def get(self, key: str) -> Answer | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return entry.answer

    def put(self, key: str, answer: Answer) -> None:
        self._entries[key] = _Entry(
            answer=answer, expires_at=time.monotonic() + self._ttl_s
        )
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
