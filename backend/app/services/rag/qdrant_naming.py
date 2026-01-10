from __future__ import annotations


def qdrant_collection_name(
    *,
    base: str,
    prefix: str | None,
    tenant_id: str | None,
) -> str:
    clean_base = (base or "").strip()
    clean_prefix = (prefix or "").strip()
    clean_tenant = (tenant_id or "").strip()
    if clean_prefix and clean_tenant:
        return f"{clean_prefix}:{clean_tenant}"
    return clean_base


__all__ = ["qdrant_collection_name"]
