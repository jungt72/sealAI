"use client";

import { useMemo } from "react";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { 
  EngineeringCockpitView, 
  EngineeringPath, 
  EngineeringProperty, 
  EngineeringSection, 
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

const SECTIONS_CONFIG: Array<{
  id: EngineeringSection["id"];
  title: string;
  fields: Array<{ key: string; label: string; unit: string }>;
}> = [
  {
    id: "application_function",
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
    id: "medium_environment",
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
    id: "operating_geometry",
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
    id: "risk_readiness",
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
  const path = engineeringPath;

  const sections = {} as EngineeringCockpitView["sections"];

  SECTIONS_CONFIG.forEach(secConfig => {
    const properties: EngineeringProperty[] = secConfig.fields.flatMap((f) => {
      const assertion = assertions?.[f.key];
      const rawVal = parameters[f.key] || assertion?.value || null;
      
      let origin: DataOrigin = "missing";
      let isConfirmed = false;

      if (rawVal !== null) {
        if (assertion?.confidence === "user_override" || assertion?.confidence === "confirmed") {
          origin = "backend_placeholder";
        } else {
          origin = "pending_backend_confirmation";
        }
      }

      // Medium Registry check for medium field
      if (f.key === "medium" && workspace?.mediumClassification?.status === "available") {
        origin = "medium_registry";
      }

      const isMandatory = false;

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
      : 0;
    
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

  const backendRfqReady = workspace?.rfq?.rfq_ready === true;
  const missingMandatoryKeys: string[] = [];

  const readiness: EngineeringCockpitView["readiness"] = {
    isRfqReady: backendRfqReady,
    missingMandatoryKeys,
    blockers: backendRfqReady ? [] : ["backend_cockpit_pending"],
    status: backendRfqReady ? "rfq_ready" : "review_needed",
    releaseStatus: backendRfqReady ? "rfq_ready" : "backend_cockpit_pending",
    coverageScore: 0,
  };

  return {
    path,
    requestType: requestType || "nicht bestimmt",
    sections,
    checks: [],
    riskEvaluations: [],
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
      routing: {
        authority: "frontend_placeholder",
        note: "Backend cockpit truth is not available yet.",
      },
    },
  };
}

export function useCockpitData(): CockpitData | null {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const streamWorkspace = useWorkspaceStore((s) => s.streamWorkspace);
  const streamAssertions = useWorkspaceStore((s) => s.streamAssertions);
  const userParameterOverrides = useWorkspaceStore((s) => s.userParameterOverrides);

  return useMemo(() => {
    let rawParams: Record<string, any> = {};
    let assertions = streamAssertions;
    let wsObj = workspace;
    let mediumStatus: MediumStatusViewModel | null = null;
    let requestType: string | null = null;
    let engineeringPath: EngineeringPath | null = null;

    if (workspace) {
      rawParams = { ...(workspace.parameters || {}), ...userParameterOverrides };
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
      rawParams = { ...params, ...userParameterOverrides };
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
  }, [workspace, streamWorkspace, streamAssertions, userParameterOverrides]);
}
