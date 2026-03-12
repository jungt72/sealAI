from __future__ import annotations

from typing import Any, Iterable, List, Optional

DEFAULT_ROUTE_KEY = "general_technical_doc"

ROUTE_KEYS = (
    "product_datasheet",
    "material_datasheet",
    "technical_knowledge",
    "standard_or_norm",
    "general_technical_doc",
)

_EXPLICIT_ROUTE_TAGS = {
    "route:product_datasheet": "product_datasheet",
    "route:material_datasheet": "material_datasheet",
    "route:technical_knowledge": "technical_knowledge",
    "route:standard_or_norm": "standard_or_norm",
    "route:general_technical_doc": "general_technical_doc",
    "ingest_route:product_datasheet": "product_datasheet",
    "ingest_route:material_datasheet": "material_datasheet",
    "ingest_route:technical_knowledge": "technical_knowledge",
    "ingest_route:standard_or_norm": "standard_or_norm",
    "ingest_route:general_technical_doc": "general_technical_doc",
}

_ROUTE_KEYWORDS = (
    ("product_datasheet", ("product_datasheet", "produktdatenblatt", "dichtungstyp", "seal_type", "product")),
    ("material_datasheet", ("material_datasheet", "werkstoffdatenblatt", "compound", "material", "werkstoff")),
    ("standard_or_norm", ("standard_or_norm", "norm", "standard", "specification", "spezifikation")),
    ("technical_knowledge", ("technical_knowledge", "fachwissen", "application_note", "guide", "knowledge")),
    ("general_technical_doc", ("general_technical_doc", "technical_doc", "technical_document", "pdf")),
)

_CATEGORY_ROUTE_MAP = {
    "product": "product_datasheet",
    "material": "material_datasheet",
    "datasheet": "material_datasheet",
    "technical": "technical_knowledge",
    "standard": "standard_or_norm",
    "norm": "standard_or_norm",
    "norms": "standard_or_norm",
    "specs": "standard_or_norm",
}


def coerce_tag_strings(raw_tags: Any) -> List[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        items = [raw_tags]
    elif isinstance(raw_tags, (list, tuple, set)):
        items = list(raw_tags)
    else:
        items = [raw_tags]

    tags: List[str] = []
    seen: set[str] = set()
    for item in items:
        value: Optional[str] = None
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            for key in ("name", "slug", "tag", "label"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    value = candidate.strip()
                    break
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(value)
    return tags


def resolve_route_key(
    *,
    tags: Iterable[str] | None = None,
    category: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    normalized_tags = [str(tag).strip().lower() for tag in (tags or []) if str(tag).strip()]

    for tag in normalized_tags:
        explicit = _EXPLICIT_ROUTE_TAGS.get(tag)
        if explicit:
            return explicit

    for route_key, keywords in _ROUTE_KEYWORDS:
        if any(keyword in tag for tag in normalized_tags for keyword in keywords):
            return route_key

    category_value = str(category or "").strip().lower()
    if category_value:
        mapped = _CATEGORY_ROUTE_MAP.get(category_value)
        if mapped:
            return mapped

    name = str(filename or "").strip().lower()
    if "norm" in name or "standard" in name:
        return "standard_or_norm"
    if "material" in name or "compound" in name:
        return "material_datasheet"
    if "product" in name or "datasheet" in name:
        return "product_datasheet"

    return DEFAULT_ROUTE_KEY
