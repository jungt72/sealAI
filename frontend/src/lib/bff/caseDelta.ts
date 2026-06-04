export type CaseDeltaAction = "accept" | "reject";

export type CaseDeltaDecisionResponse = {
  session_id: string;
  action: CaseDeltaAction;
  source_event_id: string;
  applied_fields: string[];
  rejected_fields: string[];
  governance: Record<string, unknown>;
};

export async function decideCaseDelta(
  caseId: string,
  action: CaseDeltaAction,
  fieldNames: string[] = [],
): Promise<CaseDeltaDecisionResponse> {
  const response = await fetch(
    `/api/bff/agent/session/${encodeURIComponent(caseId)}/case-delta`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, field_names: fieldNames }),
    },
  );

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message = payload?.error?.message || `case_delta_decision_failed:${response.status}`;
    throw new Error(message);
  }

  return (await response.json()) as CaseDeltaDecisionResponse;
}
