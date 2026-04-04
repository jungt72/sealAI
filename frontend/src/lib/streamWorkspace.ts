import type {
  AgentStateUpdateEvent,
  AgentTurnContext,
  AgentWorkspaceUi,
  AssertionEntry,
} from "@/lib/contracts/agent";

export type StreamWorkspaceView = {
  caseId: string;
  reply: string | null;
  responseClass: string | null;
  assertions: Record<string, AssertionEntry> | null;
  structuredState: Record<string, unknown> | null;
  turnContext: AgentTurnContext | null;
  ui: Required<Pick<AgentWorkspaceUi, "parameter" | "assumption" | "recommendation" | "compute" | "matching" | "rfq" | "medium_classification" | "medium_context">> &
    AgentWorkspaceUi;
};

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
    .filter(Boolean);
}

function normalizeTurnContext(value: AgentStateUpdateEvent["turnContext"]): AgentTurnContext | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const conversationPhase =
    typeof value.conversationPhase === "string" && value.conversationPhase.trim()
      ? value.conversationPhase
      : null;
  const turnGoal =
    typeof value.turnGoal === "string" && value.turnGoal.trim() ? value.turnGoal : null;
  const responseMode =
    typeof value.responseMode === "string" && value.responseMode.trim() ? value.responseMode : null;

  if (!conversationPhase || !turnGoal || !responseMode) {
    return null;
  }

  return {
    conversationPhase,
    turnGoal,
    responseMode,
    primaryQuestion:
      typeof value.primaryQuestion === "string" && value.primaryQuestion.trim()
        ? value.primaryQuestion
        : null,
    supportingReason:
      typeof value.supportingReason === "string" && value.supportingReason.trim()
        ? value.supportingReason
        : null,
    confirmedFactsSummary: asStringArray(value.confirmedFactsSummary),
    openPointsSummary: asStringArray(value.openPointsSummary),
  };
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function buildStreamWorkspaceView(event: AgentStateUpdateEvent): StreamWorkspaceView {
  const ui = event.ui || {};

  const assertions: Record<string, AssertionEntry> | null =
    event.assertions && typeof event.assertions === "object" && Object.keys(event.assertions).length > 0
      ? event.assertions
      : null;

  return {
    caseId: event.caseId,
    reply: typeof event.reply === "string" && event.reply.trim() ? event.reply : null,
    responseClass: typeof event.responseClass === "string" ? event.responseClass : null,
    assertions,
    structuredState:
      event.structuredState && typeof event.structuredState === "object"
        ? event.structuredState
        : null,
    turnContext: normalizeTurnContext(event.turnContext),
    ui: {
      ...ui,
      parameter: {
        parameters: Array.isArray(ui.parameter?.parameters) ? ui.parameter.parameters : [],
        parameter_count:
          typeof ui.parameter?.parameter_count === "number" ? ui.parameter.parameter_count : 0,
        needs_confirmation: Boolean(ui.parameter?.needs_confirmation),
      },
      assumption: {
        items: Array.isArray(ui.assumption?.items) ? ui.assumption.items : [],
        open_points: asStringArray(ui.assumption?.open_points),
        has_open_points: Boolean(ui.assumption?.has_open_points),
      },
      recommendation: {
        scope_status:
          typeof ui.recommendation?.scope_status === "string"
            ? ui.recommendation.scope_status
            : "pending",
        rfq_admissible: Boolean(ui.recommendation?.rfq_admissible),
        requirement_class:
          typeof ui.recommendation?.requirement_class === "string"
            ? ui.recommendation.requirement_class
            : null,
        requirement_summary:
          typeof ui.recommendation?.requirement_summary === "string"
            ? ui.recommendation.requirement_summary
            : null,
        validity_notes: asStringArray(ui.recommendation?.validity_notes),
        open_points: asStringArray(ui.recommendation?.open_points),
      },
      compute: {
        items: Array.isArray(ui.compute?.items)
          ? ui.compute.items.map((item) => ({
              calc_type: typeof item?.calc_type === "string" ? item.calc_type : "unknown",
              status: typeof item?.status === "string" ? item.status : "insufficient_data",
              v_surface_m_s: asNumber(item?.v_surface_m_s),
              pv_value_mpa_m_s: asNumber(item?.pv_value_mpa_m_s),
              dn_value: asNumber(item?.dn_value),
              notes: asStringArray(item?.notes),
            }))
          : [],
      },
      matching: {
        status: typeof ui.matching?.status === "string" ? ui.matching.status : "pending",
        selected_manufacturer:
          typeof ui.matching?.selected_manufacturer === "string"
            ? ui.matching.selected_manufacturer
            : null,
        manufacturer_count:
          typeof ui.matching?.manufacturer_count === "number"
            ? ui.matching.manufacturer_count
            : 0,
        manufacturers: asStringArray(ui.matching?.manufacturers),
        notes: asStringArray(ui.matching?.notes),
      },
      rfq: {
        status: typeof ui.rfq?.status === "string" ? ui.rfq.status : "pending",
        rfq_ready: Boolean(ui.rfq?.rfq_ready),
        rfq_admissible: Boolean(ui.rfq?.rfq_admissible),
        selected_manufacturer:
          typeof ui.rfq?.selected_manufacturer === "string" ? ui.rfq.selected_manufacturer : null,
        recipient_count:
          typeof ui.rfq?.recipient_count === "number" ? ui.rfq.recipient_count : 0,
        qualified_material_count:
          typeof ui.rfq?.qualified_material_count === "number"
            ? ui.rfq.qualified_material_count
            : 0,
        requirement_class:
          typeof ui.rfq?.requirement_class === "string" ? ui.rfq.requirement_class : null,
        dispatch_ready: Boolean(ui.rfq?.dispatch_ready),
        dispatch_status: typeof ui.rfq?.dispatch_status === "string" ? ui.rfq.dispatch_status : "pending",
        notes: asStringArray(ui.rfq?.notes),
      },
      medium_classification: {
        canonical_label:
          typeof ui.medium_classification?.canonical_label === "string"
            ? ui.medium_classification.canonical_label
            : null,
        family:
          typeof ui.medium_classification?.family === "string"
            ? ui.medium_classification.family
            : "unknown",
        confidence:
          typeof ui.medium_classification?.confidence === "string"
            ? ui.medium_classification.confidence
            : "low",
        status:
          typeof ui.medium_classification?.status === "string"
            ? ui.medium_classification.status
            : "unavailable",
        normalization_source:
          typeof ui.medium_classification?.normalization_source === "string"
            ? ui.medium_classification.normalization_source
            : null,
        mapping_confidence:
          typeof ui.medium_classification?.mapping_confidence === "string"
            ? ui.medium_classification.mapping_confidence
            : null,
        matched_alias:
          typeof ui.medium_classification?.matched_alias === "string"
            ? ui.medium_classification.matched_alias
            : null,
        source_registry_key:
          typeof ui.medium_classification?.source_registry_key === "string"
            ? ui.medium_classification.source_registry_key
            : null,
        followup_question:
          typeof ui.medium_classification?.followup_question === "string"
            ? ui.medium_classification.followup_question
            : null,
        primary_raw_text:
          typeof ui.medium_classification?.primary_raw_text === "string"
            ? ui.medium_classification.primary_raw_text
            : null,
        raw_mentions: asStringArray(ui.medium_classification?.raw_mentions),
      },
      medium_context: {
        medium_label:
          typeof ui.medium_context?.medium_label === "string"
            ? ui.medium_context.medium_label
            : null,
        status:
          typeof ui.medium_context?.status === "string"
            ? ui.medium_context.status
            : "unavailable",
        scope:
          typeof ui.medium_context?.scope === "string"
            ? ui.medium_context.scope
            : "orientierend",
        summary:
          typeof ui.medium_context?.summary === "string"
            ? ui.medium_context.summary
            : null,
        properties: asStringArray(ui.medium_context?.properties),
        challenges: asStringArray(ui.medium_context?.challenges),
        followup_points: asStringArray(ui.medium_context?.followup_points),
        confidence:
          typeof ui.medium_context?.confidence === "string"
            ? ui.medium_context.confidence
            : null,
        source_type:
          typeof ui.medium_context?.source_type === "string"
            ? ui.medium_context.source_type
            : null,
        not_for_release_decisions: Boolean(ui.medium_context?.not_for_release_decisions),
        disclaimer:
          typeof ui.medium_context?.disclaimer === "string"
            ? ui.medium_context.disclaimer
            : null,
      },
    },
  };
}
