import { CockpitData } from "@/hooks/useCockpitData";

export interface RfqArtifact {
  caseId: string;
  request_type: string | null;
  parameters: Record<string, any>;
  missing: string[];
  risks: string[];
  readiness: {
    is_ready: boolean;
    status: string;
    blockers: string[];
  };
  summary: string;
}

export function generateTechnicalSummary(data: CockpitData): string {
  const { view, parameters } = data;
  const lines: string[] = [];

  lines.push(`# Technische Zusammenfassung — Fall: ${data.view.path || "unbestimmt"}`);
  lines.push(`Status: ${view.readiness.status.toUpperCase()} (${Math.round(data.coverage * 100)}% Vollständigkeit)`);
  lines.push("");

  lines.push("## 1. Problemstellung & Ziel");
  lines.push(`Anfragetyp: ${(view.requestType && view.requestType !== "nicht bestimmt") ? view.requestType.toUpperCase() : "STANDARD"}`);
  lines.push(`Medium: ${view.mediumContext.canonicalName || "Nicht identifiziert"}`);
  lines.push("");

  lines.push("## 2. Bekannte Betriebsparameter");
  const coreProps = view.sections.core_intake?.properties || [];
  coreProps.forEach(p => {
    if (p.value !== null) {
      lines.push(`- ${p.label}: ${p.value}${p.unit ? ` ${p.unit}` : ""}`);
    }
  });
  lines.push("");

  if (view.readiness.missingMandatoryKeys.length > 0) {
    lines.push("## 3. Offene Punkte (Kritisch)");
    view.readiness.missingMandatoryKeys.forEach(key => {
      lines.push(`- Fehlt: ${key.replace(/_/g, " ")}`);
    });
    lines.push("");
  }

  if (view.mediumContext.riskFlags.length > 0 || view.readiness.blockers.length > 0) {
    lines.push("## 4. Risikobewertung & Blocker");
    [...view.mediumContext.riskFlags, ...view.readiness.blockers].forEach(r => {
      lines.push(`- ACHTUNG: ${r}`);
    });
    lines.push("");
  }

  lines.push("---");
  lines.push("Erzeugt durch SealingAI — Sealing Intelligence");
  
  return lines.join("\n");
}

export function createRfqJson(data: CockpitData, caseId: string): RfqArtifact {
  // Clean parameters: only keep non-null, non-undefined values
  const cleanedParams: Record<string, any> = {};
  Object.entries(data.parameters).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      cleanedParams[key] = value;
    }
  });

  return {
    caseId,
    request_type: (data.view.requestType && data.view.requestType !== "nicht bestimmt") 
      ? data.view.requestType 
      : data.view.path,
    parameters: cleanedParams,
    missing: data.view.readiness.missingMandatoryKeys,
    risks: [...data.view.mediumStatus.status === "unavailable" ? ["Medium nicht identifiziert"] : [], ...data.view.mediumContext.riskFlags, ...data.view.readiness.blockers],
    readiness: {
      is_ready: data.view.readiness.isRfqReady,
      status: data.view.readiness.status,
      blockers: data.view.readiness.blockers
    },
    summary: generateTechnicalSummary(data)
  };
}
