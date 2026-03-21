import json
from langchain_core.tools import tool
from app.agent.evidence.models import Claim, ClaimType
from typing import List, Optional

@tool("submit_claim")
def submit_claim(
    claim_type: ClaimType,
    statement: str,
    confidence: float,
    source_fact_ids: List[str] = []
) -> str:
    """
    Übergibt eine strukturierte fachliche Erkenntnis (Claim) an den SealingAIState.
    Dies ist der einzige Weg für das LLM, den technischen Zustand des Systems zu beeinflussen.
    Validiert die Eingaben gegen das Engineering-Modell (Strict Tooling).
    """
    # Instanziierung löst Pydantic-Validierung aus
    claim = Claim(
        claim_type=claim_type,
        statement=statement,
        confidence=confidence,
        source_fact_ids=source_fact_ids
    )
    
    # Bestätigung an das LLM (Phase C3 Meilenstein)
    return f"Claim empfangen: [{claim.claim_type.value}] {claim.statement} (Confidence: {claim.confidence})"


@tool("calculate_rwdr_specifications")
def calculate_rwdr_specifications(
    shaft_diameter_mm: float,
    rpm: float,
    pressure_bar: Optional[float] = None,
    temperature_max_c: Optional[float] = None,
    temperature_min_c: Optional[float] = None,
    surface_hardness_hrc: Optional[float] = None,
    runout_mm: Optional[float] = None,
    clearance_gap_mm: Optional[float] = None,
    elastomer_material: Optional[str] = None,
    medium: Optional[str] = None,
    lubrication_mode: Optional[str] = None,
    cross_section_d2_mm: Optional[float] = None,
    groove_depth_mm: Optional[float] = None,
    groove_width_mm: Optional[float] = None,
    seal_inner_diameter_mm: Optional[float] = None,
) -> str:
    """
    Berechnet deterministisch die technischen Kennzahlen für einen Radialwellendichtring (RWDR/Simmerring).
    Verwende dieses Tool IMMER wenn der Nutzer konkrete Maße oder Betriebsparameter für einen RWDR nennt
    und eine Auslegungsbeurteilung, Geschwindigkeitsprüfung, Materialeignung oder Dimensionierung benötigt.

    WANN verwenden:
    - Nutzer nennt Wellendurchmesser + Drehzahl (→ Umfangsgeschwindigkeit nach DIN 3760)
    - Nutzer fragt nach PV-Wert, Reibungsleistung oder Materialeignung für RWDR
    - Nutzer nennt Druckbeaufschlagung und möchte Extrusionsrisiko wissen
    - Nutzer nennt Nutenmaße (d2, Nuttiefe, Nutbreite) für Kompressionsgrad oder Füllfaktor
    - Nutzer nennt Temperaturbereich für Wärmeausdehnung oder Schrumpfungsrisiko
    - Nutzer fragt nach Oberflächenhärte (HRC) Anforderungen für eine Welle

    PARAMETER (alle Längen in mm, Drehzahl in rpm, Druck in bar, Temperatur in °C):
    - shaft_diameter_mm: Wellendurchmesser d1 [mm] — PFLICHT
    - rpm: Drehzahl n [1/min] — PFLICHT
    - pressure_bar: Systemdruck [bar] — optional, für PV-Wert und Extrusionsrisiko
    - temperature_max_c: maximale Betriebstemperatur [°C] — optional
    - temperature_min_c: minimale Betriebstemperatur [°C] — optional, für Schrumpfungsrisiko
    - surface_hardness_hrc: Wellenoberfläche Härte [HRC] — optional, Empfehlung ≥ 55 HRC
    - runout_mm: Wellentaumel / Rundlaufabweichung [mm] — optional
    - clearance_gap_mm: Spaltmaß am Dichtspalt [mm] — optional, für Extrusionsrisiko
    - elastomer_material: Elastomerwerkstoff (z.B. "FKM", "NBR", "PTFE", "EPDM", "HNBR") — optional
    - medium: Abdichtmedium (z.B. "Hydrauliköl", "Wasser") — optional
    - lubrication_mode: Schmierungszustand ("dry" = trocken, "" = geschmiert) — optional
    - cross_section_d2_mm: Schnurdicke d2 des Dichtelements [mm] — optional (Nutgeometrie)
    - groove_depth_mm: Nuttiefe [mm] — optional (Kompressionsgrad)
    - groove_width_mm: Nutbreite [mm] — optional (Füllfaktor)
    - seal_inner_diameter_mm: Innen-Ø des Dichtrings (Schnurring) [mm] — optional (Vordehnung)

    RÜCKGABE: JSON-String mit:
    - v_surface_m_s: Umfangsgeschwindigkeit [m/s] (DIN 3760)
    - pv_value_mpa_m_s: PV-Wert [MPa·m/s]
    - friction_power_watts: Reibungsleistung [W]
    - status: "ok" | "warning" | "critical" | "insufficient_data"
    - notes: Liste der Warnhinweise und Grenzwertverletzungen
    - hrc_warning, pv_warning, runout_warning, dry_running_risk: bool
    - extrusion_risk, requires_backup_ring: bool
    - geometry_warning, shrinkage_risk: bool
    - compression_ratio_pct, groove_fill_pct, stretch_pct: float | null
    - thermal_expansion_mm: float | null
    """
    from app.agent.domain.rwdr_calc import RwdrCalcInput, calculate_rwdr

    inp = RwdrCalcInput(
        shaft_diameter_mm=shaft_diameter_mm,
        rpm=rpm,
        pressure_bar=pressure_bar,
        temperature_max_c=temperature_max_c,
        temperature_min_c=temperature_min_c,
        surface_hardness_hrc=surface_hardness_hrc,
        runout_mm=runout_mm,
        clearance_gap_mm=clearance_gap_mm,
        elastomer_material=elastomer_material,
        medium=medium,
        lubrication_mode=lubrication_mode,
        cross_section_d2_mm=cross_section_d2_mm,
        groove_depth_mm=groove_depth_mm,
        groove_width_mm=groove_width_mm,
        seal_inner_diameter_mm=seal_inner_diameter_mm,
    )
    result = calculate_rwdr(inp)
    return json.dumps({
        "v_surface_m_s": result.v_surface_m_s,
        "pv_value_mpa_m_s": result.pv_value_mpa_m_s,
        "friction_power_watts": result.friction_power_watts,
        "hrc_warning": result.hrc_warning,
        "runout_warning": result.runout_warning,
        "pv_warning": result.pv_warning,
        "dry_running_risk": result.dry_running_risk,
        "extrusion_risk": result.extrusion_risk,
        "requires_backup_ring": result.requires_backup_ring,
        "compression_ratio_pct": result.compression_ratio_pct,
        "groove_fill_pct": result.groove_fill_pct,
        "stretch_pct": result.stretch_pct,
        "geometry_warning": result.geometry_warning,
        "thermal_expansion_mm": result.thermal_expansion_mm,
        "shrinkage_risk": result.shrinkage_risk,
        "status": result.status,
        "notes": result.notes,
    }, ensure_ascii=False)
