"""Shared prompt block renderers backed by central Jinja templates."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.langgraph_v2.utils.jinja import render_template


def as_prompt_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dict(dumped)
    return {}


def render_challenger_gate(
    *,
    tile: Any | None = None,
    conditions: Iterable[str] | None = None,
    metrics: Iterable[Dict[str, Any]] | None = None,
) -> str:
    tile_dict = as_prompt_dict(tile)
    metric_rows: List[Dict[str, Any]] = []
    for metric in metrics or []:
        if not isinstance(metric, dict):
            continue
        value = metric.get("value")
        if value is None:
            continue
        metric_rows.append({"key": metric.get("key"), "value": value})

    return render_template(
        "challenger_gate.j2",
        {
            "status": tile_dict.get("status"),
            "chem_warning": bool(tile_dict.get("chem_warning")),
            "chem_message": tile_dict.get("chem_message"),
            "pv_value_mpa_m_s": tile_dict.get("pv_value_mpa_m_s"),
            "v_surface_m_s": tile_dict.get("v_surface_m_s"),
            "requires_backup_ring": bool(tile_dict.get("requires_backup_ring")),
            "extrusion_risk": bool(tile_dict.get("extrusion_risk")),
            "hrc_warning": bool(tile_dict.get("hrc_warning")),
            "shrinkage_risk": bool(tile_dict.get("shrinkage_risk")),
            "conditions": [str(item).strip() for item in (conditions or []) if str(item).strip()],
            "metrics": metric_rows,
        },
    ).strip()


__all__ = ["as_prompt_dict", "render_challenger_gate"]
