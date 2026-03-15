export type RuntimeMeta = {
  interactionClass?: string | null;
  runtimePath?: string | null;
  bindingLevel?: string | null;
  hasCaseState?: boolean;
};

export type VisibleCaseNarrative = {
  governed_summary?: string;
  technical_direction?: PanelItem[];
  validity_envelope?: PanelItem[];
  next_best_inputs?: PanelItem[];
  suggested_next_questions?: PanelItem[];
  handover_status?: PanelItem | null;
  delta_status?: PanelItem | null;
  failure_analysis?: PanelItem[];
  case_summary?: PanelItem[];
  qualification_status?: PanelItem[];
};

export type PanelItem = {
  key: string;
  label: string;
  value: string;
  detail?: string | null;
  severity?: "low" | "medium" | "high";
};

export type StructuredCasePanelModel = {
  isStructured: boolean;
  title: string;
  subtitle: string;
  technicalDirection: PanelItem[];
  validityEnvelope: PanelItem[];
  caseSummary: PanelItem[];
  failureAnalysis: PanelItem[];
  nextBestInputs: PanelItem[];
  suggestedNextQuestions: PanelItem[];
  knownParameters: PanelItem[];
  derivedValues: PanelItem[];
  engineeringSignals: PanelItem[];
  qualificationStatus: PanelItem[];
  actionGate: {
    action: string;
    allowed: boolean;
    rfqReady: boolean;
    blockReasons: string[];
    summary: string;
  } | null;
  lastQualifiedAction: {
    action: string;
    lastStatus: string;
    executed: boolean;
    blockReasons: string[];
    timestamp: string;
    currentGateAllowsAction: boolean;
  } | null;
  qualifiedActionHistory: Array<{
    action: string;
    lastStatus: string;
    executed: boolean;
    blockReasons: string[];
    timestamp: string;
  }>;
};

type RawEntry = {
  value?: unknown;
  unit?: string | null;
  confirmed?: boolean;
  confidence?: number;
};

type DerivedEntry = {
  value?: unknown;
  unit?: string | null;
  formula_id?: string;
};

type SignalEntry = {
  value?: unknown;
  severity?: "low" | "medium" | "high";
  signal_class?: string;
};

type QualificationEntry = {
  status?: unknown;
  binding_level?: unknown;
  source_type?: unknown;
  source_ref?: unknown;
  details?: Record<string, unknown>;
};

type ResultContractEntry = {
  analysis_cycle_id?: unknown;
  state_revision?: unknown;
  binding_level?: unknown;
  release_status?: unknown;
  rfq_admissibility?: unknown;
  specificity_level?: unknown;
  scope_of_validity?: unknown;
  contract_obsolete?: unknown;
  invalidation_requires_recompute?: unknown;
  invalidation_reasons?: unknown;
  evidence_ref_count?: unknown;
  evidence_refs?: unknown[];
  source_ref?: unknown;
  qualified_action?: {
    summary?: unknown;
    allowed?: unknown;
    binding_level?: unknown;
  };
};

type CaseMetaEntry = {
  case_id?: unknown;
  analysis_cycle_id?: unknown;
  state_revision?: unknown;
  runtime_path?: unknown;
  binding_level?: unknown;
};

type AuditTrailEntry = {
  event_type?: unknown;
  timestamp?: unknown;
  source_ref?: unknown;
  details?: Record<string, unknown>;
};

type CaseStateLike = {
  active_domain?: string | null;
  case_meta?: CaseMetaEntry;
  raw_inputs?: Record<string, RawEntry>;
  derived_calculations?: Record<string, DerivedEntry>;
  engineering_signals?: Record<string, SignalEntry>;
  qualification_results?: Record<string, QualificationEntry>;
  result_contract?: ResultContractEntry;
  qualified_action_gate?: {
    action?: unknown;
    allowed?: unknown;
    rfq_ready?: unknown;
    binding_level?: unknown;
    block_reasons?: unknown[];
    summary?: unknown;
  };
  qualified_action_status?: {
    action?: unknown;
    last_status?: unknown;
    executed?: unknown;
    block_reasons?: unknown[];
    timestamp?: unknown;
    current_gate_allows_action?: unknown;
  };
  qualified_action_history?: Array<{
    action?: unknown;
    last_status?: unknown;
    executed?: unknown;
    block_reasons?: unknown[];
    timestamp?: unknown;
    current_gate_allows_action?: unknown;
  }>;
  readiness?: {
    ready_for_guidance?: boolean;
    ready_for_qualification?: boolean;
    missing_critical_inputs?: unknown[];
    missing_review_inputs?: unknown[];
  };
  evidence_trace?: {
    used_evidence_refs?: unknown[];
    used_source_fact_ids?: unknown[];
    evidence_ref_count?: unknown;
  };
  invalidation_state?: {
    requires_recompute?: unknown;
    stale_sections?: unknown[];
    recompute_reasons?: unknown[];
    recompute_completed?: unknown;
    material_input_revision?: unknown;
    provider_contract_revision?: unknown;
  };
  sealing_requirement_spec?: {
    contract_version?: unknown;
    rendering_status?: unknown;
    release_status?: unknown;
    rfq_admissibility?: unknown;
    binding_level?: unknown;
    source_ref?: unknown;
    render_artifact?: {
      artifact_type?: unknown;
      artifact_version?: unknown;
      filename?: unknown;
      mime_type?: unknown;
      source_ref?: unknown;
    };
  };
  audit_trail?: AuditTrailEntry[];
};

export function projectCaseStatePanel(
  caseState: CaseStateLike | null | undefined,
  runtimeMeta?: RuntimeMeta | null,
  visibleCaseNarrative?: VisibleCaseNarrative | null,
): StructuredCasePanelModel | null {
  if (!caseState) return null;

  const knownParameters = mapRawInputs(caseState.raw_inputs ?? {});
  const derivedValues = mapDerivedValues(caseState.derived_calculations ?? {});
  const engineeringSignalsState = caseState.engineering_signals ?? {};
  const engineeringSignals = mapEngineeringSignals(engineeringSignalsState);
  const visibleBindingLevel = resolveVisibleBindingLevel(caseState, runtimeMeta?.bindingLevel ?? null);
  const technicalDirection = visibleCaseNarrative?.technical_direction && visibleCaseNarrative.technical_direction.length > 0
    ? visibleCaseNarrative.technical_direction
    : mapTechnicalDirection(caseState, visibleBindingLevel);
  const validityEnvelope = visibleCaseNarrative?.validity_envelope && visibleCaseNarrative.validity_envelope.length > 0
    ? visibleCaseNarrative.validity_envelope
    : mapValidityEnvelope(caseState);
  const caseSummary = mapCaseSummary(caseState, visibleBindingLevel, visibleCaseNarrative);
  const failureAnalysis = visibleCaseNarrative?.failure_analysis && visibleCaseNarrative.failure_analysis.length > 0
    ? visibleCaseNarrative.failure_analysis
    : mapFailureAnalysis(
    engineeringSignalsState,
    caseState.qualification_results ?? {},
    caseState.readiness,
  );
  const nextBestInputs = visibleCaseNarrative?.next_best_inputs && visibleCaseNarrative.next_best_inputs.length > 0
    ? visibleCaseNarrative.next_best_inputs
    : mapNextBestInputs(
    caseState.readiness,
    caseState.result_contract,
    caseState.invalidation_state,
    caseState.qualified_action_status,
  );
  const suggestedNextQuestions = visibleCaseNarrative?.suggested_next_questions && visibleCaseNarrative.suggested_next_questions.length > 0
    ? visibleCaseNarrative.suggested_next_questions
    : mapSuggestedNextQuestions(
    caseState.readiness,
    caseState.invalidation_state,
  );
  const qualificationStatus = mapQualificationStatus(
    engineeringSignalsState,
    caseState.qualification_results ?? {},
    caseState.result_contract,
    caseState.readiness,
    caseState.invalidation_state,
    caseState.qualified_action_gate,
    caseState.audit_trail,
    visibleBindingLevel,
    visibleCaseNarrative,
  );
  const actionGate = mapQualifiedActionGate(caseState.qualified_action_gate);
  const lastQualifiedAction = mapQualifiedActionStatus(caseState.qualified_action_status);
  const qualifiedActionHistory = mapQualifiedActionHistory(caseState.qualified_action_history);

  return {
    isStructured: Boolean(runtimeMeta?.hasCaseState ?? true),
    title: "Structured Case",
    subtitle: [
      humanizeKey(caseState.active_domain ?? "unknown"),
      visibleBindingLevel ? `Binding: ${visibleBindingLevel}` : null,
    ]
      .filter(Boolean)
      .join(" · "),
    technicalDirection,
    validityEnvelope,
    caseSummary,
    failureAnalysis,
    nextBestInputs,
    suggestedNextQuestions,
    knownParameters,
    derivedValues,
    engineeringSignals,
    qualificationStatus,
    actionGate,
    lastQualifiedAction,
    qualifiedActionHistory,
  };
}

function mapValidityEnvelope(
  caseState: CaseStateLike,
): PanelItem[] {
  const resultContract = caseState.result_contract;
  const readiness = caseState.readiness;
  const invalidationState = caseState.invalidation_state;
  const governanceDetails = caseState.qualification_results?.["material_governance"]?.details ?? {};
  const scopeOfValidity = Array.isArray(resultContract?.scope_of_validity)
    ? resultContract.scope_of_validity.map(String)
    : [];
  const activeAssumptions = Array.isArray(governanceDetails["assumptions_active"])
    ? governanceDetails["assumptions_active"].map(String)
    : [];
  const gateFailures = Array.isArray(governanceDetails["gate_failures"])
    ? governanceDetails["gate_failures"].map(String)
    : [];
  const blockingUnknowns = Array.isArray(governanceDetails["unknowns_release_blocking"])
    ? governanceDetails["unknowns_release_blocking"].map(String)
    : Array.isArray(readiness?.missing_critical_inputs)
    ? readiness.missing_critical_inputs.map(String)
    : [];
  const contractObsolete = Boolean(resultContract?.contract_obsolete);
  const recomputeRequired = Boolean(resultContract?.invalidation_requires_recompute) || Boolean(invalidationState?.requires_recompute);
  const invalidationReasons = Array.isArray(resultContract?.invalidation_reasons)
    ? resultContract.invalidation_reasons.map(String)
    : Array.isArray(invalidationState?.recompute_reasons)
    ? invalidationState.recompute_reasons.map(String)
    : [];

  return [
    {
      key: "validity_scope",
      label: "Scope of Validity",
      value: scopeOfValidity.length > 0 ? `${scopeOfValidity.length} marker(s)` : "No explicit scope marker",
      detail: scopeOfValidity.length > 0 ? scopeOfValidity.join(", ") : "No explicit scope marker transported",
      severity: scopeOfValidity.length > 0 ? "low" : "medium",
    },
    {
      key: "validity_assumptions",
      label: "Active Assumptions",
      value: activeAssumptions.length > 0 ? `${activeAssumptions.length} active` : "None visible",
      detail: activeAssumptions.length > 0 ? activeAssumptions.join(", ") : "No active assumptions transported in the visible case",
      severity: activeAssumptions.length > 0 ? "medium" : "low",
    },
    {
      key: "validity_constraints",
      label: "Active Constraints",
      value: `${gateFailures.length} gate · ${blockingUnknowns.length} blocking`,
      detail: [
        gateFailures.length > 0 ? `Gate failures ${gateFailures.join(", ")}` : null,
        blockingUnknowns.length > 0 ? `Blocking unknowns ${blockingUnknowns.join(", ")}` : null,
      ].filter(Boolean).join(" · ") || "No active gate failure or blocking unknown visible",
      severity: gateFailures.length > 0 || blockingUnknowns.length > 0 ? "high" : "low",
    },
    {
      key: "validity_obsolescence",
      label: "Obsolescence & Recompute",
      value: recomputeRequired ? "Recompute required" : contractObsolete ? "Obsolete" : "Current",
      detail: [
        contractObsolete ? "Contract marked obsolete" : null,
        recomputeRequired ? "Qualification should not be relied on without recompute" : null,
        invalidationReasons.length > 0 ? `Reasons ${invalidationReasons.slice(0, 4).join(", ")}` : null,
      ].filter(Boolean).join(" · ") || "No active obsolescence or recompute requirement",
      severity: recomputeRequired || contractObsolete ? "high" : "low",
    },
  ];
}

function mapTechnicalDirection(
  caseState: CaseStateLike,
  bindingLevel: string | null,
): PanelItem[] {
  const qualificationLevel = resolveQualificationLevel(caseState.qualification_results ?? {});
  const rwdr = caseState.qualification_results?.["rwdr_preselection"];
  const selection = caseState.qualification_results?.["material_selection_projection"];
  const selectionDetails = selection?.details ?? {};
  const resultContract = caseState.result_contract;
  const readiness = caseState.readiness;
  const hardStops = collectQualificationStrings(caseState.qualification_results ?? {}, "hard_stop");
  const reviewFlags = collectQualificationLists(caseState.qualification_results ?? {}, "review_flags");
  const criticalInputs = Array.isArray(readiness?.missing_critical_inputs) ? readiness.missing_critical_inputs.map(String) : [];
  const reviewInputs = Array.isArray(readiness?.missing_review_inputs) ? readiness.missing_review_inputs.map(String) : [];
  const viableCandidateIds = Array.isArray(selectionDetails["viable_candidate_ids"])
    ? selectionDetails["viable_candidate_ids"].map(String)
    : [];
  const qualifiedCandidateIds = Array.isArray(selectionDetails["qualified_candidate_ids"])
    ? selectionDetails["qualified_candidate_ids"].map(String)
    : [];
  const winnerCandidateId = typeof selectionDetails["winner_candidate_id"] === "string"
    ? selectionDetails["winner_candidate_id"]
    : null;
  const typeClass = typeof rwdr?.details?.["type_class"] === "string" ? rwdr.details["type_class"] : null;
  const hasMaterialDirection = Boolean(winnerCandidateId) || viableCandidateIds.length > 0 || qualifiedCandidateIds.length > 0;
  const hasRwdrDirection = Boolean(typeClass);
  const basisType = hardStops.length > 0
    ? "blocked"
    : hasMaterialDirection && hasRwdrDirection
    ? "hybrid"
    : hasRwdrDirection
    ? "rwdr"
    : hasMaterialDirection
    ? "material"
    : "none";
  const confidenceScope = summarizeCommercialHandover(caseState, bindingLevel);

  let currentDirectionValue = "No active technical direction";
  let currentDirectionDetail: string | null = null;
  if (hardStops.length > 0) {
    currentDirectionValue = "Blocked";
    currentDirectionDetail = `Deterministic hard stop ${hardStops.join(", ")}`;
  } else if (winnerCandidateId && typeClass) {
    currentDirectionValue = winnerCandidateId;
    currentDirectionDetail = `Material path with RWDR ${humanizeKey(typeClass)}`;
  } else if (winnerCandidateId) {
    currentDirectionValue = winnerCandidateId;
    currentDirectionDetail = "Leading deterministic material candidate";
  } else if (typeClass) {
    currentDirectionValue = humanizeKey(typeClass);
    currentDirectionDetail = "RWDR type-class direction";
  } else if (qualifiedCandidateIds.length > 0 || viableCandidateIds.length > 0) {
    const candidateCount = qualifiedCandidateIds.length || viableCandidateIds.length;
    currentDirectionValue = `${candidateCount} shortlisted`;
    currentDirectionDetail = qualifiedCandidateIds.length > 0
      ? `Qualified candidates ${qualifiedCandidateIds.join(", ")}`
      : `Viable candidates ${viableCandidateIds.join(", ")}`;
  } else if (criticalInputs.length > 0) {
    currentDirectionValue = "Pending core inputs";
    currentDirectionDetail = `Missing ${criticalInputs.join(", ")}`;
  }

  return [
    {
      key: "technical_direction_current",
      label: "Current Direction",
      value: currentDirectionValue,
      detail: currentDirectionDetail,
      severity: hardStops.length > 0 || criticalInputs.length > 0 ? "high" : reviewFlags.length > 0 || reviewInputs.length > 0 ? "medium" : "low",
    },
    {
      key: "technical_direction_basis",
      label: "Direction Basis",
      value: humanizeKey(basisType),
      detail: [
        qualificationLevel ? `Qualification ${humanizeKey(qualificationLevel.status)}` : null,
        typeClass ? `RWDR ${typeClass}` : null,
        winnerCandidateId ? `Winner ${winnerCandidateId}` : null,
      ].filter(Boolean).join(" · ") || null,
      severity: basisType === "blocked" || basisType === "none" ? "high" : basisType === "hybrid" ? "medium" : "low",
    },
    {
      key: "technical_direction_binding",
      label: "Binding Scope",
      value: bindingLevel ?? "N/A",
      detail: [
        typeof resultContract?.rfq_admissibility === "string" ? `RFQ ${resultContract.rfq_admissibility}` : null,
        confidenceScope ? `Scope ${confidenceScope.value}` : null,
      ].filter(Boolean).join(" · ") || null,
      severity: typeof resultContract?.rfq_admissibility === "string" && resultContract.rfq_admissibility === "inadmissible"
        ? "high"
        : typeof resultContract?.rfq_admissibility === "string" && resultContract.rfq_admissibility === "provisional"
        ? "medium"
        : "low",
    },
    {
      key: "technical_direction_limits",
      label: "Limits & Reviews",
      value: hardStops.length > 0 ? `${hardStops.length} hard stop(s)` : `${reviewFlags.length + reviewInputs.length + criticalInputs.length} open item(s)`,
      detail: [
        hardStops.length > 0 ? `Hard stops ${hardStops.join(", ")}` : null,
        criticalInputs.length > 0 ? `Critical ${criticalInputs.join(", ")}` : null,
        reviewFlags.length > 0 ? `Review flags ${reviewFlags.join(", ")}` : null,
        reviewInputs.length > 0 ? `Review inputs ${reviewInputs.join(", ")}` : null,
      ].filter(Boolean).join(" · ") || "No active blocker or review item",
      severity: hardStops.length > 0 || criticalInputs.length > 0 ? "high" : reviewFlags.length > 0 || reviewInputs.length > 0 ? "medium" : "low",
    },
  ];
}

function mapCaseSummary(
  caseState: CaseStateLike,
  bindingLevel: string | null,
  visibleCaseNarrative?: VisibleCaseNarrative | null,
): PanelItem[] {
  if (visibleCaseNarrative?.case_summary && visibleCaseNarrative.case_summary.length > 0) {
    const summary = [...visibleCaseNarrative.case_summary];

    // Ensure delta_status is merged if present in narrative
    if (visibleCaseNarrative.delta_status) {
      const existingIdx = summary.findIndex(i => i.key === "what_if_delta" || i.key === "delta_impact");
      if (existingIdx >= 0) {
        summary[existingIdx] = visibleCaseNarrative.delta_status;
      } else {
        summary.push(visibleCaseNarrative.delta_status);
      }
    }

    // Ensure handover_status is merged if present in narrative
    if (visibleCaseNarrative.handover_status) {
      const existingIdx = summary.findIndex(i => i.key === "commercial_handover");
      if (existingIdx >= 0) {
        summary[existingIdx] = visibleCaseNarrative.handover_status;
      } else {
        summary.push(visibleCaseNarrative.handover_status);
      }
    }
    return summary;
  }

  const summary: PanelItem[] = [];
  const checkpoint = summarizeCheckpoint(caseState);
  if (checkpoint) {
    summary.push({
      key: "checkpoint",
      label: "Checkpoint",
      value: checkpoint.value,
      detail: checkpoint.detail,
    });
  }
  const resume = summarizeResumeReadiness(caseState);
  if (resume) {
    summary.push({
      key: "resume_readiness",
      label: "Resume Readiness",
      value: resume.value,
      detail: resume.detail,
      severity: resume.severity,
    });
  }
  const current = summarizeCurrentCase(caseState, bindingLevel);
  if (current) {
    summary.push({
      key: "current_case_summary",
      label: "Current Case Summary",
      value: current.value,
      detail: current.detail,
      severity: current.severity,
    });
  }
  const evidence = summarizeEvidenceBasis(caseState);
  if (evidence) {
    summary.push({
      key: "evidence_basis",
      label: "Evidence Basis",
      value: evidence.value,
      detail: evidence.detail,
      severity: evidence.severity,
    });
  }
  const sourceBinding = summarizeSourceBinding(caseState);
  if (sourceBinding) {
    summary.push({
      key: "source_binding",
      label: "Source Binding",
      value: sourceBinding.value,
      detail: sourceBinding.detail,
      severity: sourceBinding.severity,
    });
  }
  const whatIfDelta = visibleCaseNarrative?.delta_status ?? summarizeWhatIfDelta(caseState);
  if (whatIfDelta) {
    const deltaLabel = "label" in whatIfDelta && typeof whatIfDelta.label === "string"
      ? whatIfDelta.label
      : "What-If Delta";
    summary.push({
      key: "what_if_delta",
      label: deltaLabel,
      value: whatIfDelta.value,
      detail: whatIfDelta.detail,
      severity: whatIfDelta.severity,
    });
  }
  const auditTrailSummary = summarizeAuditTrailSummary(caseState);
  if (auditTrailSummary) {
    summary.push({
      key: "audit_trail_summary",
      label: "Audit Trail",
      value: auditTrailSummary.value,
      detail: auditTrailSummary.detail,
      severity: auditTrailSummary.severity,
    });
  }
  const exportSnapshot = summarizeExportSnapshot(caseState);
  if (exportSnapshot) {
    summary.push({
      key: "export_snapshot",
      label: "Technical Snapshot",
      value: exportSnapshot.value,
      detail: exportSnapshot.detail,
      severity: exportSnapshot.severity,
    });
  }
  const commercialHandover = visibleCaseNarrative?.handover_status ?? summarizeCommercialHandover(caseState, bindingLevel);
  if (commercialHandover) {
    const handoverLabel = "label" in commercialHandover && typeof commercialHandover.label === "string"
      ? commercialHandover.label
      : "Commercial Handover";
    summary.push({
      key: "commercial_handover",
      label: handoverLabel,
      value: commercialHandover.value,
      detail: commercialHandover.detail,
      severity: commercialHandover.severity,
    });
  }
  return summary;
}

function mapRawInputs(rawInputs: Record<string, RawEntry>): PanelItem[] {
  return Object.entries(rawInputs)
    .map(([key, entry]) => ({
      key,
      label: humanizeKey(key),
      value: formatValue(entry?.value, entry?.unit),
      detail: entry?.confirmed === false
        ? "Unconfirmed"
        : typeof entry?.confidence === "number"
        ? `Confidence ${Math.round(entry.confidence * 100)}%`
        : null,
    }))
    .filter(item => item.value !== "N/A")
    .sort((a, b) => a.label.localeCompare(b.label));
}

function mapDerivedValues(derivedCalculations: Record<string, DerivedEntry>): PanelItem[] {
  return Object.entries(derivedCalculations)
    .map(([key, entry]) => ({
      key,
      label: humanizeKey(key),
      value: formatValue(entry?.value, entry?.unit),
      detail: entry?.formula_id ? `Formula: ${entry.formula_id}` : null,
    }))
    .filter(item => item.value !== "N/A")
    .sort((a, b) => a.label.localeCompare(b.label));
}

function mapEngineeringSignals(engineeringSignals: Record<string, SignalEntry>): PanelItem[] {
  const items: PanelItem[] = Object.entries(engineeringSignals)
    .map(([key, entry]) => ({
      key,
      label: humanizeKey(key),
      value: formatSignalValue(entry?.value),
      detail: entry?.signal_class ? humanizeKey(entry.signal_class) : null,
      severity: entry?.severity ?? "low",
    }))
    .sort((a, b) => {
      const severityOrder = { high: 0, medium: 1, low: 2 };
      return (
        severityOrder[a.severity ?? "low"] - severityOrder[b.severity ?? "low"] ||
        a.label.localeCompare(b.label)
      );
    });
  const summaryItems = buildEngineeringSignalSummaryItems(engineeringSignals);
  if (summaryItems.length > 0) {
    items.unshift(...summaryItems.reverse());
  }
  return items;
}

function mapQualificationStatus(
  engineeringSignals: Record<string, SignalEntry>,
  qualificationResults: Record<string, QualificationEntry>,
  resultContract: CaseStateLike["result_contract"],
  readiness: CaseStateLike["readiness"],
  invalidationState: CaseStateLike["invalidation_state"],
  qualifiedActionGate: CaseStateLike["qualified_action_gate"],
  audit_trail: CaseStateLike["audit_trail"],
  bindingLevel: string | null,
  visibleCaseNarrative?: VisibleCaseNarrative | null,
  ): PanelItem[] {
  if (visibleCaseNarrative?.qualification_status && visibleCaseNarrative.qualification_status.length > 0) {
    // Backend is the SoT for fachliche qualification semantics.
    // Only technical renderers are added here — no fachnahe FE reconstruction.
    const items = [...visibleCaseNarrative.qualification_status];
    // Technical renderer: engineering signal summary (not available to backend narrative builder).
    const signalSummary = summarizeEngineeringSignalState(engineeringSignals);
    if (signalSummary) {
      items.unshift({
        key: "engineering_signal_summary",
        label: "Boundary & Contradiction Signals",
        value: signalSummary.value,
        detail: signalSummary.detail,
        severity: signalSummary.severity,
      });
    }
    // Technical renderer: binding level transport.
    if (bindingLevel) {
      items.unshift({
        key: "binding_level",
        label: "Binding Level",
        value: bindingLevel,
        detail: undefined,
      });
    }
    // Technical renderer: readiness status display.
    if (readiness) {
      items.push({
        key: "readiness_status",
        label: "Qualification Readiness",
        value: readiness.ready_for_qualification ? "Ready" : "Pending",
        detail: summarizeReadiness(readiness) ?? undefined,
      });
      // Technical renderer: missing review inputs (names not in readiness_status.detail).
      if (Array.isArray(readiness.missing_review_inputs) && readiness.missing_review_inputs.length > 0) {
        items.push({
          key: "missing_review_inputs",
          label: "Missing Review Inputs",
          value: String(readiness.missing_review_inputs.length),
          detail: readiness.missing_review_inputs.map(String).join(", "),
          severity: "medium" as const,
        });
      }
    }
    // Technical renderer: evidence provenance (count + refs from result_contract).
    if (typeof resultContract?.evidence_ref_count === "number" || Array.isArray(resultContract?.evidence_refs)) {
      const evidenceRefs = Array.isArray(resultContract?.evidence_refs) ? resultContract.evidence_refs.map(String) : [];
      const evidenceCount = typeof resultContract?.evidence_ref_count === "number"
        ? resultContract.evidence_ref_count
        : evidenceRefs.length;
      items.push({
        key: "qualification_evidence",
        label: "Qualification Evidence",
        value: String(evidenceCount),
        detail: [
          evidenceRefs.length > 0 ? `Refs ${evidenceRefs.join(", ")}` : "No explicit evidence refs",
          typeof resultContract?.source_ref === "string" ? `Contract ${resultContract.source_ref}` : null,
        ]
          .filter(Boolean)
          .join(" · "),
        severity: (evidenceCount > 0 ? "low" : "medium") as "low" | "medium" | "high",
      });
    }
    // Technical renderer: latest audit trail entry.
    const latestAuditItem = mapLatestAuditItem(audit_trail);
    if (latestAuditItem) items.push(latestAuditItem);
    return items;
  }

  const items: PanelItem[] = Object.entries(qualificationResults).map(([key, entry]) => ({

    key,
    label: humanizeKey(key),
    value: formatSignalValue(entry?.status),
    detail: [
      entry?.binding_level ? `Binding ${entry.binding_level}` : null,
      summarizeQualificationDetails(entry?.details),
    ]
      .filter(Boolean)
      .join(" · "),
  }));

  const qualificationSummaryItems = buildQualificationSummaryItems(
    engineeringSignals,
    qualificationResults,
    resultContract,
    readiness,
    invalidationState,
  );
  if (qualificationSummaryItems.length > 0) {
    items.unshift(...qualificationSummaryItems.reverse());
  }

  if (resultContract) {
    items.unshift({
      key: "result_contract",
      label: "Result Contract",
      value: typeof resultContract.release_status === "string" ? resultContract.release_status : "N/A",
      detail: summarizeResultContract(resultContract) ?? undefined,
    });
  }

  if (bindingLevel) {
    items.unshift({
      key: "binding_level",
      label: "Binding Level",
      value: bindingLevel,
      detail: undefined,
    });
  }
  if (readiness) {
    items.push({
      key: "readiness_status",
      label: "Qualification Readiness",
      value: readiness.ready_for_qualification ? "Ready" : "Pending",
      detail: summarizeReadiness(readiness) ?? undefined,
    });
    if (Array.isArray(readiness.missing_critical_inputs) && readiness.missing_critical_inputs.length > 0) {
      items.push({
        key: "missing_critical_inputs",
        label: "Missing Critical Inputs",
        value: String(readiness.missing_critical_inputs.length),
        detail: readiness.missing_critical_inputs.map(String).join(", "),
        severity: "high",
      });
    }
    if (Array.isArray(readiness.missing_review_inputs) && readiness.missing_review_inputs.length > 0) {
      items.push({
        key: "missing_review_inputs",
        label: "Missing Review Inputs",
        value: String(readiness.missing_review_inputs.length),
        detail: readiness.missing_review_inputs.map(String).join(", "),
        severity: "medium",
      });
    }
  }
  if (qualifiedActionGate) {
    items.push({
      key: "qualified_action_gate",
      label: "Qualified Action Gate",
      value: qualifiedActionGate.allowed ? "Enabled" : "Blocked",
      detail: [
        typeof qualifiedActionGate.summary === "string" ? qualifiedActionGate.summary : null,
        Array.isArray(qualifiedActionGate.block_reasons) && qualifiedActionGate.block_reasons.length > 0
          ? qualifiedActionGate.block_reasons.join(", ")
          : null,
      ]
        .filter(Boolean)
        .join(" · "),
    });
  }
  const latestAuditItem = mapLatestAuditItem(audit_trail);
  if (latestAuditItem) items.push(latestAuditItem);
  return items;}

function mapFailureAnalysis(
  engineeringSignals: Record<string, SignalEntry>,
  qualificationResults: Record<string, QualificationEntry>,
  readiness: CaseStateLike["readiness"],
): PanelItem[] {
  const items: PanelItem[] = [];
  const symptoms = collectFailureSymptoms(engineeringSignals, qualificationResults);
  const hypotheses = collectFailureHypotheses(engineeringSignals, qualificationResults);
  const hardStops = collectQualificationStrings(qualificationResults, "hard_stop");
  const reviewFlags = collectQualificationLists(qualificationResults, "review_flags");
  const missingCritical = Array.isArray(readiness?.missing_critical_inputs)
    ? readiness.missing_critical_inputs.map(String)
    : [];
  const missingReview = Array.isArray(readiness?.missing_review_inputs)
    ? readiness.missing_review_inputs.map(String)
    : [];

  items.push({
    key: "failure_mode",
    label: "Failure Analysis",
    value: hypotheses.length > 0 ? "Hypothesis active" : "No active hypothesis",
    detail: hypotheses.length > 0
      ? "Projection from current deterministic signals and review semantics. Not a confirmed root cause."
      : "No explicit failure hypothesis can be projected from the active case semantics.",
    severity: hypotheses.length > 0 ? "medium" : "low",
  });

  items.push({
    key: "failure_symptoms",
    label: "Visible Symptoms",
    value: String(symptoms.length),
    detail: symptoms.length > 0 ? symptoms.join(", ") : "None visible in active case",
    severity: symptoms.length > 0 ? "medium" : "low",
  });

  items.push({
    key: "failure_hypotheses",
    label: "Failure Hypotheses",
    value: String(hypotheses.length),
    detail: hypotheses.length > 0 ? hypotheses.join(", ") : "None projected",
    severity: hypotheses.length > 0 ? "medium" : "low",
  });

  items.push({
    key: "failure_confirmed_limits",
    label: "Confirmed Qualification Limits",
    value: hardStops.length > 0 ? `${hardStops.length} hard stop(s)` : reviewFlags.length > 0 ? `${reviewFlags.length} review case(s)` : "No active blocker",
    detail: [
      hardStops.length > 0 ? `Hard stops ${hardStops.join(", ")}` : null,
      reviewFlags.length > 0 ? `Review cases ${reviewFlags.join(", ")}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || "No deterministic blocker currently visible",
    severity: hardStops.length > 0 ? "high" : reviewFlags.length > 0 ? "medium" : "low",
  });

  items.push({
    key: "failure_open_unknowns",
    label: "Open Uncertainties",
    value: String(missingCritical.length + missingReview.length),
    detail: [
      missingCritical.length > 0 ? `Critical ${missingCritical.join(", ")}` : null,
      missingReview.length > 0 ? `Review ${missingReview.join(", ")}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || "No open uncertainty recorded",
    severity: missingCritical.length > 0 ? "high" : missingReview.length > 0 ? "medium" : "low",
  });

  return items;
}

function mapNextBestInputs(
  readiness: CaseStateLike["readiness"],
  resultContract: CaseStateLike["result_contract"],
  invalidationState: CaseStateLike["invalidation_state"],
  qualifiedActionStatus: CaseStateLike["qualified_action_status"],
): PanelItem[] {
  const critical = Array.isArray(readiness?.missing_critical_inputs)
    ? readiness.missing_critical_inputs.map(String)
    : [];
  const review = Array.isArray(readiness?.missing_review_inputs)
    ? readiness.missing_review_inputs.map(String)
    : [];
  const prioritized = prioritizeNextInputs(critical, review);
  const readyForQualification = Boolean(readiness?.ready_for_qualification);
  const requiresRecompute = Boolean(invalidationState?.requires_recompute);
  const rfqAdmissibility = typeof resultContract?.rfq_admissibility === "string"
    ? resultContract.rfq_admissibility
    : null;
  const lastActionStatus = typeof qualifiedActionStatus?.last_status === "string"
    ? qualifiedActionStatus.last_status
    : null;

  return [
    {
      key: "next_input_focus",
      label: "Next Best Inputs",
      value: prioritized.length > 0 ? `${prioritized.length} input(s)` : "No immediate input gap",
      detail: prioritized.length > 0
        ? prioritized.map(humanizeNextInput).join(", ")
        : requiresRecompute
        ? "No new input is missing, but stale sections should be recomputed before relying on the case."
        : readyForQualification
        ? "Qualification-ready from current visible inputs."
        : "No prioritized next input can be derived from the active case semantics.",
      severity: critical.length > 0 ? "high" : review.length > 0 ? "medium" : "low",
    },
    {
      key: "next_input_split",
      label: "Input Priority Split",
      value: `${critical.length} critical · ${review.length} review`,
      detail: [
        critical.length > 0 ? `Critical ${critical.slice(0, 3).map(humanizeNextInput).join(", ")}` : null,
        review.length > 0 ? `Review ${review.slice(0, 3).map(humanizeNextInput).join(", ")}` : null,
      ]
        .filter(Boolean)
        .join(" · ") || "No active missing-input split",
      severity: critical.length > 0 ? "high" : review.length > 0 ? "medium" : "low",
    },
    {
      key: "next_progress_step",
      label: "Next Step Impact",
      value: deriveNextStepValue(critical, review, requiresRecompute, readyForQualification),
      detail: [
        prioritized.length > 0 ? `Collect ${prioritized.map(humanizeNextInput).join(", ")}` : null,
        requiresRecompute ? "Case change currently affects qualification reliability" : null,
        rfqAdmissibility ? `RFQ ${rfqAdmissibility}` : null,
        lastActionStatus && lastActionStatus !== "none" ? `Last action ${lastActionStatus}` : null,
      ]
        .filter(Boolean)
        .join(" · ") || null,
      severity: critical.length > 0 || requiresRecompute ? "high" : review.length > 0 ? "medium" : "low",
    },
  ];
}

function mapSuggestedNextQuestions(
  readiness: CaseStateLike["readiness"],
  invalidationState: CaseStateLike["invalidation_state"],
): PanelItem[] {
  const critical = Array.isArray(readiness?.missing_critical_inputs)
    ? readiness.missing_critical_inputs.map(String)
    : [];
  const review = Array.isArray(readiness?.missing_review_inputs)
    ? readiness.missing_review_inputs.map(String)
    : [];
  const prioritized = prioritizeNextInputs(critical, review);
  const requiresRecompute = Boolean(invalidationState?.requires_recompute);
  const readyForQualification = Boolean(readiness?.ready_for_qualification);

  if (prioritized.length > 0) {
    return prioritized.map((value, index) => ({
      key: `suggested_question_${index + 1}`,
      label: `Question ${index + 1}`,
      value: critical.includes(value) ? "Critical input" : "Review input",
      detail: buildSuggestedQuestion(value, critical.includes(value)),
      severity: critical.includes(value) ? "high" : "medium",
    }));
  }

  if (requiresRecompute) {
    return [
      {
        key: "suggested_question_recompute",
        label: "Next Step",
        value: "Recompute required",
        detail: "No new question is needed right now. Recompute stale qualification sections before relying on the current case.",
        severity: "high",
      },
    ];
  }

  if (readyForQualification) {
    return [
      {
        key: "suggested_question_ready",
        label: "Next Step",
        value: "Qualification ready",
        detail: "No follow-up question is required from the current visible case. The next step is to proceed with qualification or review the result.",
        severity: "low",
      },
    ];
  }

  return [
    {
      key: "suggested_question_none",
      label: "Next Step",
      value: "No suggested question",
      detail: "No concrete follow-up question can be derived from the active case semantics.",
      severity: "low",
    },
  ];
}

function buildQualificationSummaryItems(
  engineeringSignals: Record<string, SignalEntry>,
  qualificationResults: Record<string, QualificationEntry>,
  resultContract: CaseStateLike["result_contract"],
  readiness: CaseStateLike["readiness"],
  invalidationState: CaseStateLike["invalidation_state"],
): PanelItem[] {
  const items: PanelItem[] = [];
  const signalSummary = summarizeEngineeringSignalState(engineeringSignals);
  if (signalSummary) {
    items.push({
      key: "engineering_signal_summary",
      label: "Boundary & Contradiction Signals",
      value: signalSummary.value,
      detail: signalSummary.detail,
      severity: signalSummary.severity,
    });
  }
  const qualificationLevel = resolveQualificationLevel(qualificationResults);
  if (qualificationLevel) {
    items.push({
      key: "qualification_level",
      label: "Qualification Level",
      value: humanizeKey(qualificationLevel.status),
      detail: [
        summarizeQualificationDetails(qualificationLevel.details),
        typeof qualificationLevel.source_ref === "string" ? `Source ${qualificationLevel.source_ref}` : null,
      ]
        .filter(Boolean)
        .join(" · "),
    });
  }
  if (typeof resultContract?.rfq_admissibility === "string") {
    items.push({
      key: "rfq_admissibility",
      label: "RFQ Admissibility",
      value: resultContract.rfq_admissibility,
      detail: summarizeRfqAdmissibility(resultContract),
      severity: resultContract.rfq_admissibility === "ready"
        ? "low"
        : resultContract.rfq_admissibility === "provisional"
        ? "medium"
        : "high",
    });
  }
  const hardStops = collectQualificationStrings(qualificationResults, "hard_stop");
  items.push({
    key: "hard_stops",
    label: "Hard Stops",
    value: hardStops.length > 0 ? String(hardStops.length) : "0",
    detail: hardStops.length > 0 ? hardStops.join(", ") : "None",
    severity: hardStops.length > 0 ? "high" : "low",
  });
  const reviewFlags = collectQualificationLists(qualificationResults, "review_flags");
  items.push({
    key: "review_cases",
    label: "Review Cases",
    value: reviewFlags.length > 0 ? String(reviewFlags.length) : "0",
    detail: reviewFlags.length > 0 ? reviewFlags.join(", ") : "None",
    severity: reviewFlags.length > 0 ? "medium" : "low",
  });
  const missingCriticalInputs = Array.isArray(readiness?.missing_critical_inputs)
    ? readiness.missing_critical_inputs.map(String)
    : [];
  items.push({
    key: "missing_critical_summary",
    label: "Missing Critical Data",
    value: String(missingCriticalInputs.length),
    detail: missingCriticalInputs.length > 0 ? missingCriticalInputs.join(", ") : "None",
    severity: missingCriticalInputs.length > 0 ? "high" : "low",
  });
  const deltaImpact = summarizeDeltaImpact(invalidationState, resultContract);
  if (deltaImpact) {
    items.push({
      key: "delta_impact",
      label: "Delta Impact",
      value: deltaImpact.value,
      detail: deltaImpact.detail,
      severity: deltaImpact.severity,
    });
  }
  if (typeof resultContract?.evidence_ref_count === "number" || Array.isArray(resultContract?.evidence_refs)) {
    const evidenceRefs = Array.isArray(resultContract?.evidence_refs) ? resultContract.evidence_refs.map(String) : [];
    const evidenceCount = typeof resultContract?.evidence_ref_count === "number"
      ? resultContract.evidence_ref_count
      : evidenceRefs.length;
    items.push({
      key: "qualification_evidence",
      label: "Qualification Evidence",
      value: String(evidenceCount),
      detail: [
        evidenceRefs.length > 0 ? `Refs ${evidenceRefs.join(", ")}` : "No explicit evidence refs",
        typeof resultContract?.source_ref === "string" ? `Contract ${resultContract.source_ref}` : null,
      ]
        .filter(Boolean)
        .join(" · "),
      severity: evidenceCount > 0 ? "low" : "medium",
    });
  }
  return items;
}

function buildEngineeringSignalSummaryItems(
  engineeringSignals: Record<string, SignalEntry>,
): PanelItem[] {
  const summary = summarizeEngineeringSignalState(engineeringSignals);
  if (!summary) return [];
  return [
    {
      key: "contradiction_summary",
      label: "Contradictions",
      value: String(summary.contradictions.length),
      detail: summary.contradictions.length > 0 ? summary.contradictions.join(", ") : "None",
      severity: summary.contradictions.length > 0 ? "high" : "low",
    },
    {
      key: "boundary_summary",
      label: "Boundary Cases",
      value: String(summary.boundaries.length),
      detail: summary.boundaries.length > 0 ? summary.boundaries.join(", ") : "None",
      severity: summary.boundaries.length > 0 ? summary.severity : "low",
    },
  ];
}

function mapLatestAuditItem(auditTrail: CaseStateLike["audit_trail"]): PanelItem | null {
  if (!Array.isArray(auditTrail) || auditTrail.length === 0) return null;
  const latest = auditTrail[auditTrail.length - 1];
  if (!latest) return null;
  return {
    key: "latest_audit",
    label: "Latest Audit",
    value: typeof latest.event_type === "string" ? humanizeKey(latest.event_type) : "Recorded",
    detail: [
      summarizeAuditDetails(latest.details),
      typeof latest.timestamp === "string" && latest.timestamp ? latest.timestamp : null,
      typeof latest.source_ref === "string" && latest.source_ref ? latest.source_ref : null,
    ]
      .filter(Boolean)
      .join(" · "),
  };
}

function resolveVisibleBindingLevel(
  caseState: CaseStateLike,
  runtimeBindingLevel: string | null,
): string | null {
  if (runtimeBindingLevel) return runtimeBindingLevel;
  if (typeof caseState.result_contract?.binding_level === "string") return caseState.result_contract.binding_level;
  if (typeof caseState.case_meta?.binding_level === "string") return caseState.case_meta.binding_level;
  if (typeof caseState.qualified_action_gate?.binding_level === "string") return caseState.qualified_action_gate.binding_level;
  return null;
}

function mapQualifiedActionGate(
  gate: CaseStateLike["qualified_action_gate"],
): StructuredCasePanelModel["actionGate"] {
  if (!gate) return null;
  return {
    action: typeof gate.action === "string" ? gate.action : "download_technical_rfq",
    allowed: Boolean(gate.allowed),
    rfqReady: Boolean(gate.rfq_ready),
    blockReasons: Array.isArray(gate.block_reasons) ? gate.block_reasons.map(String) : [],
    summary: typeof gate.summary === "string" ? gate.summary : (Boolean(gate.allowed) ? "qualified_action_enabled" : "qualified_action_blocked"),
  };
}

function mapQualifiedActionStatus(
  status: CaseStateLike["qualified_action_status"],
): StructuredCasePanelModel["lastQualifiedAction"] {
  if (!status) return null;
  return {
    action: typeof status.action === "string" ? status.action : "download_technical_rfq",
    lastStatus: typeof status.last_status === "string" ? status.last_status : "none",
    executed: Boolean(status.executed),
    blockReasons: Array.isArray(status.block_reasons) ? status.block_reasons.map(String) : [],
    timestamp: typeof status.timestamp === "string" ? status.timestamp : "",
    currentGateAllowsAction: Boolean(status.current_gate_allows_action),
  };
}

function mapQualifiedActionHistory(
  history: CaseStateLike["qualified_action_history"],
): StructuredCasePanelModel["qualifiedActionHistory"] {
  if (!Array.isArray(history)) return [];
  return history.map(item => ({
    action: typeof item?.action === "string" ? item.action : "download_technical_rfq",
    lastStatus: typeof item?.last_status === "string" ? item.last_status : "none",
    executed: Boolean(item?.executed),
    blockReasons: Array.isArray(item?.block_reasons) ? item.block_reasons.map(String) : [],
    timestamp: typeof item?.timestamp === "string" ? item.timestamp : "",
  }));
}

function summarizeQualificationDetails(details?: Record<string, unknown>): string | null {
  if (!details) return null;
  const parts: string[] = [];
  if (typeof details.type_class === "string") parts.push(`Type ${details.type_class}`);
  if (typeof details.hard_stop === "string") parts.push(`Hard stop ${details.hard_stop}`);
  if (typeof details.rfq_admissibility === "string") parts.push(`RFQ ${details.rfq_admissibility}`);
  if (typeof details.specificity_level === "string") parts.push(`Specificity ${details.specificity_level}`);
  if (Array.isArray(details.review_flags) && details.review_flags.length > 0) {
    parts.push(`Review ${details.review_flags.map(String).join(", ")}`);
  }
  if (Array.isArray(details.warnings) && details.warnings.length > 0) {
    parts.push(`${details.warnings.length} warning(s)`);
  }
  if (Array.isArray(details.missing_required_inputs) && details.missing_required_inputs.length > 0) {
    parts.push(`Missing ${details.missing_required_inputs.map(String).join(", ")}`);
  }
  if (Array.isArray(details.unknowns_release_blocking) && details.unknowns_release_blocking.length > 0) {
    parts.push(`Blocking ${details.unknowns_release_blocking.map(String).join(", ")}`);
  }
  if (Array.isArray(details.unknowns_manufacturer_validation) && details.unknowns_manufacturer_validation.length > 0) {
    parts.push(`Review ${details.unknowns_manufacturer_validation.map(String).join(", ")}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

function summarizeResultContract(contract: ResultContractEntry): string | null {
  const parts: string[] = [];
  if (typeof contract.binding_level === "string") parts.push(`Binding ${contract.binding_level}`);
  if (typeof contract.rfq_admissibility === "string") parts.push(`RFQ ${contract.rfq_admissibility}`);
  if (typeof contract.specificity_level === "string") parts.push(`Specificity ${contract.specificity_level}`);
  if (typeof contract.analysis_cycle_id === "string") parts.push(`Cycle ${contract.analysis_cycle_id}`);
  if (typeof contract.state_revision === "number") parts.push(`Revision ${contract.state_revision}`);
  if (Array.isArray(contract.scope_of_validity) && contract.scope_of_validity.length > 0) {
    parts.push(`Scope ${contract.scope_of_validity.join(", ")}`);
  }
  if (Boolean(contract.contract_obsolete) || Boolean(contract.invalidation_requires_recompute)) {
    parts.push("Invalidated");
  }
  if (typeof contract.qualified_action?.summary === "string") {
    parts.push(`Action ${contract.qualified_action.summary}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

function summarizeRfqAdmissibility(contract: ResultContractEntry): string | null {
  const parts: string[] = [];
  if (typeof contract.release_status === "string") parts.push(`Release ${contract.release_status}`);
  if (typeof contract.binding_level === "string") parts.push(`Binding ${contract.binding_level}`);
  if (Array.isArray(contract.scope_of_validity) && contract.scope_of_validity.length > 0) {
    parts.push(`Scope ${contract.scope_of_validity.join(", ")}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

function summarizeReadiness(readiness: NonNullable<CaseStateLike["readiness"]>): string | null {
  const parts: string[] = [];
  const critical = readiness.missing_critical_inputs?.length ?? 0;
  const review = readiness.missing_review_inputs?.length ?? 0;
  if (critical > 0) parts.push(`${critical} critical missing`);
  if (review > 0) parts.push(`${review} review missing`);
  if (parts.length === 0 && readiness.ready_for_guidance) parts.push("Structured case active");
  return parts.length > 0 ? parts.join(" · ") : null;
}

function summarizeAuditDetails(details?: Record<string, unknown>): string | null {
  if (!details) return null;
  const parts: string[] = [];
  if (typeof details.status === "string") parts.push(`Status ${details.status}`);
  if (typeof details.ready_for_qualification === "boolean") {
    parts.push(details.ready_for_qualification ? "Qualification ready" : "Qualification pending");
  }
  if (Array.isArray(details.missing_critical_inputs) && details.missing_critical_inputs.length > 0) {
    parts.push(`Critical ${details.missing_critical_inputs.map(String).join(", ")}`);
  }
  if (Array.isArray(details.missing_review_inputs) && details.missing_review_inputs.length > 0) {
    parts.push(`Review ${details.missing_review_inputs.map(String).join(", ")}`);
  }
  if (Array.isArray(details.block_reasons) && details.block_reasons.length > 0) {
    parts.push(`Blocked ${details.block_reasons.map(String).join(", ")}`);
  }
  if (typeof details.review_flag_count === "number" && details.review_flag_count > 0) {
    parts.push(`${details.review_flag_count} review flag(s)`);
  }
  if (Array.isArray(details.hard_stop_keys) && details.hard_stop_keys.length > 0) {
    parts.push(`Hard stop in ${details.hard_stop_keys.map(String).join(", ")}`);
  }
  if (Array.isArray(details.result_keys) && details.result_keys.length > 0) {
    parts.push(`Results ${details.result_keys.map(String).join(", ")}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

function summarizeCheckpoint(
  caseState: CaseStateLike,
): { value: string; detail: string | null } | null {
  const cycleId = typeof caseState.case_meta?.analysis_cycle_id === "string"
    ? caseState.case_meta.analysis_cycle_id
    : typeof caseState.result_contract?.analysis_cycle_id === "string"
    ? caseState.result_contract.analysis_cycle_id
    : null;
  const revision = typeof caseState.case_meta?.state_revision === "number"
    ? caseState.case_meta.state_revision
    : typeof caseState.result_contract?.state_revision === "number"
    ? caseState.result_contract.state_revision
    : null;
  if (!cycleId && revision === null) return null;
  const latestAudit = Array.isArray(caseState.audit_trail) && caseState.audit_trail.length > 0
    ? caseState.audit_trail[caseState.audit_trail.length - 1]
    : null;
  return {
    value: [cycleId ? `Cycle ${cycleId}` : null, revision !== null ? `Rev ${revision}` : null].filter(Boolean).join(" · "),
    detail: latestAudit
      ? [
          typeof latestAudit.event_type === "string" ? humanizeKey(latestAudit.event_type) : null,
          typeof latestAudit.timestamp === "string" ? latestAudit.timestamp : null,
        ].filter(Boolean).join(" · ")
      : null,
  };
}

function summarizeResumeReadiness(
  caseState: CaseStateLike,
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  const caseId = typeof caseState.case_meta?.case_id === "string" ? caseState.case_meta.case_id : null;
  const readiness = caseState.readiness;
  if (!caseId && !readiness) return null;
  const critical = Array.isArray(readiness?.missing_critical_inputs) ? readiness.missing_critical_inputs.map(String) : [];
  const review = Array.isArray(readiness?.missing_review_inputs) ? readiness.missing_review_inputs.map(String) : [];
  const lastStatus = typeof caseState.qualified_action_status?.last_status === "string"
    ? caseState.qualified_action_status.last_status
    : null;
  const resumable = Boolean(caseId) && Boolean(readiness?.ready_for_guidance);
  return {
    value: resumable ? "Resumable" : "Limited",
    detail: [
      caseId ? `Case ${caseId}` : null,
      critical.length > 0 ? `Critical ${critical.join(", ")}` : null,
      review.length > 0 ? `Review ${review.join(", ")}` : null,
      lastStatus && lastStatus !== "none" ? `Last action ${lastStatus}` : null,
    ].filter(Boolean).join(" · ") || null,
    severity: critical.length > 0 ? "high" : review.length > 0 ? "medium" : "low",
  };
}

function summarizeCurrentCase(
  caseState: CaseStateLike,
  bindingLevel: string | null,
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  const qualificationLevel = resolveQualificationLevel(caseState.qualification_results ?? {});
  const releaseStatus = typeof caseState.result_contract?.release_status === "string"
    ? caseState.result_contract.release_status
    : null;
  const readiness = caseState.readiness;
  const critical = Array.isArray(readiness?.missing_critical_inputs) ? readiness.missing_critical_inputs.length : 0;
  const review = Array.isArray(readiness?.missing_review_inputs) ? readiness.missing_review_inputs.length : 0;
  if (!qualificationLevel && !releaseStatus && !bindingLevel) return null;
  return {
    value: releaseStatus ?? humanizeKey(qualificationLevel?.status ?? "pending"),
    detail: [
      qualificationLevel ? `Qualification ${humanizeKey(qualificationLevel.status)}` : null,
      bindingLevel ? `Binding ${bindingLevel}` : null,
      typeof readiness?.ready_for_qualification === "boolean"
        ? readiness.ready_for_qualification ? "Qualification ready" : "Qualification pending"
        : null,
      critical > 0 ? `${critical} critical missing` : null,
      review > 0 ? `${review} review missing` : null,
    ].filter(Boolean).join(" · ") || null,
    severity: critical > 0 ? "high" : review > 0 ? "medium" : "low",
  };
}

function summarizeEvidenceBasis(
  caseState: CaseStateLike,
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  const trace = caseState.evidence_trace;
  const resultContract = caseState.result_contract;
  const evidenceRefs = Array.isArray(resultContract?.evidence_refs)
    ? resultContract.evidence_refs.map(String)
    : Array.isArray(trace?.used_evidence_refs)
    ? trace.used_evidence_refs.map(String)
    : [];
  const sourceFacts = Array.isArray(trace?.used_source_fact_ids) ? trace.used_source_fact_ids.map(String) : [];
  const count = typeof resultContract?.evidence_ref_count === "number"
    ? resultContract.evidence_ref_count
    : typeof trace?.evidence_ref_count === "number"
    ? trace.evidence_ref_count
    : evidenceRefs.length;
  if (count === 0 && sourceFacts.length === 0) return null;
  return {
    value: count > 0 ? `${count} evidence ref(s)` : `${sourceFacts.length} source fact(s)`,
    detail: [
      evidenceRefs.length > 0 ? `Evidence ${evidenceRefs.join(", ")}` : null,
      sourceFacts.length > 0 ? `Source facts ${sourceFacts.join(", ")}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || null,
    severity: count > 0 ? "low" : "medium",
  };
}

function summarizeSourceBinding(
  caseState: CaseStateLike,
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  const qualificationRefs = Object.values(caseState.qualification_results ?? {})
    .map(entry => typeof entry?.source_ref === "string" ? entry.source_ref : null)
    .filter((value): value is string => Boolean(value));
  const qualificationTypes = Object.values(caseState.qualification_results ?? {})
    .map(entry => typeof entry?.source_type === "string" ? entry.source_type : null)
    .filter((value): value is string => Boolean(value));
  const latestAuditRef = Array.isArray(caseState.audit_trail) && caseState.audit_trail.length > 0
    ? caseState.audit_trail[caseState.audit_trail.length - 1]?.source_ref
    : null;
  const refs = Array.from(new Set([
    typeof caseState.result_contract?.source_ref === "string" ? caseState.result_contract.source_ref : null,
    ...qualificationRefs,
    typeof latestAuditRef === "string" ? latestAuditRef : null,
  ].filter(Boolean)));
  if (refs.length === 0 && qualificationTypes.length === 0) return null;
  return {
    value: refs.length > 0 ? `${refs.length} bound source(s)` : `${qualificationTypes.length} deterministic source(s)`,
    detail: [
      qualificationTypes.length > 0 ? `Types ${Array.from(new Set(qualificationTypes)).join(", ")}` : null,
      refs.length > 0 ? `Refs ${refs.slice(0, 4).join(", ")}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || null,
    severity: refs.length > 0 ? "low" : "medium",
  };
}

function summarizeWhatIfDelta(
  caseState: CaseStateLike,
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  const invalidation = caseState.invalidation_state;
  if (!invalidation) return null;
  const reasons = Array.isArray(invalidation.recompute_reasons) ? invalidation.recompute_reasons.map(String) : [];
  const staleSections = Array.isArray(invalidation.stale_sections) ? invalidation.stale_sections.map(String) : [];
  const requiresRecompute = Boolean(invalidation.requires_recompute);
  const recomputeCompleted = Boolean(invalidation.recompute_completed);
  if (!requiresRecompute && !recomputeCompleted && reasons.length === 0) return null;
  return {
    value: requiresRecompute ? "Impact Detected" : recomputeCompleted ? "Recomputed" : "Updated",
    detail: [
      typeof invalidation.material_input_revision === "number" ? `Input rev ${invalidation.material_input_revision}` : null,
      typeof invalidation.provider_contract_revision === "number" ? `Provider rev ${invalidation.provider_contract_revision}` : null,
      reasons.length > 0 ? `Changed ${reasons.slice(0, 4).map(humanizeDeltaReason).join(", ")}` : null,
      staleSections.length > 0 ? `Affected ${staleSections.slice(0, 4).map(humanizeDeltaSection).join(", ")}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || null,
    severity: requiresRecompute ? "high" : recomputeCompleted ? "medium" : "low",
  };
}

function summarizeDeltaImpact(
  invalidationState: CaseStateLike["invalidation_state"],
  resultContract: CaseStateLike["result_contract"],
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  if (!invalidationState) return null;
  const staleSections = Array.isArray(invalidationState.stale_sections) ? invalidationState.stale_sections.map(String) : [];
  const reasons = Array.isArray(invalidationState.recompute_reasons) ? invalidationState.recompute_reasons.map(String) : [];
  const requiresRecompute = Boolean(invalidationState.requires_recompute) || Boolean(resultContract?.invalidation_requires_recompute);
  const recomputeCompleted = Boolean(invalidationState.recompute_completed);
  if (!requiresRecompute && !recomputeCompleted && staleSections.length === 0 && reasons.length === 0) return null;
  return {
    value: requiresRecompute ? "Qualification affected" : recomputeCompleted ? "Qualification refreshed" : "Case changed",
    detail: [
      staleSections.length > 0 ? `Affected ${staleSections.slice(0, 4).map(humanizeDeltaSection).join(", ")}` : null,
      reasons.length > 0 ? `Why ${reasons.slice(0, 4).map(humanizeDeltaReason).join(", ")}` : null,
      requiresRecompute ? "Recompute required before relying on stale sections" : null,
    ]
      .filter(Boolean)
      .join(" · ") || null,
    severity: requiresRecompute ? "high" : recomputeCompleted ? "medium" : "low",
  };
}

function summarizeAuditTrailSummary(
  caseState: CaseStateLike,
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  const trail = caseState.audit_trail;
  if (!Array.isArray(trail) || trail.length === 0) return null;
  const latest = trail[trail.length - 1];
  const first = trail[0];
  return {
    value: `${trail.length} event(s)`,
    detail: [
      latest?.event_type ? `Latest ${humanizeKey(String(latest.event_type))}` : null,
      latest?.timestamp ? String(latest.timestamp) : null,
      first?.event_type ? `Started ${humanizeKey(String(first.event_type))}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || null,
    severity: "low",
  };
}

function summarizeExportSnapshot(
  caseState: CaseStateLike,
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  const spec = caseState.sealing_requirement_spec;
  const artifact = spec?.render_artifact;
  if (!spec && !artifact) return null;
  const hasArtifact = Boolean(artifact && typeof artifact.filename === "string" && artifact.filename);
  return {
    value: hasArtifact ? "Exportable snapshot" : "Structured snapshot",
    detail: [
      typeof artifact?.filename === "string" ? artifact.filename : null,
      typeof artifact?.artifact_version === "string" ? artifact.artifact_version : null,
      typeof spec?.rendering_status === "string" ? `Render ${spec.rendering_status}` : null,
      typeof spec?.binding_level === "string" ? `Binding ${spec.binding_level}` : null,
      typeof spec?.rfq_admissibility === "string" ? `RFQ ${spec.rfq_admissibility}` : null,
      typeof artifact?.source_ref === "string"
        ? `Artifact ${artifact.source_ref}`
        : typeof spec?.source_ref === "string"
        ? `Contract ${spec.source_ref}`
        : null,
    ]
      .filter(Boolean)
      .join(" · ") || null,
    severity: hasArtifact ? "low" : "medium",
  };
}

function summarizeCommercialHandover(
  caseState: CaseStateLike,
  bindingLevel: string | null,
): { value: string; detail: string | null; severity: "low" | "medium" | "high" } | null {
  const contract = caseState.result_contract;
  const gate = caseState.qualified_action_gate;
  const spec = caseState.sealing_requirement_spec;
  const visibleBinding = bindingLevel
    ?? (typeof contract?.binding_level === "string" ? contract.binding_level : null)
    ?? (typeof gate?.binding_level === "string" ? gate.binding_level : null);
  const releaseStatus = typeof contract?.release_status === "string" ? contract.release_status : null;
  const rfqAdmissibility = typeof contract?.rfq_admissibility === "string" ? contract.rfq_admissibility : null;
  const hasSnapshot = Boolean(spec?.render_artifact && typeof spec.render_artifact.filename === "string" && spec.render_artifact.filename);
  const handoverReady = Boolean(gate?.allowed) && Boolean(gate?.rfq_ready) && visibleBinding === "RFQ_BASIS";
  if (!visibleBinding && !releaseStatus && !rfqAdmissibility && !gate && !spec) return null;

  let value = "Guidance only";
  let severity: "low" | "medium" | "high" = "high";
  if (handoverReady && hasSnapshot) {
    value = "Handover ready";
    severity = "low";
  } else if (rfqAdmissibility === "ready" || visibleBinding === "RFQ_BASIS") {
    value = "RFQ ready";
    severity = "low";
  } else if (visibleBinding === "QUALIFIED_PRESELECTION") {
    value = "Prequalified";
    severity = "medium";
  } else if (visibleBinding === "ORIENTATION" || visibleBinding === "CALCULATION") {
    value = "Orientation only";
    severity = "medium";
  }

  return {
    value,
    detail: [
      visibleBinding ? `Binding ${visibleBinding}` : null,
      releaseStatus ? `Release ${releaseStatus}` : null,
      rfqAdmissibility ? `RFQ ${rfqAdmissibility}` : null,
      gate ? `Gate ${gate.allowed ? "enabled" : "blocked"}` : null,
      hasSnapshot ? "Technical snapshot available" : null,
    ]
      .filter(Boolean)
      .join(" · ") || null,
    severity,
  };
}

function humanizeDeltaReason(value: string): string {
  return humanizeKey(value.replace(/:/g, " "));
}

function humanizeDeltaSection(value: string): string {
  return value
    .split(".")
    .map(part => humanizeKey(part))
    .join(" / ");
}

function summarizeEngineeringSignalState(
  engineeringSignals: Record<string, SignalEntry>,
): {
  value: string;
  detail: string;
  severity: "low" | "medium" | "high";
  contradictions: string[];
  boundaries: string[];
} | null {
  const contradictions: string[] = [];
  const boundaries: string[] = [];

  for (const [key, entry] of Object.entries(engineeringSignals)) {
    const signalClass = typeof entry?.signal_class === "string" ? entry.signal_class : "";
    const value = typeof entry?.value === "string" ? entry.value : entry?.value;
    const severity = entry?.severity ?? "low";

    if (key.includes("conflict") || signalClass === "conflict_count") {
      contradictions.push(
        typeof value === "number" ? `${humanizeKey(key)} ${value}` : humanizeKey(key),
      );
      continue;
    }

    const isBoundarySignal = signalClass === "threshold_warning"
      || signalClass === "risk_level"
      || signalClass === "fit_status"
      || key.includes("limit")
      || key.includes("boundary")
      || key.includes("high")
      || (severity === "high" && signalClass !== "gate");
    if (!isBoundarySignal) continue;

    boundaries.push(
      typeof value === "number" || typeof value === "string"
        ? `${humanizeKey(key)}: ${formatSignalValue(value)}`
        : humanizeKey(key),
    );
  }

  if (contradictions.length === 0 && boundaries.length === 0) return null;
  const severity = contradictions.length > 0 ? "high" : "medium";
  const parts: string[] = [];
  if (contradictions.length > 0) parts.push(`${contradictions.length} contradiction(s)`);
  if (boundaries.length > 0) parts.push(`${boundaries.length} boundary signal(s)`);
  return {
    value: parts.join(" · "),
    detail: [
      contradictions.length > 0 ? `Contradictions ${contradictions.join(", ")}` : null,
      boundaries.length > 0 ? `Boundary ${boundaries.join(", ")}` : null,
    ]
      .filter(Boolean)
      .join(" · "),
    severity,
    contradictions,
    boundaries,
  };
}

function resolveQualificationLevel(
  qualificationResults: Record<string, QualificationEntry>,
): { status: string; details?: Record<string, unknown>; source_ref?: string } | null {
  const preferredKeys = ["material_core", "rwdr_preselection", "material_governance", "material_selection_projection"];
  for (const key of preferredKeys) {
    const entry = qualificationResults[key];
    if (typeof entry?.status === "string") {
      return {
        status: entry.status,
        details: entry.details,
        source_ref: typeof entry.source_ref === "string" ? entry.source_ref : undefined,
      };
    }
  }
  for (const entry of Object.values(qualificationResults)) {
    if (typeof entry?.status === "string") {
      return {
        status: entry.status,
        details: entry.details,
        source_ref: typeof entry.source_ref === "string" ? entry.source_ref : undefined,
      };
    }
  }
  return null;
}

function collectQualificationStrings(
  qualificationResults: Record<string, QualificationEntry>,
  key: string,
): string[] {
  const values = Object.values(qualificationResults)
    .map(entry => entry?.details?.[key])
    .filter((value): value is string => typeof value === "string" && value.length > 0);
  return Array.from(new Set(values));
}

function collectQualificationLists(
  qualificationResults: Record<string, QualificationEntry>,
  key: string,
): string[] {
  const values = Object.values(qualificationResults).flatMap(entry => {
    const raw = entry?.details?.[key];
    return Array.isArray(raw) ? raw.map(String) : [];
  });
  return Array.from(new Set(values.filter(Boolean)));
}

function collectFailureSymptoms(
  engineeringSignals: Record<string, SignalEntry>,
  qualificationResults: Record<string, QualificationEntry>,
): string[] {
  const symptoms: string[] = [];

  for (const [key, entry] of Object.entries(engineeringSignals)) {
    const signalClass = typeof entry?.signal_class === "string" ? entry.signal_class : "";
    const severity = entry?.severity ?? "low";
    if (signalClass === "conflict_count" || severity === "low") continue;
    symptoms.push(
      typeof entry?.value === "string" || typeof entry?.value === "number"
        ? `${humanizeKey(key)}: ${formatSignalValue(entry.value)}`
        : humanizeKey(key),
    );
  }

  const warnings = collectQualificationLists(qualificationResults, "warnings");
  for (const warning of warnings) symptoms.push(humanizeKey(warning));

  return Array.from(new Set(symptoms));
}

function collectFailureHypotheses(
  engineeringSignals: Record<string, SignalEntry>,
  qualificationResults: Record<string, QualificationEntry>,
): string[] {
  const reviewFlags = collectQualificationLists(qualificationResults, "review_flags");
  const warnings = collectQualificationLists(qualificationResults, "warnings");
  const hardStops = collectQualificationStrings(qualificationResults, "hard_stop");
  const hypotheses: string[] = [];

  const hasPressureRisk = hasSignalValue(engineeringSignals, "rwdr_pressure_risk_level", ["high", "critical"]);
  const hasTribologyRisk = hasSignalValue(engineeringSignals, "rwdr_tribology_risk_level", ["high", "critical"]);
  const hasMaterialRisk = typeof engineeringSignals.material_risk_warning?.value === "string";
  const hasSurfaceSpeedHigh = Object.prototype.hasOwnProperty.call(engineeringSignals, "surface_speed_high");

  if (hasPressureRisk || reviewFlags.includes("review_water_with_pressure")) {
    hypotheses.push("Leakage hypothesis from pressure or water burden");
  }
  if (reviewFlags.includes("review_dry_run_high_speed")) {
    hypotheses.push("Dry-run hypothesis from deterministic RWDR review trigger");
  }
  if (hasMaterialRisk) {
    hypotheses.push("Chemical damage hypothesis remains open and requires evidence validation");
  }
  if (warnings.includes("installation_path_damage_risk")) {
    hypotheses.push("Mounting error hypothesis from installation damage risk");
  }
  if (hasTribologyRisk || hasSurfaceSpeedHigh) {
    hypotheses.push("Wear pattern hypothesis from tribology or speed boundary");
  }
  if (hardStops.length > 0) {
    hypotheses.push("Deterministic hard stop indicates functional unsuitability, not confirmed root cause");
  }

  return Array.from(new Set(hypotheses));
}

function prioritizeNextInputs(
  critical: string[],
  review: string[],
): string[] {
  const ordered = [...critical, ...review]
    .filter(Boolean)
    .filter((value, index, list) => list.indexOf(value) === index);
  return ordered.slice(0, 3);
}

function buildSuggestedQuestion(value: string, critical: boolean): string {
  const prefix = critical ? "Please confirm" : "Please add if available";
  const field = humanizeNextInput(value);
  switch (value) {
    case "pressure_bar":
      return `${prefix} the operating pressure in bar.`;
    case "temperature_c":
      return `${prefix} the operating temperature in °C.`;
    case "medium":
      return `${prefix} the medium or fluid at the sealing interface.`;
    case "shaft_diameter_mm":
      return `${prefix} the shaft diameter in mm.`;
    case "available_width_mm":
      return `${prefix} the available installation width in mm.`;
    case "technical_inputs_not_confirmed":
      return "Please confirm the current technical operating inputs before continuing.";
    default:
      return `${prefix} ${field.toLowerCase()}.`;
  }
}

function humanizeNextInput(value: string): string {
  if (value === "technical_inputs_not_confirmed") {
    return "Technical inputs not confirmed";
  }
  return humanizeKey(value);
}

function deriveNextStepValue(
  critical: string[],
  review: string[],
  requiresRecompute: boolean,
  readyForQualification: boolean,
): string {
  if (critical.length > 0) return "Ask critical inputs first";
  if (review.length > 0) return "Resolve review inputs";
  if (requiresRecompute) return "Recompute affected sections";
  if (readyForQualification) return "Advance qualification";
  return "Structured case active";
}

function hasSignalValue(
  engineeringSignals: Record<string, SignalEntry>,
  key: string,
  acceptedValues: string[],
): boolean {
  const raw = engineeringSignals[key]?.value;
  return typeof raw === "string" && acceptedValues.includes(raw);
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\bmm\b/gi, "mm")
    .replace(/\bmps\b/gi, "m/s")
    .replace(/\bpv\b/gi, "PV")
    .replace(/\brfq\b/gi, "RFQ")
    .replace(/\bptfe\b/gi, "PTFE")
    .replace(/\brwdr\b/gi, "RWDR")
    .replace(/\b\w/g, char => char.toUpperCase());
}

function formatValue(value: unknown, unit?: string | null): string {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "number") {
    const numeric = Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/\.?0+$/, "");
    return unit ? `${numeric} ${unit}` : numeric;
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return unit ? `${String(value)} ${unit}` : String(value);
}

function formatSignalValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "boolean") return value ? "Active" : "Inactive";
  return String(value);
}
