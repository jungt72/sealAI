"""Paperless-ngx REST client — the ONE place that talks to Paperless (build-spec §3 Paperless path).

Pure I/O helper (stdlib urllib, no new dep). Shared by the manual review-queue CLI
(``ops/ingest_fachkarte.py``) and the auto-ingestion webhook route (``api/routes/rag_ingest.py``) so
there is exactly one fetch implementation. Config comes from the environment directly
(``PAPERLESS_URL`` / ``PAPERLESS_TOKEN`` — no ``SEALAI_V2_`` prefix, matching the existing .env
convention), not the pydantic ``Settings`` (which would look for a prefixed name).
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


class PaperlessConfigError(RuntimeError):
    """PAPERLESS_URL / PAPERLESS_TOKEN missing from the environment."""


def _base_and_token() -> tuple[str, str]:
    base = os.environ.get("PAPERLESS_URL", "").rstrip("/")
    token = os.environ.get("PAPERLESS_TOKEN", "")
    if not base or not token:
        raise PaperlessConfigError("PAPERLESS_URL / PAPERLESS_TOKEN not set in env")
    return base, token


def fetch_document(doc_id: str | int) -> dict:
    """One document's raw Paperless API payload (id, title, content, tags — tag IDs, not names)."""
    base, token = _base_and_token()
    req = urllib.request.Request(
        f"{base}/api/documents/{doc_id}/", headers={"Authorization": f"Token {token}"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 — trusted internal Paperless
        return json.load(r)


def fetch_tag_names(tag_ids: list[int]) -> tuple[str, ...]:
    """Resolve Paperless tag IDs -> names (one call per id; a document carries only a handful)."""
    if not tag_ids:
        return ()
    base, token = _base_and_token()
    names: list[str] = []
    for tid in tag_ids:
        req = urllib.request.Request(
            f"{base}/api/tags/{tid}/", headers={"Authorization": f"Token {token}"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            names.append(str(json.load(r).get("name", "")))
    return tuple(n for n in names if n)


def fetch_document_text_and_tags(doc_id: str | int) -> tuple[str, str, tuple[str, ...]]:
    """(content, source-provenance-label, tag names) for one document — the shape every caller needs."""
    doc = fetch_document(doc_id)
    title = (doc.get("title") or f"doc-{doc_id}")[:80]
    tags = fetch_tag_names(doc.get("tags") or [])
    return doc.get("content") or "", f"paperless#{doc_id}:{title}", tags


def find_tag_id(name: str) -> int | None:
    """The Paperless tag id for an EXISTING tag name (exact match), or None. Read-only lookup — never
    creates a tag (tag creation/taxonomy is an owner decision, not something the ingestion path does)."""
    base, token = _base_and_token()
    req = urllib.request.Request(
        f"{base}/api/tags/?name__iexact={urllib.parse.quote(name)}",
        headers={"Authorization": f"Token {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        results = json.load(r).get("results") or []
    return int(results[0]["id"]) if results else None


def add_tag_to_document(doc_id: str | int, tag_id: int) -> None:
    """Add ``tag_id`` to a document's tag set (idempotent — a no-op if already present). Paperless's
    document PATCH replaces the WHOLE tags list, so this fetches the current set first and appends."""
    doc = fetch_document(doc_id)
    current = doc.get("tags") or []
    if tag_id in current:
        return
    _patch_tags(doc_id, current + [tag_id])


def remove_tag_from_document(doc_id: str | int, tag_id: int) -> None:
    """Remove ``tag_id`` from a document's tag set (idempotent — a no-op if already absent). Used to
    clear a stale ``sealai:status-failed`` once a later attempt succeeds, so the status tags never
    lie (failed + draft both present would read as "broken AND indexed" — ambiguous)."""
    doc = fetch_document(doc_id)
    current = doc.get("tags") or []
    if tag_id not in current:
        return
    _patch_tags(doc_id, [t for t in current if t != tag_id])


def _patch_tags(doc_id: str | int, tag_ids: list[int]) -> None:
    base, token = _base_and_token()
    body = json.dumps({"tags": tag_ids}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/documents/{doc_id}/",
        data=body,
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        r.read()
