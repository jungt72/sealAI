#!/usr/bin/env python3
"""Deterministic metadata enrichment for sealai_knowledge_v3."""

from __future__ import annotations

import argparse
import html
import os
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient


MATERIAL_PATTERN = re.compile(
    r"\b("  # Known seal materials + optional hardness suffix
    r"NBR|HNBR|FKM|FFKM|EPDM|VMQ|FVMQ|PTFE|PU|PUR|TPU|PEEK"
    r")(?:[-_/]?(\d{2,3}))?\b",
    re.IGNORECASE,
)
SHORE_PATTERN = re.compile(r"\b(?:shore(?:\s*[ad])?|sh)\s*[:=]?\s*(\d{2,3})\b", re.IGNORECASE)
KYROLON_PATTERN = re.compile(r"\bkyrolon\s+(\d{2,3})[a-z]?\b", re.IGNORECASE)
TEMP_RANGE_C_PATTERN = re.compile(
    r"([−-]?\d{1,3}(?:[.,]\d+)?)\s*(?:to|bis|[-–—]{1,2})\s*([−-]?\d{1,3}(?:[.,]\d+)?)\s*°\s*c\b",
    re.IGNORECASE,
)
TEMP_C_VALUE_PATTERN = re.compile(r"([−-]?\d{1,3}(?:[.,]\d+)?)\s*°\s*c\b", re.IGNORECASE)
TEMP_UPPER_THRESHOLD_PATTERN = re.compile(
    r"(?:over|above|ueber|über|oberhalb|beginnt bei)\s*([−-]?\d{1,3}(?:[.,]\d+)?)\s*°\s*c\b",
    re.IGNORECASE,
)

MATERIAL_DEFAULTS: dict[str, tuple[int, tuple[float, float]]] = {
    "PTFE": (79, (-200.0, 260.0)),
    "NBR": (70, (-30.0, 100.0)),
    "HNBR": (80, (-30.0, 150.0)),
    "FKM": (75, (-20.0, 200.0)),
    "FFKM": (80, (-20.0, 325.0)),
    "EPDM": (70, (-40.0, 140.0)),
    "VMQ": (70, (-55.0, 200.0)),
    "FVMQ": (70, (-55.0, 175.0)),
    "PU": (90, (-30.0, 100.0)),
    "PUR": (90, (-30.0, 100.0)),
    "TPU": (90, (-30.0, 100.0)),
    "PEEK": (85, (-60.0, 250.0)),
    "UNKNOWN": (70, (-40.0, 120.0)),
}


@dataclass(frozen=True)
class ExtractedSpec:
    material_code: str
    shore_hardness: int
    min_c: float
    max_c: float


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace("−", "-").replace(",", "."))
    except ValueError:
        return None


def _normalize_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    normalized = (
        raw.replace("</w:p>", "\n")
        .replace("</w:tr>", "\n")
        .replace("</w:tc>", "\t")
    )
    text = re.sub(r"<[^>]+>", "", normalized)
    return html.unescape(text)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        try:
            return _normalize_docx_text(path)
        except Exception:
            return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="replace")
    except Exception:
        return ""


def _map_source_to_local_path(source: str | None, uploads_root: Path, fallback_filename: str) -> Path | None:
    if source:
        src = source.strip()
        if src:
            if src.startswith("/app/data/uploads/"):
                rel = src[len("/app/data/uploads/") :]
                candidate = uploads_root / rel
                if candidate.exists():
                    return candidate
            candidate = Path(src)
            if candidate.exists():
                return candidate
    if fallback_filename:
        matches = list(uploads_root.rglob(fallback_filename))
        if len(matches) == 1:
            return matches[0]
    return None


def _extract_material_code(text: str, filename: str) -> str:
    haystack = f"{filename}\n{text}"
    matches = list(MATERIAL_PATTERN.finditer(haystack))
    if matches:
        # Prefer explicit hardness-coded material (e.g. NBR-70) over plain material token.
        matches.sort(key=lambda m: 1 if m.group(2) else 0, reverse=True)
        mat = (matches[0].group(1) or "").upper()
        hardness = matches[0].group(2)
        return f"{mat}-{hardness}" if hardness else mat
    if "kyrolon" in haystack.lower():
        return "PTFE"
    return "UNKNOWN"


def _extract_shore_hardness(text: str, filename: str, material_code: str) -> int:
    haystack = f"{filename}\n{text}"
    code_match = re.search(r"(?:-|_)(\d{2,3})\b", material_code)
    if code_match:
        value = int(code_match.group(1))
        if 0 <= value <= 120:
            return value

    kyrolon_match = KYROLON_PATTERN.search(haystack)
    if kyrolon_match:
        value = int(kyrolon_match.group(1))
        if 0 <= value <= 120:
            return value

    shore_candidates: list[int] = []
    for shore_match in SHORE_PATTERN.finditer(haystack):
        value = int(shore_match.group(1))
        if 0 <= value <= 120:
            shore_candidates.append(value)
    if shore_candidates:
        # Prefer the higher hardness candidate for mixed notations like "Shore D >=60 ... 10-20".
        return max(shore_candidates)

    base = material_code.split("-", 1)[0].upper()
    return MATERIAL_DEFAULTS.get(base, MATERIAL_DEFAULTS["UNKNOWN"])[0]


def _extract_temp_range(text: str, material_code: str) -> tuple[float, float]:
    candidates: list[tuple[float, float]] = []
    for match in TEMP_RANGE_C_PATTERN.finditer(text):
        lo = _to_float(match.group(1))
        hi = _to_float(match.group(2))
        if lo is None or hi is None:
            continue
        lo, hi = min(lo, hi), max(lo, hi)
        # Skip purely decomposition-style high ranges (e.g. 650-700 C) as operating envelopes.
        if lo >= 150.0 and hi >= 300.0:
            continue
        candidates.append((lo, hi))

    if candidates:
        # Prefer range with widest spread (typically actual envelope versus narrow decomposition range).
        candidates.sort(key=lambda item: item[1] - item[0], reverse=True)
        return candidates[0]

    c_values: list[float] = []
    for match in TEMP_C_VALUE_PATTERN.finditer(text):
        parsed = _to_float(match.group(1))
        if parsed is None:
            continue
        c_values.append(parsed)

    if c_values:
        negatives = [value for value in c_values if value < 0]
        thresholds: list[float] = []
        for match in TEMP_UPPER_THRESHOLD_PATTERN.finditer(text):
            parsed = _to_float(match.group(1))
            if parsed is None:
                continue
            if 30.0 <= parsed <= 400.0:
                thresholds.append(parsed)
        if negatives and thresholds:
            return (min(negatives), min(thresholds))
        if len(c_values) >= 2:
            bounded = [value for value in c_values if -300.0 <= value <= 400.0]
            if bounded:
                return (min(bounded), max(bounded))

    base = material_code.split("-", 1)[0].upper()
    return MATERIAL_DEFAULTS.get(base, MATERIAL_DEFAULTS["UNKNOWN"])[1]


def _extract_specs(text: str, filename: str) -> ExtractedSpec:
    material_code = _extract_material_code(text=text, filename=filename)
    shore = _extract_shore_hardness(text=text, filename=filename, material_code=material_code)
    min_c, max_c = _extract_temp_range(text=text, material_code=material_code)
    if min_c > max_c:
        min_c, max_c = max_c, min_c
    return ExtractedSpec(
        material_code=material_code,
        shore_hardness=shore,
        min_c=float(min_c),
        max_c=float(max_c),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill RAG technical metadata in Qdrant.")
    parser.add_argument("--collection", default="sealai_knowledge_v3")
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY") or None)
    parser.add_argument("--uploads-root", default="data/backend/uploads")
    parser.add_argument("--apply", action="store_true", help="Persist updates to Qdrant.")
    args = parser.parse_args()

    uploads_root = Path(args.uploads_root).resolve()
    client = QdrantClient(url=args.qdrant_url, api_key=args.qdrant_api_key)

    by_doc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"points": [], "filename": "", "source": "", "text_parts": []}
    )

    offset: Any = None
    while True:
        points, offset = client.scroll(
            collection_name=args.collection,
            limit=128,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for point in points:
            payload = point.payload or {}
            metadata = payload.get("metadata") or {}
            doc_id = str(payload.get("document_id") or metadata.get("document_id") or metadata.get("doc_id") or "")
            if not doc_id:
                continue
            record = by_doc[doc_id]
            record["points"].append(point)
            if not record["filename"]:
                record["filename"] = str(payload.get("filename") or metadata.get("title") or "")
            if not record["source"]:
                record["source"] = str(payload.get("source") or metadata.get("source_uri") or "")
            chunk_text = str(payload.get("text") or metadata.get("text") or "")
            if chunk_text.strip():
                record["text_parts"].append(chunk_text)
        if offset is None:
            break

    updated_points = 0
    doc_rows: list[str] = []

    for doc_id, info in sorted(by_doc.items(), key=lambda item: item[0]):
        filename = str(info.get("filename") or "")
        source = str(info.get("source") or "")
        local_path = _map_source_to_local_path(source=source, uploads_root=uploads_root, fallback_filename=filename)
        file_text = _read_text(local_path) if local_path else ""
        merged_text = "\n".join([file_text, *info.get("text_parts", [])])
        specs = _extract_specs(merged_text, filename=filename)

        doc_rows.append(
            f"{doc_id} | {filename or 'n/a'} | {specs.material_code} | Shore {specs.shore_hardness} | "
            f"{specs.min_c:.2f}..{specs.max_c:.2f} C | {str(local_path) if local_path else 'unresolved'}"
        )

        for point in info["points"]:
            payload = dict(point.payload or {})
            metadata = dict(payload.get("metadata") or {})
            payload["material_code"] = specs.material_code
            payload["shore_hardness"] = specs.shore_hardness
            payload["temp_range"] = {"min_c": specs.min_c, "max_c": specs.max_c}
            metadata["material_code"] = specs.material_code
            metadata["shore_hardness"] = specs.shore_hardness
            metadata["temp_range"] = {"min_c": specs.min_c, "max_c": specs.max_c}
            payload["metadata"] = metadata

            if args.apply:
                client.overwrite_payload(
                    collection_name=args.collection,
                    points=[point.id],
                    payload=payload,
                )
            updated_points += 1

    print(f"documents={len(by_doc)} points={updated_points} apply={args.apply}")
    for row in doc_rows:
        print(row)

    if args.apply:
        null_material = 0
        null_shore = 0
        null_temp = 0
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=args.collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for point in points:
                payload = point.payload or {}
                metadata = payload.get("metadata") or {}
                material = payload.get("material_code")
                shore = payload.get("shore_hardness")
                temp = payload.get("temp_range")
                if material in (None, "", "None"):
                    material = metadata.get("material_code")
                if shore in (None, "", "None"):
                    shore = metadata.get("shore_hardness")
                if not isinstance(temp, dict):
                    temp = metadata.get("temp_range")
                if material in (None, "", "None"):
                    null_material += 1
                if shore in (None, "", "None"):
                    null_shore += 1
                if not isinstance(temp, dict) or temp.get("min_c") is None or temp.get("max_c") is None:
                    null_temp += 1
            if offset is None:
                break
        print(f"post_check_null_material={null_material} post_check_null_shore={null_shore} post_check_null_temp={null_temp}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
