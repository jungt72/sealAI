import type { WorkspaceView, WorkspaceLifecycleStep } from "@/lib/contracts/workspace";
import type {
  EngineeringCockpitView,
  EngineeringCheckResult,
  EngineeringPath,
  EngineeringSection,
  EngineeringSectionId,
} from "@/lib/engineering/cockpitModel";
import { buildRfqDocumentReadPath } from "../bff/workspace.ts";

type RawCockpitProperty = {
  key?: string;
  label?: string;
  value?: unknown;
  unit?: string | null;
  origin?: string | null;
  confidence?: string | null;
  is_confirmed?: boolean;
  is_mandatory?: boolean;
};

type RawCockpitSection = {
  section_id?: string | null;
  title?: string | null;
  completion?: {
    mandatory_present?: number;
    mandatory_total?: number;
    percent?: number;
  } | null;
  properties?: RawCockpitProperty[];
};

type RawEngineeringCheckResult = {
  calc_id?: string;
  label?: string;
  formula_version?: string;
  required_inputs?: string[];
  missing_inputs?: string[];
  valid_paths?: string[];
  output_key?: string;
  unit?: string | null;
  status?: string;
  value?: unknown;
  fallback_behavior?: string;
  guardrails?: string[];
  notes?: string[];
};

type RawCockpitView = {
  request_type?: string | null;
  engineering_path?: string | null;
  routing_metadata?: {
    phase?: string | null;
    last_node?: string | null;
    routing?: Record<string, unknown>;
  } | null;
  sections?: RawCockpitSection[];
  checks?: RawEngineeringCheckResult[];
  missing_mandatory_keys?: string[];
  blockers?: string[];
  readiness?: {
    status?: string | null;
    is_rfq_ready?: boolean;
    release_status?: string | null;
    coverage_score?: number | null;
  } | null;
};

type LegacyWorkspaceProjection = {
  request_type?: string | null;
  engineering_path?: string | null;
  cockpit_view?: RawCockpitView | null;
  parameters?: {
    medium?: string | null;
    temperature_c?: number | null;
    pressure_bar?: number | null;
    sealing_type?: string | null;
    pressure_direction?: string | null;
    duty_profile?: string | null;
    shaft_diameter_mm?: number | null;
    speed_rpm?: number | null;
    installation?: string | null;
    geometry_context?: string | null;
    contamination?: string | string[] | null;
    counterface_surface?: string | null;
    tolerances?: string | null;
    industry?: string | null;
    compliance?: string | string[] | null;
    medium_qualifiers?: string | string[] | null;
    motion_type?: string | null;
  } | null;

  communication_context?: {
    conversation_phase?: string | null;
    turn_goal?: string | null;
    primary_question?: string | null;
    supporting_reason?: string | null;
    response_mode?: string | null;
    confirmed_facts_summary?: string[];
    open_points_summary?: string[];
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
  technical_derivations?: Array<{
    calc_type?: string;
    status?: string;
    v_surface_m_s?: number | null;
    pv_value_mpa_m_s?: number | null;
    dn_value?: number | null;
    notes?: string[];
  }>;
  medium_capture?: {
    raw_mentions?: string[];
    primary_raw_text?: string | null;
    source_turn_ref?: string | null;
    source_turn_index?: number | null;
  };
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
  };
  case_summary: {
    thread_id: string | null;
    intent_goal?: string | null;
    turn_count: number;
    max_turns: number;
  };
  completeness: {
    coverage_score: number;
    coverage_gaps: string[];
    completeness_depth: string;
    missing_critical_parameters: string[];
    analysis_complete: boolean;
    recommendation_ready: boolean;
  };
  governance_status: {
    release_status: string;
    scope_of_validity: string[];
    assumptions_active: string[];
    unknowns_release_blocking: string[];
    unknowns_manufacturer_validation: string[];
    gate_failures: string[];
    governance_notes: string[];
    required_disclaimers: string[];
    verification_passed: boolean;
  };
  specificity: {
    material_specificity_required: string;
    completeness_depth: string;
    elevation_possible?: boolean;
    elevation_hints?: Array<{
      label: string;
      field_key: string | null;
      reason: string;
      priority: number;
      action_type: string;
    }>;
    elevation_target?: string | null;
  };
  candidate_clusters: {
    plausibly_viable: Record<string, unknown>[];
    manufacturer_validation_required: Record<string, unknown>[];
    inadmissible_or_excluded: Record<string, unknown>[];
    total_candidates: number;
  };
  conflicts: {
    total: number;
    open: number;
    resolved: number;
    by_severity: Record<string, number>;
    items: Array<{
      conflict_type: string;
      severity: string;
      summary: string;
      resolution_status: string;
    }>;
  };
  claims_summary: {
    total: number;
    by_type: Record<string, number>;
    by_origin: Record<string, number>;
    items: Array<{
      value: string | null;
      claim_type: string;
      claim_origin: string;
    }>;
  };
  evidence_summary?: {
    evidence_present?: boolean;
    evidence_count?: number;
    trusted_sources_present?: boolean;
    evidence_supported_topics?: string[];
    source_backed_findings?: string[];
    deterministic_findings?: string[];
    assumption_based_findings?: string[];
    unresolved_open_points?: string[];
    evidence_gaps?: string[];
  };
  manufacturer_questions: {
    mandatory: string[];
    open_questions: Array<{
      id: string;
      question: string;
      reason: string;
      priority: string;
      category: string;
    }>;
    total_open: number;
  };
  partner_matching: {
    matching_ready: boolean;
    shortlist_ready?: boolean;
    inquiry_ready?: boolean;
    not_ready_reasons: string[];
    blocking_reasons?: string[];
    material_fit_items: Array<{
      material: string;
      cluster: string;
      specificity: string;
      requires_validation: boolean;
      fit_basis: string;
      grounded_facts?: Array<{
        name: string;
        value: string;
        unit: string | null;
        source: string;
        source_rank: number;
        grounding_basis: string;
        is_divergent: boolean;
        variants?: Array<{
          value: string;
          source: string;
          source_rank: number;
        }>;
      }>;
    }>;
    open_manufacturer_questions: string[];
    selected_partner_id?: string | null;
    data_source: string;
  };
  rfq_status: {
    release_status: string;
    rfq_confirmed: boolean;
    rfq_ready?: boolean;
    blockers: string[];
    open_points: string[];
    has_pdf: boolean;
    has_html_report: boolean;
    handover_ready?: boolean;
    handover_initiated?: boolean;
  };
  rfq_package: {
    has_draft: boolean;
    rfq_id: string | null;
    rfq_basis_status: string;
    operating_context_redacted: Record<string, unknown>;
    manufacturer_questions_mandatory: string[];
    conflicts_visible_count: number;
    buyer_assumptions_acknowledged: string[];
  };
  cycle_info: {
    current_assertion_cycle_id: number;
    state_revision: number;
    asserted_profile_revision: number;
    derived_artifacts_stale: boolean;
    stale_reason: string | null;
  };
};

function releaseClassFromStatus(status: string): "A" | "B" | "C" | "D" | null {
  switch (status) {
    case "rfq_ready":
      return "A";
    case "precheck_only":
      return "B";
    case "manufacturer_validation_required":
      return "C";
    case "inadmissible":
      return "D";
    default:
      return null;
  }
}

function buildLifecycleSteps(projection: LegacyWorkspaceProjection): WorkspaceLifecycleStep[] {
  const { case_summary, rfq_status, governance_status, partner_matching, rfq_package } = projection;
  const steps: WorkspaceLifecycleStep[] = [];

  const turnCount = case_summary.turn_count ?? 0;
  steps.push({
    label: "Case Started",
    status: turnCount > 0 ? "done" : "pending",
    detail: turnCount > 0 ? `Turn ${turnCount}/${case_summary.max_turns}` : undefined,
    iconName: "Layers",
  });

  const releaseStatus = governance_status.release_status;
  steps.push({
    label: "Governed Review",
    status: releaseStatus === "inadmissible" ? "active" : "done",
    detail: releaseStatus.replace(/_/g, " "),
    iconName: "Shield",
  });

  steps.push({
    label: "RFQ Draft",
    status: rfq_package.has_draft ? "done" : "pending",
    detail: rfq_package.has_draft ? rfq_status.release_status.replace(/_/g, " ") : undefined,
    iconName: "FileText",
  });

  steps.push({
    label: "Document Generated",
    status: rfq_status.has_html_report ? "done" : rfq_package.has_draft ? "active" : "pending",
    detail: rfq_status.has_pdf ? "PDF available" : rfq_status.has_html_report ? "HTML report" : undefined,
    iconName: "FileDown",
  });

  steps.push({
    label: "Partner Matching",
    status: partner_matching.matching_ready ? "active" : "pending",
    detail: partner_matching.material_fit_items.length > 0
      ? `${partner_matching.material_fit_items.length} candidate${partner_matching.material_fit_items.length === 1 ? "" : "s"}`
      : undefined,
    iconName: "Factory",
  });

  if (rfq_status.handover_initiated) {
    steps.push({
      label: "RFQ Submitted",
      status: "done",
      detail: partner_matching.selected_partner_id || undefined,
      iconName: "Zap",
    });
  }

  return steps;
}

function toEngineeringPath(value: string | null | undefined): EngineeringPath | null {
  return value === "ms_pump" ||
    value === "rwdr" ||
    value === "static" ||
    value === "labyrinth" ||
    value === "hyd_pneu" ||
    value === "unclear_rotary"
    ? value
    : null;
}

function emptyCockpitSection(id: EngineeringSectionId, title: string): EngineeringSection {
  return {
    id,
    title,
    properties: [],
    completion: {
      mandatoryPresent: 0,
      mandatoryTotal: 0,
      percent: 0,
    },
  };
}

function defaultCockpitSections(): Record<EngineeringSectionId, EngineeringSection> {
  return {
    core_intake: emptyCockpitSection("core_intake", "A. Grunddaten"),
    failure_drivers: emptyCockpitSection("failure_drivers", "B. Technische Risikofaktoren"),
    geometry_fit: emptyCockpitSection("geometry_fit", "C. Geometrie & Einbauraum"),
    rfq_liability: emptyCockpitSection("rfq_liability", "D. Anfrage- & Freigabereife"),
  };
}

function mapCockpitChecks(rawChecks: RawEngineeringCheckResult[] | undefined): EngineeringCheckResult[] {
  return (rawChecks || []).map((check) => ({
    calcId: check.calc_id || "",
    label: check.label || check.calc_id || "",
    formulaVersion: check.formula_version || "",
    requiredInputs: check.required_inputs || [],
    missingInputs: check.missing_inputs || [],
    validPaths: (check.valid_paths || []).flatMap((path) => {
      const engineeringPath = toEngineeringPath(path);
      return engineeringPath ? [engineeringPath] : [];
    }),
    outputKey: check.output_key || "",
    unit: check.unit ?? null,
    status: check.status || "insufficient_data",
    value: check.value ?? null,
    fallbackBehavior: check.fallback_behavior || "insufficient_data_when_required_inputs_missing",
    guardrails: check.guardrails || [],
    notes: check.notes || [],
  }));
}

function mapCockpitView(projection: LegacyWorkspaceProjection): EngineeringCockpitView | null {
  const raw = projection.cockpit_view;
  if (!raw) {
    return null;
  }

  const sections = defaultCockpitSections();
  for (const section of raw.sections || []) {
    const id = section.section_id;
    if (id !== "core_intake" && id !== "failure_drivers" && id !== "geometry_fit" && id !== "rfq_liability") {
      continue;
    }
    sections[id] = {
      id,
      title: section.title || sections[id].title,
      completion: {
        mandatoryPresent: section.completion?.mandatory_present ?? 0,
        mandatoryTotal: section.completion?.mandatory_total ?? 0,
        percent: section.completion?.percent ?? 0,
      },
      properties: (section.properties || []).map((property) => ({
        key: property.key || "",
        label: property.label || property.key || "",
        value: property.value ?? null,
        unit: property.unit || undefined,
        origin: property.origin ?? null,
        confidence: property.confidence ?? null,
        isConfirmed: Boolean(property.is_confirmed),
        isMandatory: Boolean(property.is_mandatory),
      })),
    };
  }

  return {
    path: toEngineeringPath(raw.engineering_path) || toEngineeringPath(projection.engineering_path),
    requestType: raw.request_type || projection.request_type || projection.case_summary.intent_goal || "nicht bestimmt",
    routingMetadata: {
      phase: raw.routing_metadata?.phase || null,
      lastNode: raw.routing_metadata?.last_node || null,
      routing: raw.routing_metadata?.routing || {},
    },
    sections,
    checks: mapCockpitChecks(raw.checks),
    readiness: {
      isRfqReady: Boolean(raw.readiness?.is_rfq_ready),
      missingMandatoryKeys: raw.missing_mandatory_keys || [],
      blockers: raw.blockers || [],
      status:
        raw.readiness?.status === "rfq_ready" ||
        raw.readiness?.status === "review_needed" ||
        raw.readiness?.status === "preliminary"
          ? raw.readiness.status
          : "preliminary",
      releaseStatus: raw.readiness?.release_status || projection.governance_status.release_status,
      coverageScore: raw.readiness?.coverage_score ?? projection.completeness.coverage_score,
    },
    mediumContext: {
      canonicalName: projection.medium_classification?.canonical_label || null,
      isConfirmed: projection.medium_classification?.confidence === "high",
      properties: projection.medium_context?.properties || [],
      riskFlags: projection.medium_context?.challenges || [],
    },
  };
}

export function mapWorkspaceView(
  caseId: string,
  projection: LegacyWorkspaceProjection,
): WorkspaceView {
  const lifecycleSteps = buildLifecycleSteps(projection);
  const releaseStatus = projection.governance_status.release_status;
  const hasDocument = Boolean(projection.rfq_status.has_html_report || projection.rfq_status.has_pdf);
  const rfqReady = Boolean(projection.rfq_status.rfq_ready);

  return {
    caseId,
    requestType: projection.request_type || projection.case_summary.intent_goal || null,
    engineeringPath: projection.engineering_path || null,
    cockpit: mapCockpitView(projection),
    communication: projection.communication_context
      ? {
          conversationPhase: projection.communication_context.conversation_phase || null,
          turnGoal: projection.communication_context.turn_goal || null,
          primaryQuestion: projection.communication_context.primary_question || null,
          supportingReason: projection.communication_context.supporting_reason || null,
          responseMode: projection.communication_context.response_mode || null,
          confirmedFactsSummary: projection.communication_context.confirmed_facts_summary || [],
          openPointsSummary: projection.communication_context.open_points_summary || [],
        }
      : undefined,
    parameters: projection.parameters
      ? {
          medium: projection.parameters.medium ?? null,
          temperature_c: projection.parameters.temperature_c ?? null,
          pressure_bar: projection.parameters.pressure_bar ?? null,
          sealing_type: projection.parameters.sealing_type ?? null,
          pressure_direction: projection.parameters.pressure_direction ?? null,
          duty_profile: projection.parameters.duty_profile ?? null,
          shaft_diameter_mm: projection.parameters.shaft_diameter_mm ?? null,
          speed_rpm: projection.parameters.speed_rpm ?? null,
          installation: projection.parameters.installation ?? null,
          geometry_context: projection.parameters.geometry_context ?? null,
          contamination: projection.parameters.contamination ?? null,
          counterface_surface: projection.parameters.counterface_surface ?? null,
          tolerances: projection.parameters.tolerances ?? null,
          industry: projection.parameters.industry ?? null,
          compliance: projection.parameters.compliance ?? null,
          medium_qualifiers: projection.parameters.medium_qualifiers ?? null,
          motion_type: projection.parameters.motion_type ?? null,
        }
      : undefined,
    lifecycle: {
      currentStep: lifecycleSteps.find((step) => step.status === "active")?.label || null,
      completedSteps: lifecycleSteps.filter((step) => step.status === "done").map((step) => step.label),
      steps: lifecycleSteps,
    },
    summary: {
      turnCount: projection.case_summary.turn_count,
      maxTurns: projection.case_summary.max_turns,
      analysisCycleId: projection.cycle_info.current_assertion_cycle_id,
      stateRevision: projection.cycle_info.state_revision,
      assertedProfileRevision: projection.cycle_info.asserted_profile_revision,
      derivedArtifactsStale: projection.cycle_info.derived_artifacts_stale,
      staleReason: projection.cycle_info.stale_reason,
    },
    completeness: {
      coverageScore: projection.completeness.coverage_score,
      coveragePercent: Math.round(projection.completeness.coverage_score * 100),
      coverageGaps: projection.completeness.coverage_gaps,
      completenessDepth: projection.completeness.completeness_depth,
      missingCriticalParameters: projection.completeness.missing_critical_parameters,
      analysisComplete: projection.completeness.analysis_complete,
      recommendationReady: projection.completeness.recommendation_ready,
    },
    governance: {
      releaseStatus,
      releaseClass: releaseClassFromStatus(releaseStatus),
      scopeOfValidity: projection.governance_status.scope_of_validity,
      assumptions: projection.governance_status.assumptions_active,
      unknownsBlocking: projection.governance_status.unknowns_release_blocking,
      unknownsManufacturerValidation: projection.governance_status.unknowns_manufacturer_validation,
      gateFailures: projection.governance_status.gate_failures,
      notes: projection.governance_status.governance_notes,
      requiredDisclaimers: projection.governance_status.required_disclaimers,
      verificationPassed: projection.governance_status.verification_passed,
    },
    mediumCapture: {
      rawMentions: projection.medium_capture?.raw_mentions || [],
      primaryRawText: projection.medium_capture?.primary_raw_text || null,
      sourceTurnRef: projection.medium_capture?.source_turn_ref || null,
      sourceTurnIndex:
        typeof projection.medium_capture?.source_turn_index === "number"
          ? projection.medium_capture.source_turn_index
          : null,
    },
    mediumClassification: {
      canonicalLabel: projection.medium_classification?.canonical_label || null,
      family: projection.medium_classification?.family || "unknown",
      confidence: projection.medium_classification?.confidence || "low",
      status: projection.medium_classification?.status || "unavailable",
      normalizationSource: projection.medium_classification?.normalization_source || null,
      mappingConfidence: projection.medium_classification?.mapping_confidence || null,
      matchedAlias: projection.medium_classification?.matched_alias || null,
      sourceRegistryKey: projection.medium_classification?.source_registry_key || null,
      followupQuestion: projection.medium_classification?.followup_question || null,
    },
    mediumContext: {
      mediumLabel: projection.medium_context?.medium_label || null,
      status: projection.medium_context?.status || "unavailable",
      scope: projection.medium_context?.scope || "orientierend",
      summary: projection.medium_context?.summary || null,
      properties: projection.medium_context?.properties || [],
      challenges: projection.medium_context?.challenges || [],
      followupPoints: projection.medium_context?.followup_points || [],
      confidence: projection.medium_context?.confidence || null,
      sourceType: projection.medium_context?.source_type || null,
      notForReleaseDecisions:
        projection.medium_context?.not_for_release_decisions !== false,
      disclaimer: projection.medium_context?.disclaimer || null,
    },
    technicalDerivations: (projection.technical_derivations || []).map((item) => ({
      calcType: item.calc_type || "unknown",
      status: item.status || "insufficient_data",
      vSurfaceMPerS:
        typeof item.v_surface_m_s === "number" ? item.v_surface_m_s : null,
      pvValueMpaMPerS:
        typeof item.pv_value_mpa_m_s === "number" ? item.pv_value_mpa_m_s : null,
      dnValue: typeof item.dn_value === "number" ? item.dn_value : null,
      notes: item.notes || [],
    })),
    specificity: {
      materialSpecificityRequired: projection.specificity.material_specificity_required,
      completenessDepth: projection.specificity.completeness_depth,
      elevationPossible: Boolean(projection.specificity.elevation_possible),
      elevationTarget: projection.specificity.elevation_target || null,
      elevationHints: (projection.specificity.elevation_hints || []).map((hint) => ({
        label: hint.label,
        fieldKey: hint.field_key,
        reason: hint.reason,
        priority: hint.priority,
        actionType: hint.action_type,
      })),
    },
    candidates: {
      viable: projection.candidate_clusters.plausibly_viable,
      manufacturerValidationRequired: projection.candidate_clusters.manufacturer_validation_required,
      excluded: projection.candidate_clusters.inadmissible_or_excluded,
      total: projection.candidate_clusters.total_candidates,
    },
    conflicts: {
      total: projection.conflicts.total,
      open: projection.conflicts.open,
      resolved: projection.conflicts.resolved,
      bySeverity: projection.conflicts.by_severity,
      items: projection.conflicts.items.map((item) => ({
        conflictType: item.conflict_type,
        severity: item.severity,
        summary: item.summary,
        resolutionStatus: item.resolution_status,
      })),
    },
    claims: {
      total: projection.claims_summary.total,
      byType: projection.claims_summary.by_type,
      byOrigin: projection.claims_summary.by_origin,
      items: projection.claims_summary.items.map((item) => ({
        value: item.value,
        claimType: item.claim_type,
        claimOrigin: item.claim_origin,
      })),
    },
    evidence: {
      evidencePresent: Boolean(projection.evidence_summary?.evidence_present),
      evidenceCount: projection.evidence_summary?.evidence_count ?? 0,
      trustedSourcesPresent: Boolean(projection.evidence_summary?.trusted_sources_present),
      evidenceSupportedTopics: projection.evidence_summary?.evidence_supported_topics || [],
      sourceBackedFindings: projection.evidence_summary?.source_backed_findings || [],
      deterministicFindings: projection.evidence_summary?.deterministic_findings || [],
      assumptionBasedFindings: projection.evidence_summary?.assumption_based_findings || [],
      unresolvedOpenPoints: projection.evidence_summary?.unresolved_open_points || [],
      evidenceGaps: projection.evidence_summary?.evidence_gaps || [],
    },
    manufacturerQuestions: {
      mandatory: projection.manufacturer_questions.mandatory,
      openQuestions: projection.manufacturer_questions.open_questions.map((item) => ({
        id: item.id,
        question: item.question,
        reason: item.reason,
        priority: item.priority,
        category: item.category,
      })),
      totalOpen: projection.manufacturer_questions.total_open,
    },
    matching: {
      ready: projection.partner_matching.matching_ready,
      shortlistReady: Boolean(projection.partner_matching.shortlist_ready),
      inquiryReady: Boolean(projection.partner_matching.inquiry_ready),
      notReadyReasons: projection.partner_matching.not_ready_reasons,
      blockingReasons: projection.partner_matching.blocking_reasons || [],
      items: projection.partner_matching.material_fit_items.map((item) => ({
        material: item.material,
        cluster: item.cluster,
        specificity: item.specificity,
        requiresValidation: item.requires_validation,
        fitBasis: item.fit_basis,
        groundedFacts: (item.grounded_facts || []).map((fact) => ({
          name: fact.name,
          value: fact.value,
          unit: fact.unit,
          source: fact.source,
          sourceRank: fact.source_rank,
          groundingBasis: fact.grounding_basis,
          isDivergent: fact.is_divergent,
          variants: (fact.variants || []).map((variant) => ({
            value: variant.value,
            source: variant.source,
            sourceRank: variant.source_rank,
          })),
        })),
      })),
      openManufacturerQuestions: projection.partner_matching.open_manufacturer_questions,
      selectedPartnerId: projection.partner_matching.selected_partner_id || null,
      dataSource: projection.partner_matching.data_source,
    },
    rfq: {
      status: rfqReady ? "ready" : projection.rfq_package.has_draft ? "draft" : "unavailable",
      rfq_ready: rfqReady,
      releaseStatus,
      confirmed: projection.rfq_status.rfq_confirmed,
      blockers: projection.rfq_status.blockers,
      openPoints: projection.rfq_status.open_points,
      hasPdf: projection.rfq_status.has_pdf,
      hasHtmlReport: hasDocument,
      hasDraft: projection.rfq_package.has_draft,
      documentUrl: hasDocument ? buildRfqDocumentReadPath(caseId) : null,
      handoverReady: Boolean(projection.rfq_status.handover_ready),
      handoverInitiated: Boolean(projection.rfq_status.handover_initiated),
      package: {
        rfqId: projection.rfq_package.rfq_id,
        basisStatus: projection.rfq_package.rfq_basis_status,
        operatingContextRedacted: projection.rfq_package.operating_context_redacted,
        manufacturerQuestionsMandatory: projection.rfq_package.manufacturer_questions_mandatory,
        conflictsVisibleCount: projection.rfq_package.conflicts_visible_count,
        buyerAssumptionsAcknowledged: projection.rfq_package.buyer_assumptions_acknowledged,
      },
    },
  };
}
