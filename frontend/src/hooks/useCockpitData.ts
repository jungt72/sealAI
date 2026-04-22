"use client";

import { useMemo } from "react";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { 
  EngineeringCockpitView, 
  EngineeringPath, 
  EngineeringProperty, 
  EngineeringSection, 
  DEFAULT_PATH_RULES,
  PATH_RULES,
  DataOrigin
} from "@/lib/engineering/cockpitModel";
import { 
  MediumStatusViewModel, 
  buildMediumStatusViewFromWorkspace, 
  buildMediumStatusViewFromStream 
} from "@/lib/mediumStatusView";

export type CockpitData = {
  view: EngineeringCockpitView;
  parameters: Record<string, any>;
  coverage: number;
  releaseStatus: string;
  mediumStatus: MediumStatusViewModel;
};

function isEngineeringPath(value: string | null | undefined): value is EngineeringPath {
  return (
    value === "ms_pump" ||
    value === "rwdr" ||
    value === "static" ||
    value === "labyrinth" ||
    value === "hyd_pneu" ||
    value === "unclear_rotary"
  );
}

function deriveFallbackEngineeringPath(parameters: Record<string, any>): EngineeringPath | null {
  const motion = String(parameters.motion_type || "").toLowerCase();
  const equipment = [
    parameters.installation,
    parameters.application_context,
    parameters.sealing_type,
    parameters.geometry_context,
  ]
    .filter((value) => value !== null && value !== undefined && value !== "")
    .map(String)
    .join(" ")
    .toLowerCase();

  if (equipment.includes("labyrinth")) return "labyrinth";
  if (motion === "static") return "static";

  const hasRwdrMarker =
    equipment.includes("ptfe-rwdr") ||
    equipment.includes("ptfe rwdr") ||
    equipment.includes("rwdr") ||
    equipment.includes("wellendichtring") ||
    equipment.includes("radialwellendichtring") ||
    equipment.includes("simmerring") ||
    equipment.includes("lip seal");
  if (hasRwdrMarker || (motion === "rotary" && equipment.includes("gearbox"))) {
    return "rwdr";
  }

  if (motion === "rotary" && (equipment.includes("pump") || equipment.includes("gleitring"))) return "ms_pump";

  if (
    equipment.includes("hydraul") ||
    equipment.includes("pneumat") ||
    equipment.includes("cylinder") ||
    equipment.includes("zylinder") ||
    equipment.includes("kolbenstange") ||
    equipment.includes("rod")
  ) {
    return "hyd_pneu";
  }
  if (motion === "rotary") return "unclear_rotary";
  return null;
}

const SECTIONS_CONFIG: Array<{
  id: EngineeringSection["id"];
  title: string;
  fields: Array<{ key: string; label: string; unit: string }>;
}> = [
  {
    id: "core_intake",
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
    id: "failure_drivers",
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
    id: "geometry_fit",
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
    id: "rfq_liability",
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
  workspace: any,
  requestType: string | null = null,
  engineeringPath: EngineeringPath | null = null
): EngineeringCockpitView {
  const path = engineeringPath ?? deriveFallbackEngineeringPath(parameters);
  const rules = path ? PATH_RULES[path] : DEFAULT_PATH_RULES;

  const sections = {} as EngineeringCockpitView["sections"];

  SECTIONS_CONFIG.forEach(secConfig => {
    const properties: EngineeringProperty[] = secConfig.fields.flatMap((f) => {
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

      const isMandatory = rules.mandatory.includes(f.key);
      const isHidden = rules.hidden.includes(f.key);
      if (isHidden) {
        return [];
      }

      return [{
        key: f.key,
        label: f.label,
        value: rawVal,
        unit: f.unit,
        origin,
        confidence: assertion?.confidence || null,
        isConfirmed,
        isMandatory,
      }];
    });

    const mandatoryVisible = properties.filter(p => p.isMandatory);
    const filledMandatory = mandatoryVisible.filter(p => p.value !== null);
    
    const percent = mandatoryVisible.length > 0
      ? Math.round((filledMandatory.length / mandatoryVisible.length) * 100)
      : 100;
    
    sections[secConfig.id] = {
      id: secConfig.id,
      title: secConfig.title,
      properties,
      completion: {
        mandatoryPresent: filledMandatory.length,
        mandatoryTotal: mandatoryVisible.length,
        percent,
      },
    };
  });

  const allProps = Object.values(sections).flatMap(s => s.properties);
  const missingMandatoryKeys = allProps
    .filter(p => p.isMandatory && p.value === null)
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
    requestType: requestType || "nicht bestimmt",
    sections,
    checks: [],
    readiness,
    mediumContext: {
      canonicalName: workspace?.mediumClassification?.canonicalLabel || null,
      isConfirmed: workspace?.mediumClassification?.confidence === "high",
      properties: workspace?.mediumContext?.properties || [],
      riskFlags: workspace?.mediumContext?.challenges || []
    },
    routingMetadata: {
      phase: workspace?.communication?.conversationPhase || null,
      lastNode: null,
      routing: {},
    },
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
    let mediumStatus: MediumStatusViewModel | null = null;
    let requestType: string | null = null;
    let engineeringPath: EngineeringPath | null = null;

    if (workspace) {
      rawParams = workspace.parameters || {};
      mediumStatus = buildMediumStatusViewFromWorkspace(workspace);
      requestType = workspace.requestType || null;
      engineeringPath = isEngineeringPath(workspace.engineeringPath) ? workspace.engineeringPath : null;
    } else if (streamWorkspace) {
      const params: Record<string, any> = {};
      const streamParams = streamWorkspace.ui.parameter.parameters || [];
      for (const p of streamParams) {
        if (p.field_name) {
          params[p.field_name.toLowerCase().replace(/\s+/g, "_")] = p.value;
        }
      }
      rawParams = params;
      wsObj = streamWorkspace as any; 
      mediumStatus = buildMediumStatusViewFromStream(streamWorkspace);
    } else {
      return null;
    }

    if (!mediumStatus) return null;

    if (workspace?.cockpit) {
      return {
        view: workspace.cockpit,
        parameters: rawParams,
        coverage: workspace?.completeness?.coverageScore || 0,
        releaseStatus: workspace?.governance.releaseStatus || "inadmissible",
        mediumStatus,
      };
    }

    const view = projectEngineeringView(rawParams, assertions, wsObj, requestType, engineeringPath);

    return {
      view,
      parameters: rawParams,
      coverage: workspace?.completeness?.coverageScore || 0,
      releaseStatus: workspace?.governance.releaseStatus || "inadmissible",
      mediumStatus
    };
  }, [workspace, streamWorkspace, streamAssertions]);
}
