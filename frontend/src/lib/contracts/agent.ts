export type AgentStreamRequest = {
  caseId?: string;
  message: string;
};

export const OUTWARD_RESPONSE_CLASSES = [
  "conversational_answer",
  "structured_clarification",
  "governed_state_update",
  "technical_preselection",
  "candidate_shortlist",
  "inquiry_ready",
] as const;

export type OutwardResponseClass = (typeof OUTWARD_RESPONSE_CLASSES)[number];

export function isOutwardResponseClass(value: unknown): value is OutwardResponseClass {
  return (
    typeof value === "string" &&
    (OUTWARD_RESPONSE_CLASSES as readonly string[]).includes(value)
  );
}

export type AgentInquiryUi = {
  status?: string;
  inquiry_ready?: boolean;
  inquiry_admissible?: boolean;
  /** @deprecated Compat alias for inquiry_ready. */
  rfq_ready?: boolean;
  /** @deprecated Compat alias for inquiry_admissible. */
  rfq_admissible?: boolean;
  selected_manufacturer?: string | null;
  recipient_count?: number;
  qualified_material_count?: number;
  requirement_class?: string | null;
  dispatch_ready?: boolean;
  dispatch_status?: string;
  notes?: string[];
};

export type AgentWorkspaceUi = {
  parameter?: {
    parameters?: Array<{
      field_name?: string;
      value?: unknown;
      unit?: string | null;
      confidence?: string;
    }>;
    parameter_count?: number;
    needs_confirmation?: boolean;
  };
  assumption?: {
    items?: Array<{
      kind?: string;
      text?: string;
    }>;
    open_points?: string[];
    has_open_points?: boolean;
  };
  recommendation?: {
    scope_status?: string;
    inquiry_admissible?: boolean;
    /** @deprecated Compat alias for inquiry_admissible. */
    rfq_admissible?: boolean;
    requirement_class?: string | null;
    requirement_summary?: string | null;
    validity_notes?: string[];
    open_points?: string[];
  };
  compute?: {
    items?: Array<{
      calc_type?: string;
      status?: string;
      v_surface_m_s?: unknown;
      pv_value_mpa_m_s?: unknown;
      dn_value?: unknown;
      notes?: string[];
    }>;
  };
  matching?: {
    status?: string;
    selected_manufacturer?: string | null;
    manufacturer_count?: number;
    manufacturers?: string[];
    notes?: string[];
  };
  inquiry?: AgentInquiryUi;
  /** @deprecated Compat alias for inquiry. */
  rfq?: AgentInquiryUi;
  medium_classification?: {
    canonical_label?: string | null;
    family?: string;
    confidence?: string;
    status?: string;
    normalization_source?: string | null;
    mapping_confidence?: string | null;
    matched_alias?: string | null;
    source_registry_key?: string | null;
    followup_question?: string | null;
    primary_raw_text?: string | null;
    raw_mentions?: string[];
  };
  medium_context?: {
    medium_label?: string | null;
    status?: string;
    scope?: string;
    summary?: string | null;
    properties?: string[];
    challenges?: string[];
    followup_points?: string[];
    confidence?: string | null;
    source_type?: string | null;
    not_for_release_decisions?: boolean;
    disclaimer?: string | null;
  };
  norm?: {
    status?: string;
    norm_version?: string | null;
    sealai_request_id?: string | null;
    requirement_class?: string | null;
    seal_family?: string | null;
    application_summary?: string | null;
    material_family?: string | null;
    qualified_material_count?: number;
    open_points?: string[];
    validity_notes?: string[];
  };
  export_profile?: {
    status?: string;
    export_profile_version?: string | null;
    sealai_request_id?: string | null;
    selected_manufacturer?: string | null;
    recipient_count?: number;
    requirement_class?: string | null;
    application_summary?: string | null;
    dimensions_summary?: string[];
    material_summary?: string | null;
    inquiry_ready?: boolean;
    /** @deprecated Compat alias for inquiry_ready. */
    rfq_ready?: boolean;
    dispatch_ready?: boolean;
    unresolved_points?: string[];
    notes?: string[];
  };
  manufacturer_mapping?: {
    status?: string;
    mapping_version?: string | null;
    selected_manufacturer?: string | null;
    mapped_product_family?: string | null;
    mapped_material_family?: string | null;
    geometry_export_hint?: string | null;
    unresolved_mapping_points?: string[];
    notes?: string[];
  };
  dispatch_contract?: {
    status?: string;
    contract_version?: string | null;
    sealai_request_id?: string | null;
    selected_manufacturer?: string | null;
    recipient_count?: number;
    requirement_class?: string | null;
    application_summary?: string | null;
    material_summary?: string | null;
    dimensions_summary?: string[];
    inquiry_ready?: boolean;
    /** @deprecated Compat alias for inquiry_ready. */
    rfq_ready?: boolean;
    dispatch_ready?: boolean;
    unresolved_points?: string[];
    mapping_summary?: string | null;
    handover_notes?: string[];
  };
};

export type AssertionEntry = {
  value: string;
  confidence: string;
};

export type AgentConversationStrategy = {
  conversationPhase: string;
  turnGoal: string;
  primaryQuestion?: string | null;
  supportingReason?: string | null;
  responseMode: string;
};

export type AgentTurnContext = {
  conversationPhase: string;
  turnGoal: string;
  primaryQuestion?: string | null;
  supportingReason?: string | null;
  responseMode: string;
  confirmedFactsSummary?: string[];
  openPointsSummary?: string[];
};

export type AgentStateUpdateEvent = {
  type: "state_update";
  caseId: string;
  reply?: string;
  responseClass?: OutwardResponseClass | null;
  assertions?: Record<string, AssertionEntry>;
  structuredState?: Record<string, unknown> | null;
  conversationStrategy?: AgentConversationStrategy | null;
  turnContext?: AgentTurnContext | null;
  ui?: AgentWorkspaceUi;
};

export type AgentStreamEvent =
  | { type: "case_bound"; caseId: string }
  | { type: "token"; text: string }
  | { type: "message_complete"; message: string }
  | AgentStateUpdateEvent
  | { type: "workspace_hint"; caseId: string }
  | { type: "error"; code: string; message: string };
