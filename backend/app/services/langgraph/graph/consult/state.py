# backend/app/services/langgraph/graph/consult/state.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import Annotated
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


# ---- Parameter- & Derived-Typen -------------------------------------------------
class Parameters(TypedDict, total=False):
    # Kernparameter
    temp_max_c: float
    druck_bar: float
    drehzahl_u_min: float
    wellen_mm: float
    relativgeschwindigkeit_ms: float  # alias für geschwindigkeit_m_s
    geschwindigkeit_m_s: float
    # Hydraulik
    stange_mm: float
    nut_d_mm: float
    nut_b_mm: float
    # Aliasse / Harmonisierung
    tmax_c: float
    pressure_bar: float
    n_u_min: float
    rpm: float
    v_ms: float
    # optionale Filter/Routing
    material: str
    profile: str
    domain: str
    norm: str
    lang: str
    # optionale physikalische Parameter (falls bekannt; sonst werden optionale Berechnungen übersprungen)
    mu: float                     # Reibkoeffizient
    contact_pressure_mpa: float   # Kontaktpressung an der Dichtkante
    axial_force_n: float          # Axialkraft (Hydraulik)
    width_mm: float               # wirksame Dichtbreite (für Reib-/Leistungsabschätzung)


class Derived(TypedDict, total=False):
    # Allgemeine berechnete Größen
    surface_speed_m_s: float              # v
    umfangsgeschwindigkeit_m_s: float     # v (de)
    omega_rad_s: float                    # ω
    p_bar: float                          # Druck [bar]
    p_pa: float                           # Druck [Pa]
    p_mpa: float                          # Druck [MPa]
    pv_bar_ms: float                      # PV in bar·m/s
    pv_mpa_ms: float                      # PV in MPa·m/s
    # Optional – nur wenn genug Parameter vorliegen
    friction_force_n: float               # F_f = μ * N (wenn N/Kontaktpressung bekannt)
    friction_power_w: float               # P = F_f * v
    # Vorhandene Felder bleiben erhalten
    relativgeschwindigkeit_ms: float
    calculated: Dict[str, Any]
    flags: Dict[str, Any]
    warnings: List[str]
    requirements: List[str]


# ---- Graph-State ----------------------------------------------------------------
class ConsultState(TypedDict, total=False):
    # Dialog
    messages: Annotated[List[AnyMessage], add_messages]
    query: str

    # Parameter
    params: Parameters
    derived: Derived

    # Routing / Kontext
    user_id: Optional[str]
    tenant: Optional[str]
    domain: Optional[str]
    phase: Optional[str]
    consult_required: Optional[bool]

    # ---- UI/Frontend-Integration ----
    ui_event: Dict[str, Any]
    missing_fields: List[str]

    # --- RAG-Ergebnis ---
    retrieved_docs: List[Dict[str, Any]]
    context: str

    # Empfehlungen / Ergebnis
    empfehlungen: List[Dict[str, Any]]

    # Qualitäts-/Validierungsinfos
    validation: Dict[str, Any]
    confidence: float
    needs_more_params: bool

    # --- Legacy-Felder ---
    docs: List[Dict[str, Any]]
    citations: List[str]
    answer: Optional[str]
