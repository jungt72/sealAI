export interface AgentContributor {
  agent: string;
  confidence?: number;
}

export interface AgentPayload {
  answer?: string;
  confidence?: number;
  evidence?: unknown[];
  metadata?: Record<string, unknown>;
}

export interface AggregatedResponse extends AgentPayload {
  metadata?: AgentPayload['metadata'] & {
    contributors?: AgentContributor[];
  };
}

export interface DebatePayload {
  answer?: string;
  confidence?: number;
  evidence?: unknown[];
  metadata?: Record<string, unknown>;
}

export interface LangGraphFinalPayload {
  trace_id?: string;
  session_id?: string;
  confidence?: number;
  domain?: string;
  responses?: Record<string, AgentPayload>;
  debate?: DebatePayload;
  aggregated?: AggregatedResponse;
  ui_events?: unknown[];
  [key: string]: unknown;
}
