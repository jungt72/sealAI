from __future__ import annotations


def qdrant_collection_name(
    *,
    base: str,
    prefix: str | None,
    tenant_id: str | None,
) -> str:
    clean_base = (base or "").strip()
    return clean_base


__all__ = ["qdrant_collection_name"]
