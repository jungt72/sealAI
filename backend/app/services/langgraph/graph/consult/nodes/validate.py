# backend/app/services/langgraph/graph/consult/nodes/validate.py
from __future__ import annotations
from typing import Any, Dict


def _to_float(x: Any) -> Any:
    try:
        if isinstance(x, bool):
            return x
        return float(x)
    except Exception:
        return x


def validate_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Leichter Parameter-Check/Normalisierung vor RAG.
    WICHTIG: Keine Berechnungen, kein Calculator-Aufruf – das macht calc_agent.
    """
    params = dict(state.get("params") or {})

    # numerische Felder best-effort in float wandeln
    for k in (
        "temp_max_c", "temp_min_c", "druck_bar", "drehzahl_u_min",
        "wellen_mm", "gehause_mm", "breite_mm",
        "relativgeschwindigkeit_ms",
        "tmax_c", "pressure_bar", "n_u_min", "rpm", "v_ms",
    ):
        if k in params and params[k] not in (None, "", []):
            params[k] = _to_float(params[k])

    # einfache Alias-Harmonisierung (falls Ziel noch leer)
    alias = {
        "tmax_c": "temp_max_c",
        "pressure_bar": "druck_bar",
        "n_u_min": "drehzahl_u_min",
        "rpm": "drehzahl_u_min",
        "v_ms": "relativgeschwindigkeit_ms",
    }
    for src, dst in alias.items():
        if (params.get(dst) in (None, "", [])) and (params.get(src) not in (None, "", [])):
            params[dst] = params[src]

    return {**state, "params": params, "phase": "validate"}
