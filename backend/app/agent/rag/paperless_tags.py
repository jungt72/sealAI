from __future__ import annotations

import re
from typing import Any

PAPERLESS_TAG_PREFIXES: dict[str, str] = {
    "sts_mat": "sts_mat:",
    "sts_type": "sts_type:",
    "doc_type": "doc_type:",
    "lang": "lang:",
    "source": "source:",
    "sts_med": "sts_med:",
    "sts_rs": "sts_rs:",
    "norm": "norm:",
    "industry": "industry:",
}

PAPERLESS_RAG_ENABLE_TAGS: frozenset[str] = frozenset(
    {
        "rag:enabled",
        "rag:enable",
        "rag:yes",
        "sealai:rag",
        "sealingai:rag",
        "sealai-rag",
        "sealai_rag",
        "sealingai-rag",
        "sealingai_rag",
    }
)

PAPERLESS_PILOT_TAGS: tuple[str, ...] = (
    "rag:enabled",
    "doc_type:datasheet",
    "sts_mat:STS-MAT-SIC-A1",
    "sts_type:STS-TYPE-GS-CART",
    "lang:de",
    "source:hersteller-name",
)

PAPERLESS_PILOT_FIELDS: tuple[str, ...] = (
    "doc_type",
    "sts_mat",
    "sts_type",
    "lang",
    "source",
)
PAPERLESS_INGEST_BASIS_FIELDS: tuple[str, ...] = (
    "sts_mat",
    "sts_type",
    "sts_med",
    "sts_rs",
)

_SMART_MATERIAL_TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("STS-MAT-HNBR-A1", ("hnbr", "hydrierter nitrilkautschuk")),
    ("STS-MAT-FFKM-A1", ("ffkm",)),
    ("STS-MAT-PTFE-A1", ("ptfe", "teflon")),
    ("STS-MAT-EPDM-A1", ("epdm",)),
    ("STS-MAT-FKM-A1", ("fkm", "viton")),
    (
        "STS-MAT-NBR-A1",
        ("nbr", "nitril", "nitrilkautschuk", "buna-n", "buna n", "perbunan"),
    ),
    ("STS-MAT-SIC-A1", ("sic", "siliciumcarbid", "silicon carbide")),
)

_TECHNICAL_KNOWLEDGE_HINTS = (
    "deep research",
    "research",
    "report",
    "fachwissen",
    "grundlagen",
    "guide",
    "application note",
    "whitepaper",
    "technical knowledge",
)
_DATASHEET_HINTS = ("datasheet", "datenblatt", "data sheet", "werkstoffdatenblatt")


def _coerce_tags(raw_tags: Any) -> list[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        items = [raw_tags]
    elif isinstance(raw_tags, (list, tuple, set)):
        items = list(raw_tags)
    else:
        items = [raw_tags]

    tags: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(value)
    return tags


def _values_for_prefix(tags: list[str], prefix: str) -> list[str]:
    values: list[str] = []
    prefix_lower = prefix.lower()
    for tag in tags:
        lowered = tag.lower()
        if not lowered.startswith(prefix_lower):
            continue
        values.append(tag[len(prefix) :].strip())
    return [value for value in values if value]


def has_paperless_rag_flag(raw_tags: Any) -> bool:
    tags = _coerce_tags(raw_tags)
    return any(tag.strip().lower() in PAPERLESS_RAG_ENABLE_TAGS for tag in tags)


def _has_prefix(tags: list[str], prefix: str) -> bool:
    prefix_lower = prefix.lower()
    return any(tag.lower().startswith(prefix_lower) for tag in tags)


def _append_tag(tags: list[str], value: str) -> None:
    lowered = value.lower()
    if lowered not in {tag.lower() for tag in tags}:
        tags.append(value)


def _contains_token(haystack: str, token: str) -> bool:
    escaped = re.escape(token)
    if re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", haystack):
        return True
    return token in haystack


def augment_paperless_tags_for_rag(
    raw_tags: Any,
    *,
    title: str | None = None,
    filename: str | None = None,
) -> list[str]:
    """Infer safe RAG routing tags from Paperless metadata.

    The user-facing workflow should stay simple: one explicit RAG enable tag is
    enough. We only add conservative, transparent metadata that can be inferred
    from title/filename. The explicit RAG flag remains mandatory.
    """
    tags = _coerce_tags(raw_tags)
    if not has_paperless_rag_flag(tags):
        return tags

    text = f"{title or ''} {filename or ''}".strip().lower()

    if not _has_prefix(tags, PAPERLESS_TAG_PREFIXES["doc_type"]):
        if any(hint in text for hint in _DATASHEET_HINTS):
            _append_tag(tags, "doc_type:datasheet")
        else:
            _append_tag(tags, "doc_type:technical_knowledge")

    if not any(tag.lower().startswith(("route:", "ingest_route:")) for tag in tags):
        if any(hint in text for hint in _DATASHEET_HINTS):
            _append_tag(tags, "route:material_datasheet")
        elif any(hint in text for hint in _TECHNICAL_KNOWLEDGE_HINTS):
            _append_tag(tags, "route:technical_knowledge")

    if not _has_prefix(tags, PAPERLESS_TAG_PREFIXES["sts_mat"]):
        for code, aliases in _SMART_MATERIAL_TAGS:
            if any(_contains_token(text, alias) for alias in aliases):
                _append_tag(tags, f"sts_mat:{code}")
                break

    return tags


def parse_paperless_tags(raw_tags: Any) -> dict[str, Any]:
    tags = _coerce_tags(raw_tags)
    parsed = {
        "raw_tags": tags,
        "rag_enabled": has_paperless_rag_flag(tags),
        "doc_type": None,
        "language": None,
        "source": None,
        "sts_mat_codes": _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["sts_mat"]),
        "sts_type_codes": _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["sts_type"]),
        "sts_med_codes": _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["sts_med"]),
        "sts_rs_codes": _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["sts_rs"]),
        "norm_references": _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["norm"]),
        "industries": _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["industry"]),
    }
    doc_types = _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["doc_type"])
    languages = _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["lang"])
    sources = _values_for_prefix(tags, PAPERLESS_TAG_PREFIXES["source"])
    parsed["doc_type"] = doc_types[0] if doc_types else None
    parsed["language"] = languages[0] if languages else None
    parsed["source"] = sources[0] if sources else None
    return parsed


def evaluate_paperless_tag_readiness(raw_tags: Any) -> dict[str, Any]:
    parsed = parse_paperless_tags(raw_tags)
    present_fields = {
        field
        for field, prefix in PAPERLESS_TAG_PREFIXES.items()
        if _values_for_prefix(parsed["raw_tags"], prefix)
    }
    has_ingest_basis = any(
        parsed[f"{field}_codes"] for field in PAPERLESS_INGEST_BASIS_FIELDS
    )
    missing_pilot_fields = [
        field for field in PAPERLESS_PILOT_FIELDS if field not in present_fields
    ]
    return {
        "parsed": parsed,
        "present_fields": sorted(present_fields),
        "rag_enabled": bool(parsed["rag_enabled"]),
        "ingest_ready": bool(
            parsed["rag_enabled"] and parsed["doc_type"] and has_ingest_basis
        ),
        "pilot_ready": bool(parsed["rag_enabled"] and len(missing_pilot_fields) == 0),
        "missing_pilot_fields": missing_pilot_fields,
    }
