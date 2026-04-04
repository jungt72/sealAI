export type AgentOverrideItemRequest = {
  field_name: string;
  value: unknown;
  unit?: string | null;
};

export type AgentOverrideRequest = {
  overrides: AgentOverrideItemRequest[];
  turn_index?: number;
};

export type AgentOverrideResponse = {
  session_id: string;
  applied_fields: string[];
  governance: {
    gov_class: string | null;
    rfq_admissible: boolean;
    blocking_unknowns: string[];
    conflict_flags: string[];
    validity_limits: string[];
    open_validation_points: string[];
  };
};

export async function patchAgentOverrides(
  caseId: string,
  payload: AgentOverrideRequest,
): Promise<AgentOverrideResponse> {
  const response = await fetch(`/api/bff/agent/session/${encodeURIComponent(caseId)}/override`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message =
      body?.error?.message ||
      body?.detail?.message ||
      body?.detail ||
      `parameter_override_failed:${response.status}`;
    throw new Error(message);
  }

  return (await response.json()) as AgentOverrideResponse;
}
