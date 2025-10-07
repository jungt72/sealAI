# backend/app/langgraph/graph_chat.py
from __future__ import annotations

import asyncio
import math
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple


# =========================
# Utility: domain knowledge
# =========================

RWDR_FIELDS_REQUIRED = [
    "wellen_mm",        # Welle
    "gehause_mm",       # Gehäuse
    "breite_mm",        # Breite
    "medium",           # Medium
    "temp_max_c",       # Tmax
    "druck_bar",        # Druck
    "drehzahl_u_min",   # Drehzahl
]

HYD_STANGE_FIELDS_REQUIRED = [
    "stange_mm",
    "nut_d_mm",
    "nut_b_mm",
    "geschwindigkeit_m_s",
    "druck_bar",
    "temp_max_c",
]

def _as_num(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return None

def _trim(s: Any) -> str:
    return (str(s or "")).strip()

def _split_tokens(t: str, chunk_size: int = 24) -> List[str]:
    """
    Teilt Text in halbwegs natürliche Tokens für Streaming.
    - bevorzugt nach Leerzeichen
    - fällt zurück auf feste Breite
    """
    t = t.replace("\r", "")
    words = t.split(" ")
    out: List[str] = []
    buf: List[str] = []
    cur = 0
    for w in words:
        if cur + len(w) + (1 if buf else 0) > chunk_size:
            out.append(" ".join(buf))
            buf = [w]
            cur = len(w)
        else:
            buf.append(w)
            cur += len(w) + (1 if buf else 0)
    if buf:
        out.append(" ".join(buf))
    return [x for x in out if x]


# =========================
# Derived/calculated values
# =========================

def _derive_calc(params: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Leitet aus eingegebenen Parametern sinnvolle Größen ab, z. B.:
    - Umfangsgeschwindigkeit v (m/s)
    - Winkelgeschwindigkeit ω (rad/s)
    - PV-Wert (bar·m/s bzw. MPa·m/s)
    Liefert (calculated, warnings)
    """
    calc: Dict[str, Any] = {}
    warnings: List[str] = []

    d_mm = _as_num(params.get("wellen_mm")) or _as_num(params.get("stange_mm"))
    n_rpm = _as_num(params.get("drehzahl_u_min"))
    v_ms = _as_num(params.get("geschwindigkeit_m_s"))
    p_bar = _as_num(params.get("druck_bar"))

    # Umfangsgeschwindigkeit v aus d & n, falls v nicht direkt gegeben
    if v_ms is None and d_mm is not None and n_rpm is not None:
        # v = π * d[m] * n[1/s]
        v_ms = math.pi * (d_mm / 1000.0) * (n_rpm / 60.0)
        calc["surface_speed_m_s"] = v_ms
    elif v_ms is not None:
        calc["surface_speed_m_s"] = v_ms

    # ω (rad/s) aus n
    if n_rpm is not None:
        calc["omega_rad_s"] = 2.0 * math.pi * (n_rpm / 60.0)

    # PV
    if p_bar is not None and v_ms is not None:
        calc["pv_bar_ms"] = p_bar * v_ms
        calc["p_bar"] = p_bar
        # zusätzlich MPa-Variante
        calc["p_mpa"] = p_bar / 10.0
        calc["pv_mpa_ms"] = (p_bar / 10.0) * v_ms

    # leichte Plausibilitäten
    if v_ms is not None and v_ms > 20:
        warnings.append("Sehr hohe Gleitgeschwindigkeit – prüfen Sie die Materialauswahl.")
    if p_bar is not None and p_bar > 100:
        warnings.append("Außergewöhnlich hoher Druck – Dichtungsauswahl genau validieren.")

    return calc, warnings


# =========================
# Core consult logic
# =========================

def _detect_case(params: Dict[str, Any]) -> str:
    """
    erkennt den Anwendungsfall grob an 'falltyp'/'bauform'
    """
    falltyp = _trim(params.get("falltyp")).lower()
    bauform = _trim(params.get("bauform")).lower()
    if "stange" in falltyp or "hydraul" in falltyp or "stange" in bauform:
        return "hyd_stange"
    # default = RWDR
    return "rwdr"

def _missing_for_case(case: str, params: Dict[str, Any]) -> List[str]:
    req = RWDR_FIELDS_REQUIRED if case == "rwdr" else HYD_STANGE_FIELDS_REQUIRED
    missing = []
    for k in req:
        v = params.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(k)
    return missing

def _one_line_summary(params: Dict[str, Any]) -> str:
    parts = []
    if params.get("wellen_mm"): parts.append(f"Welle {params['wellen_mm']}")
    if params.get("gehause_mm"): parts.append(f"Gehäuse {params['gehause_mm']}")
    if params.get("breite_mm"): parts.append(f"Breite {params['breite_mm']}")
    if params.get("stange_mm"): parts.append(f"Stange {params['stange_mm']}")
    if params.get("nut_d_mm"): parts.append(f"Nut D {params['nut_d_mm']}")
    if params.get("nut_b_mm"): parts.append(f"Nut B {params['nut_b_mm']}")
    if params.get("geschwindigkeit_m_s") is not None: parts.append(f"v {params['geschwindigkeit_m_s']} m/s")
    if params.get("medium"): parts.append(f"Medium {params['medium']}")
    if params.get("temp_max_c") is not None: parts.append(f"Tmax {params['temp_max_c']}°C")
    if params.get("druck_bar") is not None: parts.append(f"Druck {params['druck_bar']} bar")
    if params.get("drehzahl_u_min") is not None: parts.append(f"n {params['drehzahl_u_min']} 1/min")
    return ", ".join(parts)

def _build_text_answer(user_text: str, params: Dict[str, Any]) -> str:
    """
    erzeugt eine klare, fachliche Antwort in DE.
    """
    case = _detect_case(params)
    calc, warnings = _derive_calc(params)
    summary = _one_line_summary(params)

    intro = ""
    if user_text:
        lt = user_text.strip().lower()
        if "hallo" in lt or "hello" in lt:
            intro = "Hallo! 👋 "

    lines = []
    if intro:
        lines.append(intro)

    if summary:
        lines.append(f"Zusammenfassung deiner Angaben: {summary}.")

    if "surface_speed_m_s" in calc:
        lines.append(f"Abgeleitete Umfangsgeschwindigkeit v ≈ **{calc['surface_speed_m_s']:.3f} m/s**.")
    if "omega_rad_s" in calc:
        lines.append(f"Winkelgeschwindigkeit ω ≈ **{calc['omega_rad_s']:.3f} rad/s**.")
    if "pv_bar_ms" in calc:
        lines.append(f"PV-Wert ≈ **{calc['pv_bar_ms']:.3f} bar·m/s** "
                     f"(= {calc['pv_mpa_ms']:.3f} MPa·m/s).")

    if case == "rwdr":
        lines.append("Für einen **Radialwellendichtring (RWDR)** bewerte ich Material und Bauform "
                     "in Abhängigkeit von Druck, Temperatur und Umfangsgeschwindigkeit.")
    else:
        lines.append("Für eine **Hydraulik-Stangendichtung** bewerte ich Profil und Werkstoff "
                     "in Abhängigkeit von Druck, Temperatur und Stangengeschwindigkeit.")

    if warnings:
        lines.append("")
        lines.append("**Hinweise:**")
        for w in warnings:
            lines.append(f"- {w}")

    lines.append("")
    lines.append("Wenn du willst, kann ich jetzt eine konkrete Dichtungsempfehlung ableiten oder "
                 "die Angaben verfeinern.")

    return "\n".join(lines).strip()


# =====================================
# Public API used by backend WS/REST
# =====================================

async def stream_consult(state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Async-Generator, der Events passend zu deinem Frontend liefert:
      start → token* → final → done
    und bei fehlenden Pflichtfeldern einen UI-Event `open_form` emittiert.
    """
    # Eingaben normalisieren
    user_text: str = _trim(state.get("input"))
    thread_id: str = _trim(state.get("chat_id") or state.get("thread_id") or "api:default")
    params: Dict[str, Any] = dict(state.get("params") or {})

    # Start-Event
    yield {"event": "start", "thread_id": f"{thread_id}", "route": "graph", "graph": "consult"}

    # Pflichtfelder prüfen (Case-abhängig)
    case = _detect_case(params)
    missing = _missing_for_case(case, params)

    if missing:
        # UI-Event: Formular öffnen & Prefill/Missing signalisieren
        yield {
            "event": "ui_action",
            "ui_action": "open_form",
            "prefill": params,
            "missing": missing,
            "form_id": "consult_form",
        }
        # Direkte (kurze) sprachliche Nachfrage – triggert Frontend-"open_form"-Heuristik auch aus Text
        ask = (
            "Mir fehlen noch folgende Angaben, bevor ich eine präzise Empfehlung geben kann: "
            f"**{', '.join(missing)}**. Kannst du mir diese bitte nennen (gern in einer Zeile)?"
        )
        for tok in _split_tokens(ask, 38):
            yield {"event": "token", "delta": tok + " "}
            await asyncio.sleep(0)  # kooperatives Scheduling
        yield {"event": "final", "text": ask}

        # Optional: abgeleitete Größen trotzdem anbieten, wenn schon möglich
        calc, warnings = _derive_calc(params)
        if calc or warnings:
            yield {
                "event": "ui_action",
                "ui_action": "calc_snapshot",
                "derived": {"calculated": calc, "warnings": warnings},
            }

        yield {"event": "done", "thread_id": f"{thread_id}"}
        return

    # Alles da → Antwort bauen
    text = _build_text_answer(user_text, params)

    # Abgeleitetes
    calc, warnings = _derive_calc(params)
    if calc or warnings:
        yield {
            "event": "ui_action",
            "ui_action": "calc_snapshot",
            "derived": {"calculated": calc, "warnings": warnings},
        }

    # Token-Stream
    for tok in _split_tokens(text, 46):
        yield {"event": "token", "delta": tok + " "}
        await asyncio.sleep(0)

    # Final
    yield {"event": "final", "text": text}
    yield {"event": "done", "thread_id": f"{thread_id}"}


def invoke_consult(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Synchrone Variante – erzeugt denselben Final-Text wie der Stream.
    Wird von /api/v1/ai/beratung genutzt.
    """
    user_text: str = _trim(state.get("input"))
    params: Dict[str, Any] = dict(state.get("params") or {})
    case = _detect_case(params)
    missing = _missing_for_case(case, params)

    if missing:
        ask = (
            "Mir fehlen noch folgende Angaben, bevor ich eine präzise Empfehlung geben kann: "
            f"**{', '.join(missing)}**. Kannst du mir diese bitte nennen (gern in einer Zeile)?"
        )
        return {
            "message": {"role": "assistant", "content": ask},
            "ui_action": {"ui_action": "open_form", "prefill": params, "missing": missing},
            "final": {"text": ask},
        }

    text = _build_text_answer(user_text, params)
    calc, warnings = _derive_calc(params)
    out: Dict[str, Any] = {
        "message": {"role": "assistant", "content": text},
        "final": {"text": text},
    }
    if calc or warnings:
        out["ui_action"] = {"ui_action": "calc_snapshot", "derived": {"calculated": calc, "warnings": warnings}}
    return out
