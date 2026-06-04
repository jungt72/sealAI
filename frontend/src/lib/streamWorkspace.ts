import type {
  ActionChip,
  AgentStateUpdateEvent,
  AgentTurnContext,
  AgentWorkspaceUi,
  AssertionEntry,
  PocketCockpitPatch,
  ProposedCaseDelta,
} from "@/lib/contracts/agent";
import type { WorkspaceRfqReadinessProjection } from "./contracts/workspace.ts";
import { mapRfqReadinessProjection } from "./mapping/rfqReadiness.ts";

export type StreamWorkspaceView = {
  caseId: string;
  reply: string | null;
  responseClass: string | null;
  assertions: Record<string, AssertionEntry> | null;
  structuredState: Record<string, unknown> | null;
  turnContext: AgentTurnContext | null;
  v92Dashboard: Record<string, unknown> | null;
  proposedCaseDelta: ProposedCaseDelta | null;
  rfqReadinessProjection: WorkspaceRfqReadinessProjection | null;
  // V1.6 mobile-first additive fields (Patch 6). Backend-provided Pocket Cockpit
  // for mobile-triage turns; null on legacy/non-mobile turns (client-derived
  // fallback then applies).
  pocketCockpitPatch: PocketCockpitPatch | null;
  actionChips: ActionChip[] | null;
  ui: Required<Pick<AgentWorkspaceUi, "parameter" | "assumption" | "recommendation" | "compute" | "matching" | "rfq" | "medium_classification" | "medium_context" | "v92">> &
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

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function uiSection<T>(
  eventUi: AgentWorkspaceUi,
  structuredUi: AgentWorkspaceUi,
  key: keyof AgentWorkspaceUi,
): T | undefined {
  return (eventUi[key] ?? structuredUi[key]) as T | undefined;
}

function workspaceUiFromEvent(event: AgentStateUpdateEvent): AgentWorkspaceUi {
  const eventUi = (asRecord(event.ui) ?? {}) as AgentWorkspaceUi;
  const structuredState = asRecord(event.structuredState);
  const structuredUi = (asRecord(structuredState?.view) ?? {}) as AgentWorkspaceUi;

  return {
    ...structuredUi,
    ...eventUi,
    parameter: uiSection(eventUi, structuredUi, "parameter"),
    assumption: uiSection(eventUi, structuredUi, "assumption"),
    recommendation: uiSection(eventUi, structuredUi, "recommendation"),
    compute: uiSection(eventUi, structuredUi, "compute"),
    matching: uiSection(eventUi, structuredUi, "matching"),
    rfq: uiSection(eventUi, structuredUi, "rfq"),
    medium_classification: uiSection(eventUi, structuredUi, "medium_classification"),
    medium_context: uiSection(eventUi, structuredUi, "medium_context"),
    v92: uiSection(eventUi, structuredUi, "v92"),
  };
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

export function buildStreamWorkspaceView(
  event: AgentStateUpdateEvent & { caseId: string },
): StreamWorkspaceView {
  const ui = workspaceUiFromEvent(event);

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
    v92Dashboard:
      event.v92Dashboard && typeof event.v92Dashboard === "object"
        ? event.v92Dashboard
        : null,
    proposedCaseDelta:
      event.proposedCaseDelta && Array.isArray(event.proposedCaseDelta.fields)
        ? event.proposedCaseDelta
        : null,
    rfqReadinessProjection: mapRfqReadinessProjection(event.rfq_readiness_projection),
    pocketCockpitPatch:
      event.pocket_cockpit_patch && typeof event.pocket_cockpit_patch === "object"
        ? event.pocket_cockpit_patch
        : null,
    actionChips: Array.isArray(event.action_chips) ? event.action_chips : null,
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
      v92: {
        seal_system: {
          status: typeof ui.v92?.seal_system?.status === "string" ? ui.v92.seal_system.status : "pending",
          seal_family:
            typeof ui.v92?.seal_system?.seal_family === "string"
              ? ui.v92.seal_system.seal_family
              : "unknown",
          seal_type:
            typeof ui.v92?.seal_system?.seal_type === "string"
              ? ui.v92.seal_system.seal_type
              : "unknown_seal",
          missing_fields: asStringArray(ui.v92?.seal_system?.missing_fields),
          validity_boundaries: asStringArray(ui.v92?.seal_system?.validity_boundaries),
        },
        engineering: {
          status:
            typeof ui.v92?.engineering?.status === "string" ? ui.v92.engineering.status : "pending",
          route: typeof ui.v92?.engineering?.route === "string" ? ui.v92.engineering.route : "unknown",
          next_best_engineering_action:
            typeof ui.v92?.engineering?.next_best_engineering_action === "string"
              ? ui.v92.engineering.next_best_engineering_action
              : "identify_seal_system",
          blockers: asStringArray(ui.v92?.engineering?.blockers),
        },
        calculations: {
          status:
            typeof ui.v92?.calculations?.status === "string" ? ui.v92.calculations.status : "pending",
          result_count:
            typeof ui.v92?.calculations?.result_count === "number"
              ? ui.v92.calculations.result_count
              : 0,
          blocked_calculations: asStringArray(ui.v92?.calculations?.blocked_calculations),
          guardrail_violations: asStringArray(ui.v92?.calculations?.guardrail_violations),
        },
        standards: {
          status: typeof ui.v92?.standards?.status === "string" ? ui.v92.standards.status : "pending",
          registry_version:
            typeof ui.v92?.standards?.registry_version === "string"
              ? ui.v92.standards.registry_version
              : "standards_registry_metadata_v1",
          applicable_count:
            typeof ui.v92?.standards?.applicable_count === "number"
              ? ui.v92.standards.applicable_count
              : 0,
          blocking_gaps: asStringArray(ui.v92?.standards?.blocking_gaps),
          claim_boundary:
            typeof ui.v92?.standards?.claim_boundary === "string"
              ? ui.v92.standards.claim_boundary
              : "",
        },
        evidence_graph: {
          status:
            typeof ui.v92?.evidence_graph?.status === "string"
              ? ui.v92.evidence_graph.status
              : "pending",
          node_count:
            typeof ui.v92?.evidence_graph?.node_count === "number"
              ? ui.v92.evidence_graph.node_count
              : 0,
          unresolved_gaps: asStringArray(ui.v92?.evidence_graph?.unresolved_gaps),
        },
        compound: {
          status: typeof ui.v92?.compound?.status === "string" ? ui.v92.compound.status : "pending",
          material_family_count:
            typeof ui.v92?.compound?.material_family_count === "number"
              ? ui.v92.compound.material_family_count
              : 0,
          compound_count:
            typeof ui.v92?.compound?.compound_count === "number" ? ui.v92.compound.compound_count : 0,
          product_count:
            typeof ui.v92?.compound?.product_count === "number" ? ui.v92.compound.product_count : 0,
          separation_violations: asStringArray(ui.v92?.compound?.separation_violations),
        },
        review: {
          status: typeof ui.v92?.review?.status === "string" ? ui.v92.review.status : "not_started",
          blocking_findings: asStringArray(ui.v92?.review?.blocking_findings),
          required_corrections: asStringArray(ui.v92?.review?.required_corrections),
        },
        dossier: {
          status: typeof ui.v92?.dossier?.status === "string" ? ui.v92.dossier.status : "pending",
          dossier_id:
            typeof ui.v92?.dossier?.dossier_id === "string" ? ui.v92.dossier.dossier_id : null,
          fact_count:
            typeof ui.v92?.dossier?.fact_count === "number" ? ui.v92.dossier.fact_count : 0,
          calculation_count:
            typeof ui.v92?.dossier?.calculation_count === "number"
              ? ui.v92.dossier.calculation_count
              : 0,
          candidate_count:
            typeof ui.v92?.dossier?.candidate_count === "number"
              ? ui.v92.dossier.candidate_count
              : 0,
          blockers: asStringArray(ui.v92?.dossier?.blockers),
          no_final_technical_release: Boolean(ui.v92?.dossier?.no_final_technical_release),
        },
      },
    },
  };
}
