import type {
  WorkspaceCompletenessScore,
  WorkspaceCurrentStateAnalysis,
  WorkspaceDecisionUnderstanding,
  WorkspaceLifecycleStep,
  WorkspaceNeedsAnalysis,
  WorkspaceNextBestQuestion,
  WorkspaceSealApplicationProfile,
  WorkspaceView,
} from "@/lib/contracts/workspace";
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

type RawRiskEvaluationResult = {
  risk_name?: string;
  score?: number;
  label?: string;
  drivers?: string[];
  missing_inputs?: string[];
  rule_ids?: string[];
  explanation_short?: string;
  confidence?: string;
  ruleset_version?: string;
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
  risk_evaluations?: RawRiskEvaluationResult[];
  missing_mandatory_keys?: string[];
  blockers?: string[];
  readiness?: {
    status?: string | null;
    is_rfq_ready?: boolean;
    release_status?: string | null;
    coverage_score?: number | null;
    readiness_level?: number | null;
    readiness_label?: string | null;
    missing_required_fields?: string[];
    blocking_unknowns?: string[];
    recommended_next_question?: string | null;
    rfq_possible?: boolean;
    risk_score_max?: number | null;
    risk_label_max?: string | null;
    ruleset_version?: string | null;
  } | null;
};

type RawDeepDiveTab = {
  tab_id?: string;
  label?: string;
  status?: string;
  detected?: string[];
  relevance?: string;
  opportunities?: string[];
  risks?: string[];
  derived_direction?: string;
  missing?: string[];
  next_action?: string | null;
  return_to_analysis?: string;
  cards?: Array<{
    title?: string;
    body?: string;
    items?: string[];
  }>;
};

type RawNeedsAnalysis = {
  primary_need?: string;
  secondary_needs?: string[];
  urgency?: string;
  user_side?: string | null;
  context_side?: string | null;
  confidence?: number;
  notes?: string[];
};

type RawCurrentStateAnalysis = {
  known_fields?: string[];
  missing_fields?: string[];
  uncertain_fields?: string[];
  conflicting_fields?: string[];
  evidence_backed_fields?: string[];
  seal_type_status?: string;
  readiness_hint?: string;
  confidence?: number;
};

type RawNextBestQuestion = {
  question?: string;
  reason?: string;
  focus_key?: string;
  priority?: number;
  expected_answer_type?: string;
  applies_to_case_type?: string;
  applies_to_seal_type?: string;
  source?: string;
  max_questions_policy?: string;
};

type RawCompletenessScore = {
  score?: number;
  missing_critical_count?: number;
  known_critical_count?: number;
  uncertainty_count?: number;
  conflict_count?: number;
  notes?: string[];
};

type RawDecisionUnderstanding = {
  case_summary?: string;
  understood_now?: string[];
  technical_meaning?: string[];
  plausible_directions?: string[];
  not_yet_decidable?: string[];
  key_risks?: string[];
  confidence_notes?: string[];
  next_best_question?: string | null;
  manufacturer_review_needs?: string[];
  needs_analysis?: RawNeedsAnalysis;
  current_state_analysis?: RawCurrentStateAnalysis;
  next_best_questions?: RawNextBestQuestion[];
  completeness_score?: RawCompletenessScore;
};

type RawSealApplicationProfile = {
  seal_family?: string;
  seal_type?: string;
  seal_type_confidence?: number;
  confidence_band?: string;
  matched_alias?: string | null;
  ambiguous?: boolean;
  candidate_types?: string[];
  application_domain?: string | null;
  motion_type?: string | null;
  standard_refs?: string[];
  type_specific_missing_hints?: string[];
  notes?: string[];
  source?: string;
};

type LegacyWorkspaceProjection = {
  case_type?: string | null;
  request_type?: string | null;
  engineering_path?: string | null;
  seal_application_profile?: RawSealApplicationProfile | null;
  decision_understanding?: RawDecisionUnderstanding | null;
  needs_analysis?: RawNeedsAnalysis | null;
  current_state_analysis?: RawCurrentStateAnalysis | null;
  next_best_questions?: RawNextBestQuestion[];
  completeness_score?: RawCompletenessScore | null;
  cockpit_view?: RawCockpitView | null;
  deep_dive_tabs?: RawDeepDiveTab[];
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
    validation_status?: string | null;
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
    label: "RFQ-Preview",
    status: rfq_package.has_draft ? "done" : "pending",
    detail: rfq_package.has_draft ? rfq_status.release_status.replace(/_/g, " ") : undefined,
    iconName: "FileText",
  });

  steps.push({
    label: "Export vorbereiten",
    status: rfq_status.has_html_report ? "done" : rfq_package.has_draft ? "active" : "pending",
    detail: rfq_status.has_pdf ? "PDF available" : rfq_status.has_html_report ? "HTML report" : undefined,
    iconName: "FileDown",
  });

  steps.push({
    label: "Herstellerpruefung erforderlich",
    status: partner_matching.matching_ready ? "active" : "pending",
    detail: partner_matching.material_fit_items.length > 0
      ? `${partner_matching.material_fit_items.length} candidate${partner_matching.material_fit_items.length === 1 ? "" : "s"}`
      : undefined,
    iconName: "Factory",
  });

  if (rfq_status.handover_initiated) {
    steps.push({
      label: "Export vorbereitet",
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
    application_function: emptyCockpitSection("application_function", "1. Anlage & Funktion"),
    medium_environment: emptyCockpitSection("medium_environment", "2. Medium & Umgebung"),
    operating_geometry: emptyCockpitSection("operating_geometry", "3. Betriebsdaten & Geometrie"),
    risk_readiness: emptyCockpitSection("risk_readiness", "4. Risiken & Anfrage-Reife"),
  };
}

const LEGACY_SECTION_ID_MAP: Record<string, EngineeringSectionId> = {
  core_intake: "application_function",
  failure_drivers: "medium_environment",
  geometry_fit: "operating_geometry",
  rfq_liability: "risk_readiness",
};

function normalizeSectionId(id: string | null | undefined): EngineeringSectionId | null {
  if (id === "application_function" || id === "medium_environment" || id === "operating_geometry" || id === "risk_readiness") {
    return id;
  }
  return id ? LEGACY_SECTION_ID_MAP[id] ?? null : null;
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

function mapRiskEvaluations(rawRisks: RawRiskEvaluationResult[] | undefined): EngineeringCockpitView["riskEvaluations"] {
  return (rawRisks || []).map((risk) => ({
    riskName: risk.risk_name || "unknown",
    score: typeof risk.score === "number" ? risk.score : 9,
    label: risk.label || "unknown",
    drivers: risk.drivers || [],
    missingInputs: risk.missing_inputs || [],
    ruleIds: risk.rule_ids || [],
    explanationShort: risk.explanation_short || "",
    confidence: risk.confidence || "medium",
    rulesetVersion: risk.ruleset_version || "",
  }));
}


function mapDeepDiveTabs(rawTabs: RawDeepDiveTab[] | undefined) {
  return (rawTabs || [])
    .filter((tab) =>
      tab.tab_id === "analysis" ||
      tab.tab_id === "medium" ||
      tab.tab_id === "material" ||
      tab.tab_id === "seal_type",
    )
    .map((tab) => ({
      tabId: tab.tab_id as "analysis" | "medium" | "material" | "seal_type",
      label: tab.label || tab.tab_id || "",
      status: tab.status || "available",
      detected: tab.detected || [],
      relevance: tab.relevance || "",
      opportunities: tab.opportunities || [],
      risks: tab.risks || [],
      derivedDirection: tab.derived_direction || "",
      missing: tab.missing || [],
      nextAction: tab.next_action ?? null,
      returnToAnalysis: tab.return_to_analysis || "Zurueck zur Analyse",
      cards: (tab.cards || []).map((card) => ({
        title: card.title || "",
        body: card.body || "",
        items: card.items || [],
      })),
    }));
}

function mapNeedsAnalysis(raw: RawNeedsAnalysis | null | undefined): WorkspaceNeedsAnalysis {
  return {
    primaryNeed: raw?.primary_need || "unknown",
    secondaryNeeds: raw?.secondary_needs || [],
    urgency: raw?.urgency || "unknown",
    userSide: raw?.user_side || null,
    contextSide: raw?.context_side || null,
    confidence: typeof raw?.confidence === "number" ? raw.confidence : 0,
    notes: raw?.notes || [],
  };
}

function mapCurrentStateAnalysis(raw: RawCurrentStateAnalysis | null | undefined): WorkspaceCurrentStateAnalysis {
  return {
    knownFields: raw?.known_fields || [],
    missingFields: raw?.missing_fields || [],
    uncertainFields: raw?.uncertain_fields || [],
    conflictingFields: raw?.conflicting_fields || [],
    evidenceBackedFields: raw?.evidence_backed_fields || [],
    sealTypeStatus: raw?.seal_type_status || "unknown",
    readinessHint: raw?.readiness_hint || "precheck",
    confidence: typeof raw?.confidence === "number" ? raw.confidence : 0,
  };
}

function mapNextBestQuestion(raw: RawNextBestQuestion): WorkspaceNextBestQuestion {
  return {
    question: raw.question || "",
    reason: raw.reason || "",
    focusKey: raw.focus_key || "",
    priority: typeof raw.priority === "number" ? raw.priority : 1,
    expectedAnswerType: raw.expected_answer_type || "text",
    appliesToCaseType: raw.applies_to_case_type || "unknown",
    appliesToSealType: raw.applies_to_seal_type || "unknown_seal",
    source: raw.source || "next_best_question_service",
    maxQuestionsPolicy: raw.max_questions_policy || "ask_1_to_3_targeted_questions",
  };
}

function mapCompletenessScore(raw: RawCompletenessScore | null | undefined): WorkspaceCompletenessScore {
  return {
    score: typeof raw?.score === "number" ? raw.score : 0,
    missingCriticalCount: raw?.missing_critical_count ?? 0,
    knownCriticalCount: raw?.known_critical_count ?? 0,
    uncertaintyCount: raw?.uncertainty_count ?? 0,
    conflictCount: raw?.conflict_count ?? 0,
    notes: raw?.notes || [],
  };
}

function mapDecisionUnderstanding(projection: LegacyWorkspaceProjection): WorkspaceDecisionUnderstanding {
  const raw = projection.decision_understanding || {};
  return {
    caseSummary: raw.case_summary || "",
    understoodNow: raw.understood_now || [],
    technicalMeaning: raw.technical_meaning || [],
    plausibleDirections: raw.plausible_directions || [],
    notYetDecidable: raw.not_yet_decidable || [],
    keyRisks: raw.key_risks || [],
    confidenceNotes: raw.confidence_notes || [],
    nextBestQuestion: raw.next_best_question || null,
    manufacturerReviewNeeds: raw.manufacturer_review_needs || [],
    needsAnalysis: mapNeedsAnalysis(raw.needs_analysis || projection.needs_analysis),
    currentStateAnalysis: mapCurrentStateAnalysis(raw.current_state_analysis || projection.current_state_analysis),
    nextBestQuestions: (raw.next_best_questions || projection.next_best_questions || []).map(mapNextBestQuestion),
    completenessScore: mapCompletenessScore(raw.completeness_score || projection.completeness_score),
  };
}

function mapSealApplicationProfile(raw: RawSealApplicationProfile | null | undefined): WorkspaceSealApplicationProfile {
  return {
    sealFamily: raw?.seal_family || "unknown",
    sealType: raw?.seal_type || "unknown_seal",
    sealTypeConfidence: typeof raw?.seal_type_confidence === "number" ? raw.seal_type_confidence : 0,
    confidenceBand: raw?.confidence_band || "low",
    matchedAlias: raw?.matched_alias || null,
    ambiguous: Boolean(raw?.ambiguous),
    candidateTypes: raw?.candidate_types || [],
    applicationDomain: raw?.application_domain || null,
    motionType: raw?.motion_type || null,
    standardRefs: raw?.standard_refs || [],
    typeSpecificMissingHints: raw?.type_specific_missing_hints || [],
    notes: raw?.notes || [],
    source: raw?.source || "seal_type_normalizer",
  };
}

function mapCockpitView(projection: LegacyWorkspaceProjection): EngineeringCockpitView | null {
  const raw = projection.cockpit_view;
  if (!raw) {
    return null;
  }

  const sections = defaultCockpitSections();
  for (const section of raw.sections || []) {
    const id = normalizeSectionId(section.section_id);
    if (!id) {
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
    riskEvaluations: mapRiskEvaluations(raw.risk_evaluations),
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
      readinessLevel: raw.readiness?.readiness_level ?? undefined,
      readinessLabel: raw.readiness?.readiness_label ?? undefined,
      missingRequiredFields: raw.readiness?.missing_required_fields || [],
      blockingUnknowns: raw.readiness?.blocking_unknowns || [],
      recommendedNextQuestion: raw.readiness?.recommended_next_question ?? null,
      rfqPossible: raw.readiness?.rfq_possible ?? undefined,
      riskScoreMax: raw.readiness?.risk_score_max ?? undefined,
      riskLabelMax: raw.readiness?.risk_label_max ?? undefined,
      rulesetVersion: raw.readiness?.ruleset_version ?? undefined,
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
    caseType: projection.case_type || null,
    requestType: projection.request_type || projection.case_summary.intent_goal || null,
    engineeringPath: projection.engineering_path || null,
    sealApplicationProfile: mapSealApplicationProfile(projection.seal_application_profile),
    decisionUnderstanding: mapDecisionUnderstanding(projection),
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
      validationStatus: projection.medium_context?.validation_status || null,
      notForReleaseDecisions:
        projection.medium_context?.not_for_release_decisions !== false,
      disclaimer: projection.medium_context?.disclaimer || null,
    },
    deepDiveTabs: mapDeepDiveTabs(projection.deep_dive_tabs),
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
