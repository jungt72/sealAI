import { CockpitData } from "@/hooks/useCockpitData";

export interface RfqPayload {
  case_id: string;
  request_type: string;
  engineering_path: string | null;
  parameters: Record<string, any>;
  risks: string[];
  missing: string[];
  summary: string;
  attachments: string[];
  manufacturer_ids: string[];
}

export function buildRfqPayload(
  data: CockpitData, 
  caseId: string, 
  selectedManufacturerIds: string[]
): RfqPayload {
  const { view, parameters } = data;
  
  // Clean parameters: only keep non-null, non-undefined values
  const cleanedParams: Record<string, any> = {};
  Object.entries(parameters).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      cleanedParams[key] = value;
    }
  });

  return {
    case_id: caseId,
    request_type: (view.requestType && view.requestType !== "nicht bestimmt") 
      ? view.requestType 
      : "nicht_bestimmt",
    engineering_path: view.path,
    parameters: cleanedParams,
    risks: [
      ...data.mediumStatus.status === "unavailable" ? ["Medium nicht identifiziert"] : [], 
      ...view.mediumContext.riskFlags, 
      ...view.readiness.blockers
    ],
    missing: view.readiness.missingMandatoryKeys,
    summary: data.view.mediumContext.canonicalName 
      ? `Technische Anfrage für ${data.view.mediumContext.canonicalName} im Pfad ${view.path || "unbestimmt"}.`
      : `Technische Anfrage für unidentifiziertes Medium im Pfad ${view.path || "unbestimmt"}.`,
    attachments: [],
    manufacturer_ids: selectedManufacturerIds
  };
}
