"use client";

import { useMemo } from "react";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { 
  EngineeringCockpitView, 
  EngineeringPath, 
  EngineeringProperty, 
  EngineeringSection, 
  PATH_RULES,
  DataOrigin
} from "@/lib/engineering/cockpitModel";

export type CockpitData = {
  view: EngineeringCockpitView;
  parameters: Record<string, any>;
  coverage: number;
  releaseStatus: string;
};

const SECTIONS_CONFIG = [
  {
    id: "core",
    title: "A. Grunddaten",
    fields: [
      { key: "medium", label: "Medium / Fluid", unit: "" },
      { key: "temperature_c", label: "Temperatur", unit: "°C" },
      { key: "pressure_bar", label: "Druck", unit: "bar" },
      { key: "shaft_diameter_mm", label: "Referenz-Ø", unit: "mm" },
      { key: "speed_rpm", label: "Drehzahl", unit: "rpm" },
      { key: "motion_type", label: "Bewegungsart", unit: "" },
      { key: "installation", label: "Equipment-Typ", unit: "" },
      { key: "pressure_direction", label: "Druckrichtung", unit: "" },
    ]
  },
  {
    id: "failure",
    title: "B. Technische Risikofaktoren",
    fields: [
      { key: "viscosity", label: "Viskosität", unit: "cSt" },
      { key: "solids_percent", label: "Feststoffe", unit: "%" },
      { key: "ph", label: "pH-Wert", unit: "" },
      { key: "dry_run_possible", label: "Trockenlauf mögl.", unit: "" },
      { key: "cleaning_cycles", label: "Reinigungszyklen", unit: "" },
    ]
  },
  {
    id: "geometry",
    title: "C. Geometrie & Einbauraum",
    fields: [
      { key: "geometry_context", label: "Bauraum", unit: "" },
      { key: "shaft_material", label: "Wellenwerkstoff", unit: "" },
      { key: "shaft_hardness", label: "Wellenhärte", unit: "HRC" },
      { key: "runout_mm", label: "Rundlauf", unit: "mm" },
      { key: "vibration_rms", label: "Vibration RMS", unit: "mm/s" },
    ]
  },
  {
    id: "rfq",
    title: "D. Anfrage- & Freigabereife",
    fields: [
      { key: "allowable_leakage", label: "Zul. Leckage", unit: "" },
      { key: "life_hours", label: "Lebensdauer", unit: "h" },
      { key: "compliance", label: "Konformität", unit: "" },
    ]
  }
];

function projectEngineeringView(
  parameters: Record<string, any>,
  assertions: Record<string, any> | null,
  workspace: any
): EngineeringCockpitView {
  // 1. Path Detection
  const motion = parameters.motion_type || "unclear";
  const equipment = parameters.installation || "unclear";
  
  let path: EngineeringPath = "standard";
  if (motion === "rotary" && equipment === "pump") path = "mechanical_seal_pump";
  else if (motion === "rotary" && (equipment === "gearbox" || equipment === "rotary_general")) path = "radial_shaft_seal";
  else if (motion === "static") path = "static_seal";
  else if (motion === "rotary") path = "unclear_rotary";

  const rules = PATH_RULES[path];

  // 2. Section Projection
  const sections: Record<string, EngineeringSection> = {};

  SECTIONS_CONFIG.forEach(secConfig => {
    const properties: EngineeringProperty[] = secConfig.fields.map(f => {
      const assertion = assertions?.[f.key];
      const rawVal = parameters[f.key] || assertion?.value || null;
      
      let origin: DataOrigin = "missing";
      let isConfirmed = false;

      if (rawVal !== null) {
        if (assertion?.confidence === "user_override" || assertion?.confidence === "confirmed") {
          origin = "user";
          isConfirmed = true;
        } else {
          origin = "inferred";
          isConfirmed = false;
        }
      }

      // Medium Registry check for medium field
      if (f.key === "medium" && workspace?.mediumClassification?.status === "available") {
        origin = "medium_registry";
      }

      return {
        key: f.key,
        label: f.label,
        value: rawVal,
        unit: f.unit,
        origin,
        isConfirmed,
        isMandatory: rules.mandatory.includes(f.key),
        isHidden: rules.hidden.includes(f.key),
        riskFlags: [] // Placeholder for future logic
      };
    });

    const visibleProps = properties.filter(p => !p.isHidden);
    const mandatoryVisible = visibleProps.filter(p => p.isMandatory);
    const filledMandatory = mandatoryVisible.filter(p => p.value !== null);
    
    // Honest completeness: 
    // If mandatory fields exist, percentage reflects them.
    // If no mandatory fields exist, it's 100% only if all visible optional fields are filled, else 0.5 (or similar)
    // Actually, let's stick to mandatory, but if 0 mandatory, show 1 only if at least one optional is filled.
    let completeness = 0;
    if (mandatoryVisible.length > 0) {
      completeness = filledMandatory.length / mandatoryVisible.length;
    } else {
      const filledOptional = visibleProps.filter(p => p.value !== null).length;
      completeness = visibleProps.length > 0 && filledOptional === visibleProps.length ? 1 : (filledOptional > 0 ? 0.5 : 0);
    }
    
    sections[secConfig.id] = {
      id: secConfig.id,
      title: secConfig.title,
      properties,
      completeness
    };
  });

  // 3. Readiness Calculation
  const allProps = Object.values(sections).flatMap(s => s.properties);
  const missingMandatoryKeys = allProps
    .filter(p => p.isMandatory && p.value === null && !p.isHidden)
    .map(p => p.key);

  const isRfqReady = workspace?.rfq?.rfq_ready || (missingMandatoryKeys.length === 0 && (workspace?.completeness?.coverageScore || 0) > 0.6);

  const readiness: EngineeringCockpitView["readiness"] = {
    isRfqReady,
    missingMandatoryKeys,
    blockers: workspace?.rfq?.blockers || [],
    status: isRfqReady ? "rfq_ready" : (missingMandatoryKeys.length > 0 ? "preliminary" : "review_needed")
  };

  return {
    path,
    sections,
    readiness,
    mediumContext: {
      canonicalName: workspace?.mediumClassification?.canonicalLabel || null,
      isConfirmed: workspace?.mediumClassification?.confidence === "high",
      properties: workspace?.mediumContext?.properties || [],
      riskFlags: workspace?.mediumContext?.challenges || []
    }
  };
}

export function useCockpitData(): CockpitData | null {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const streamWorkspace = useWorkspaceStore((s) => s.streamWorkspace);
  const streamAssertions = useWorkspaceStore((s) => s.streamAssertions);

  return useMemo(() => {
    let rawParams: Record<string, any> = {};
    let assertions = streamAssertions;
    let wsObj = workspace;

    if (workspace) {
      rawParams = workspace.parameters || {};
    } else if (streamWorkspace) {
      const params: Record<string, any> = {};
      const streamParams = streamWorkspace.ui.parameter.parameters || [];
      for (const p of streamParams) {
        if (p.field_name) {
          params[p.field_name.toLowerCase().replace(/\s+/g, "_")] = p.value;
        }
      }
      rawParams = params;
      // We don't assign streamWorkspace to wsObj if it's strictly typed to WorkspaceView
      // Instead we pass it as any to the projector which handles it safely
      wsObj = streamWorkspace as any; 
    } else {
      return null;
    }

    const view = projectEngineeringView(rawParams, assertions, wsObj);

    return {
      view,
      parameters: rawParams,
      coverage: workspace?.completeness?.coverageScore || 0,
      releaseStatus: workspace?.governance.releaseStatus || "inadmissible",
    };
  }, [workspace, streamWorkspace, streamAssertions]);
}
