import type { WorkspaceRfqReadinessProjection } from "./workspace.ts";

export type AgentStreamRequest = {
  caseId?: string;
  conversationId?: string;
  message: string;
  turnId?: string;
  turn_id?: string;
};

export type AgentAnswerTrace = {
  reply_source:
    | "fast_responder"
    | "knowledge_service"
    | "light_conversation"
    | "exploration_stream"
    | "governed_output_contract"
    | "hcl"
    | "legacy_renderer"
    | "api_guard"
    | "unknown";
  answer_markdown_source:
    | "reply_passthrough"
    | "fast_responder"
    | "knowledge_service"
    | "knowledge_composer"
    | "governed_composer"
    | "hcl"
    | "light_conversation"
    | "exploration_stream"
    | "legacy_renderer"
    | "composer_fallback"
    | "deterministic_fallback"
    | "unknown";
  final_visible_source:
    | "answer_markdown"
    | "reply"
    | "unknown";
  composer_attempted: boolean;
  composer_succeeded: boolean;
  hcl_attempted: boolean;
  hcl_succeeded: boolean;
  fallback_reason: string | null;
};

export type AgentRunMeta = Record<string, unknown> & {
  answer_trace?: AgentAnswerTrace;
};

export type TurnEnvelope = {
  turn_id: string;
  session_id: string;
  case_id?: string | null;
  case_revision_before?: number | null;
  case_revision_after?: number | null;
  user_message: string;
  route: string;
  intent: string;
  is_technical: boolean;
  state_mutation_policy: string;
  requires_engine: boolean;
  requires_evidence: boolean;
  requires_adversarial_review: boolean;
  requires_final_guard: boolean;
  streaming_policy: string;
  created_at: string;
  trace_id: string;
};

export type FinalGuardResult = {
  decision: string;
  severity: string;
  blocked_reasons?: string[];
  required_revisions?: string[];
  allowed_claim_level?: string;
  detected_forbidden_claims?: string[];
  human_review_required?: boolean;
  user_visible_limitations?: string[];
  final_stream_allowed?: boolean;
};

export type V92DashboardContract = Record<string, unknown> & {
  schema_version?: string;
  case_id?: string | null;
  case_revision?: number | null;
  turn_id?: string;
  route?: string;
  readiness_band?: string;
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
  v92?: {
    seal_system?: {
      status?: string;
      seal_family?: string;
      seal_type?: string;
      missing_fields?: string[];
      validity_boundaries?: string[];
    };
    engineering?: {
      status?: string;
      route?: string;
      next_best_engineering_action?: string;
      blockers?: string[];
    };
    calculations?: {
      status?: string;
      result_count?: number;
      blocked_calculations?: string[];
      guardrail_violations?: string[];
    };
    standards?: {
      status?: string;
      registry_version?: string;
      applicable_count?: number;
      blocking_gaps?: string[];
      claim_boundary?: string;
    };
    evidence_graph?: {
      status?: string;
      node_count?: number;
      unresolved_gaps?: string[];
    };
    compound?: {
      status?: string;
      material_family_count?: number;
      compound_count?: number;
      product_count?: number;
      separation_violations?: string[];
    };
    review?: {
      status?: string;
      blocking_findings?: string[];
      required_corrections?: string[];
    };
    dossier?: {
      status?: string;
      dossier_id?: string | null;
      fact_count?: number;
      calculation_count?: number;
      candidate_count?: number;
      blockers?: string[];
      no_final_technical_release?: boolean;
    };
  };
};

export type AssertionEntry = {
  value: string;
  confidence: string;
};

export type ProposedCaseDeltaField = {
  field_name: string;
  proposed_value: unknown;
  unit?: string | null;
  provenance?: string;
  confidence?: string;
  confirmation_required?: boolean;
  source_turn_index?: number;
  status?: "proposed" | "accepted" | "rejected" | string;
};

export type ProposedCaseDelta = {
  fields: ProposedCaseDeltaField[];
  source?: string;
  schema_version?: string;
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
  caseId?: string;
  noCaseCreated?: boolean;
  reply?: string;
  answer_markdown?: string;
  responseClass?: OutwardResponseClass | null;
  assertions?: Record<string, AssertionEntry>;
  structuredState?: Record<string, unknown> | null;
  conversationStrategy?: AgentConversationStrategy | null;
  turnContext?: AgentTurnContext | null;
  turnEnvelope?: TurnEnvelope | null;
  turnBoundaryDecision?: Record<string, unknown> | null;
  finalAnswerContext?: Record<string, unknown> | null;
  nonTechnicalAnswerContext?: Record<string, unknown> | null;
  finalGuardResult?: FinalGuardResult | null;
  v92Dashboard?: V92DashboardContract | null;
  proposedCaseDelta?: ProposedCaseDelta | null;
  rfq_readiness_projection?: WorkspaceRfqReadinessProjection | null;
  ui?: AgentWorkspaceUi;
  runMeta?: AgentRunMeta | null;
};

export type AgentStreamEvent =
  | { type: "case_bound"; caseId: string }
  | { type: "answer.stream.start"; source?: "answer_markdown" | "reply" }
  | { type: "answer.token"; text: string }
  | { type: "answer.done" }
  | { type: "progress"; data?: unknown }
  | { type: "message_complete"; message: string }
  | AgentStateUpdateEvent
  | { type: "workspace_hint"; caseId: string }
  | { type: "error"; code: string; message: string };
