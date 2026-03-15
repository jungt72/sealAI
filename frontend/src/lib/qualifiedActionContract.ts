export type QualifiedActionResponse = {
  case_id: string;
  action: string;
  allowed: boolean;
  executed: boolean;
  block_reasons: string[];
  runtime_path: string;
  binding_level: string;
  qualified_action_gate?: Record<string, unknown> | null;
  case_state?: Record<string, unknown> | null;
  visible_case_narrative?: Record<string, unknown> | null;
  action_payload?: Record<string, unknown> | null;
  audit_event?: Record<string, unknown> | null;
};

export async function invokeQualifiedAction(params: {
  apiEndpoint: string;
  caseId: string;
  authToken: string;
  action?: "download_rfq";
}): Promise<QualifiedActionResponse> {
  const { apiEndpoint, caseId, authToken, action = "download_rfq" } = params;
  const response = await fetch(`${apiEndpoint}/cases/${caseId}/actions/download-rfq`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ action }),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      (payload && typeof payload.detail === "string" && payload.detail) ||
        `Qualified action request failed (${response.status})`,
    );
  }
  return payload as QualifiedActionResponse;
}
