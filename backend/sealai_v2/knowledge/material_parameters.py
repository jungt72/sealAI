"""Structured material-parameter store (V2.2). Pure, no LLM. The KERNEL owns the parameters (operating
limits, Shore hardness, density, chemical resistance, …); L1 only RENDERS them as a table — the numbers
never come from the model (no-fake-precision / "Kernel besitzt die Fakten, L1 erzählt nur"). Each material
carries a ``review_state`` ('reviewed' = owner-grounded | 'draft' = vorläufige Richtwerte): until reviewed
the render shows the vorläufig marker. A missing parameter is NOT invented — the caller renders it as '—'.

The store is data-driven (``material_parameters_seed.json``) so curation = editing JSON + the owner's
multi-LLM review, never code. This module just loads + matches; it asserts no engineering values itself.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_SEED = Path(__file__).resolve().parent / "material_parameters_seed.json"


def _validated_blocks(data: dict) -> dict:
    blocks = {k: v for k, v in data.items() if not k.startswith("_")}
    for material, block in blocks.items():
        state = block.get("review_state")
        if state not in {"reviewed", "draft"}:
            raise ValueError(
                f"{material}: invalid material-parameter review_state {state!r}"
            )
        params = block.get("params")
        if not isinstance(params, list) or not params:
            raise ValueError(f"{material}: material-parameter block requires params")
        if state == "reviewed" and not block.get("sources"):
            raise ValueError(f"{material}: reviewed parameters require primary sources")
        for param in params:
            if (
                not str(param.get("parameter_id", "")).strip()
                or param.get("value_kind")
                not in {
                    "typical",
                    "minimum",
                    "maximum",
                    "range",
                    "limit",
                    "qualitative",
                }
                or not str(param.get("label", "")).strip()
                or not str(param.get("value", "")).strip()
            ):
                raise ValueError(
                    f"{material}: every parameter requires parameter_id, value_kind, label and value"
                )
        if state == "reviewed":
            if any(not str(param.get("basis", "")).strip() for param in params):
                raise ValueError(
                    f"{material}: reviewed parameters require a source-conditioned basis"
                )
            required_context = ("grade", "test_method", "conditions", "source_ref")
            if any(
                not all(str(param.get(field, "")).strip() for field in required_context)
                for param in params
            ):
                raise ValueError(
                    f"{material}: reviewed parameters require grade, test_method, conditions and source_ref"
                )
    return blocks


@lru_cache(maxsize=1)
def _load() -> dict:
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    return _validated_blocks(data)


def lookup(material: str) -> dict | None:
    """The structured parameter block for one material (case-insensitive), or None when not in the store."""
    if not material:
        return None
    for k, v in _load().items():
        if k.lower() == material.lower():
            return {"material": k, **v}
    return None


@lru_cache(maxsize=1)
def _vocab() -> tuple[str, ...]:
    # longest-first so a compound family name wins over a substring (e.g. Glasfaser-PTFE over PTFE)
    return tuple(sorted(_load().keys(), key=len, reverse=True))


def material_parameters_for(text: str) -> list[dict]:
    """The grounded parameter blocks for the materials NAMED in ``text`` (word-boundary, longest-first,
    deduped). Empty when none match / the store has no entry. The render decides table-vs-not. Pure."""
    low = (text or "").lower()
    matches: list[tuple[int, int, dict]] = []
    seen: set[str] = set()
    for order, m in enumerate(_vocab()):
        ml = m.lower()
        if ml in seen:
            continue
        match = re.search(rf"\b{re.escape(ml)}\b", low)
        if match:
            blk = lookup(m)
            if blk:
                matches.append((match.start(), order, blk))
                seen.add(ml)
    return [block for _position, _order, block in sorted(matches)]


def parameter_text(blocks: list[dict] | None) -> str:
    """Complete, deterministic text surface allowed to contribute numeric answer content."""
    parts: list[str] = []
    for block in blocks or ():
        parts.extend(str(source) for source in block.get("sources", ()))
        for param in block.get("params", ()):
            parts.extend(
                str(param.get(field, ""))
                for field in (
                    "label",
                    "value",
                    "basis",
                    "grade",
                    "test_method",
                    "conditions",
                    "source_ref",
                )
            )
    return " ".join(part for part in parts if part)


def comparison_matrix(blocks: list[dict]) -> tuple[tuple[str, ...], list[dict]] | None:
    """Compile aligned material rows without asking the model to join or invent values."""
    if not blocks:
        return None
    subjects = tuple(str(block["material"]) for block in blocks)
    labels: dict[str, str] = {}
    values: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for block in blocks:
        subject = str(block["material"])
        for param in block.get("params", ()):
            parameter_id = str(param["parameter_id"])
            if parameter_id not in values:
                order.append(parameter_id)
                values[parameter_id] = {}
            labels.setdefault(parameter_id, str(param["label"]))
            context = "; ".join(
                part
                for part in (
                    str(param.get("grade", "")).strip(),
                    str(param.get("test_method", "")).strip(),
                    str(param.get("conditions", "")).strip(),
                )
                if part
            )
            values[parameter_id][subject] = (
                f"{param['value']} ({context})" if context else str(param["value"])
            )
    return subjects, [
        {
            "parameter_id": parameter_id,
            "label": labels[parameter_id],
            "values": values[parameter_id],
        }
        for parameter_id in order
    ]
