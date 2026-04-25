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
  fields: Array<{ key: string; label: string; unit: string; aliases?: string[] }>;
}> = [
  {
    id: "application_function",
    title: "1. Anlage & Funktion",
    fields: [
      { key: "asset_type", label: "Anlage / Baugruppe", unit: "", aliases: ["installation", "application_context"] },
      { key: "asset_function", label: "Funktion", unit: "", aliases: ["primary_function"] },
      { key: "seal_location", label: "Dichtstelle", unit: "", aliases: ["geometry_context"] },
      { key: "motion_type", label: "Bewegungsart", unit: "", aliases: ["movement_type"] },
      { key: "primary_function", label: "Dichtfunktion", unit: "", aliases: ["pressure_direction"] },
      { key: "consequence_of_failure", label: "Ausfallfolge", unit: "", aliases: ["allowable_leakage"] },
    ]
  },
  {
    id: "medium_environment",
    title: "2. Medium & Umgebung",
    fields: [
      { key: "medium_name", label: "Medium", unit: "", aliases: ["medium"] },
      { key: "medium_category", label: "Medienkategorie", unit: "", aliases: ["medium_family"] },
      { key: "temperature_max", label: "Temperatur max.", unit: "°C", aliases: ["temperature_c"] },
      { key: "particles_present", label: "Partikel", unit: "", aliases: ["solids_percent", "contamination"] },
      { key: "cleaning_media", label: "Reinigung / CIP", unit: "", aliases: ["cleaning_cycles"] },
      { key: "food_contact", label: "Food/Pharma/ATEX", unit: "", aliases: ["compliance", "industry"] },
      { key: "benetzung", label: "Benetzung", unit: "", aliases: ["dry_run_possible", "duty_profile"] },
    ]
  },
  {
    id: "operating_geometry",
    title: "3. Betriebsdaten & Geometrie",
    fields: [
      { key: "shaft_diameter", label: "Wellendurchmesser", unit: "mm", aliases: ["shaft_diameter_mm"] },
      { key: "housing_bore", label: "Gehäusebohrung", unit: "mm", aliases: ["housing_bore_mm"] },
      { key: "installation_width", label: "Einbaubreite", unit: "mm", aliases: ["installation_width_mm"] },
      { key: "speed_rpm", label: "Drehzahl", unit: "rpm" },
      { key: "pressure_nominal", label: "Betriebsdruck", unit: "bar", aliases: ["pressure_bar"] },
      { key: "surface_finish", label: "Oberfläche", unit: "", aliases: ["counterface_surface"] },
      { key: "shaft_material", label: "Wellenwerkstoff", unit: "" },
      { key: "shaft_runout", label: "Rundlauf", unit: "mm", aliases: ["runout_mm"] },
    ]
  },
  {
    id: "risk_readiness",
    title: "4. Risiken & Anfrage-Reife",
    fields: [
      { key: "top_risks", label: "Top-Risiken", unit: "", aliases: ["contamination", "medium_qualifiers"] },
      { key: "readiness_level", label: "Readiness Level", unit: "" },
      { key: "blocking_unknowns", label: "Blockierende Unbekannte", unit: "" },
      { key: "recommended_next_question", label: "Nächste Frage", unit: "" },
      { key: "rfq_possible", label: "RFQ möglich", unit: "" },
      { key: "compliance", label: "Norm/Hygiene/ATEX", unit: "", aliases: ["industry"] },
    ]
  }
];

function readParameterValue(parameters: Record<string, any>, assertion: any, key: string, aliases: string[] = []) {
  for (const candidate of [key, ...aliases]) {
    const value = parameters[candidate] ?? assertion?.[candidate]?.value;
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }
  return null;
}

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
      const rawVal = readParameterValue(parameters, assertions, f.key, f.aliases);
      
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
