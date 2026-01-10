from __future__ import annotations

import hashlib
from typing import Any

__all__ = [
    "build_point_ids",
    "file_source_id",
    "qdrant_point_id",
    "stable_sha256_hex",
]


def stable_sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_source_id(file_path: str) -> str:
    try:
        with open(file_path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return stable_sha256_hex(file_path)


def qdrant_point_id(*, tenant_id: str, source_id: str, chunk_index: int, chunk_text: str) -> str:
    canonical = f"{tenant_id}|{source_id}|{chunk_index}|{stable_sha256_hex(chunk_text)}"
    return stable_sha256_hex(canonical)


def build_point_ids(*, tenant_id: str, source_id: str, chunks: list[Any]) -> list[str]:
    ids: list[str] = []
    for index, doc in enumerate(chunks):
        text = getattr(doc, "page_content", "") or ""
        ids.append(
            qdrant_point_id(
                tenant_id=tenant_id,
                source_id=source_id,
                chunk_index=index,
                chunk_text=text,
            )
        )
    return ids
