from __future__ import annotations

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

PAPERLESS_PILOT_TAGS: tuple[str, ...] = (
    "doc_type:datasheet",
    "sts_mat:STS-MAT-SIC-A1",
    "sts_type:STS-TYPE-GS-CART",
    "lang:de",
    "source:hersteller-name",
)

PAPERLESS_PILOT_FIELDS: tuple[str, ...] = ("doc_type", "sts_mat", "sts_type", "lang", "source")
PAPERLESS_INGEST_BASIS_FIELDS: tuple[str, ...] = ("sts_mat", "sts_type", "sts_med", "sts_rs")


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
        values.append(tag[len(prefix):].strip())
    return [value for value in values if value]


def parse_paperless_tags(raw_tags: Any) -> dict[str, Any]:
    tags = _coerce_tags(raw_tags)
    parsed = {
        "raw_tags": tags,
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
    has_ingest_basis = any(parsed[f"{field}_codes"] for field in PAPERLESS_INGEST_BASIS_FIELDS)
    missing_pilot_fields = [field for field in PAPERLESS_PILOT_FIELDS if field not in present_fields]
    return {
        "parsed": parsed,
        "present_fields": sorted(present_fields),
        "ingest_ready": bool(parsed["doc_type"] and has_ingest_basis),
        "pilot_ready": len(missing_pilot_fields) == 0,
        "missing_pilot_fields": missing_pilot_fields,
    }
