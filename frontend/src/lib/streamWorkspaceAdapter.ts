import type { WorkspaceView } from "@/lib/contracts/workspace";
import type { StreamWorkspaceView } from "@/lib/streamWorkspace";

type WorkspaceParameterValue = string | number | string[] | null | undefined;
type WorkspaceParameters = NonNullable<WorkspaceView["parameters"]>;

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

function normalizeFieldName(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function streamParameters(streamWorkspace: StreamWorkspaceView): WorkspaceParameters {
  const parameters: Record<string, WorkspaceParameterValue> = {};

  for (const parameter of streamWorkspace.ui.parameter.parameters ?? []) {
    const fieldName = normalizeFieldName(parameter.field_name);
    if (!fieldName || !hasValue(parameter.value)) {
      continue;
    }
    parameters[fieldName] = parameter.value as WorkspaceParameterValue;
  }

  const pressureAlias =
    parameters.pressure_bar ??
    parameters.pressure_at_seal_bar ??
    parameters.pressure_delta_bar ??
    parameters.pressure_system_bar ??
    parameters.ambiguous_pressure_bar;
  if (hasValue(pressureAlias) && !hasValue(parameters.pressure_bar)) {
    parameters.pressure_bar = pressureAlias;
  }

  if (!hasValue(parameters.installation)) {
    parameters.installation =
      parameters.application_context ??
      parameters.application ??
      parameters.einbauort ??
      parameters.aggregate ??
      null;
  }

  if (!hasValue(parameters.sealing_material_family) && hasValue(parameters.material)) {
    parameters.sealing_material_family = parameters.material;
  }

  return parameters;
}

function lowerParameter(parameters: WorkspaceParameters, key: string): string {
  return String(parameters?.[key] ?? "").toLowerCase();
}

function engineeringPathFromStream(
  streamWorkspace: StreamWorkspaceView,
  parameters: WorkspaceParameters,
): string | null {
  const sealType = [
    lowerParameter(parameters, "sealing_type"),
    lowerParameter(parameters, "seal_type"),
    lowerParameter(parameters, "application"),
    String(streamWorkspace.ui.v92.seal_system?.seal_type ?? "").toLowerCase(),
    String(streamWorkspace.ui.v92.seal_system?.seal_family ?? "").toLowerCase(),
    String(streamWorkspace.ui.v92.engineering?.route ?? "").toLowerCase(),
  ].join(" ");

  if (sealType.includes("hyd")) return "hyd_pneu";
  if (sealType.includes("o-ring") || sealType.includes("oring")) return "static";
  if (sealType.includes("flansch") || sealType.includes("static")) return "static";
  if (sealType.includes("gleitring") || sealType.includes("pumpe")) return "ms_pump";
  if (sealType.includes("rwdr") || sealType.includes("radial") || sealType.includes("rot")) return "rwdr";
  return hasValue(parameters?.shaft_diameter_mm) ? "rwdr" : null;
}

function sealProfileFromStream(
  streamWorkspace: StreamWorkspaceView,
  parameters: WorkspaceParameters,
  engineeringPath: string | null,
): WorkspaceView["sealApplicationProfile"] {
  const sealFamily = String(streamWorkspace.ui.v92.seal_system?.seal_family ?? "").trim();
  const sealType =
    String(streamWorkspace.ui.v92.seal_system?.seal_type ?? "").trim() ||
    String(parameters?.sealing_type ?? "").trim() ||
    String(parameters?.seal_type ?? "").trim();

  return {
    sealFamily: sealFamily || engineeringPath || "unknown",
    sealType: sealType || "unknown",
    sealTypeConfidence: sealType || engineeringPath ? 0.7 : 0,
    confidenceBand: sealType || engineeringPath ? "candidate" : "unknown",
    matchedAlias: null,
    ambiguous: !sealType,
    candidateTypes: sealType ? [sealType] : [],
    applicationDomain: String(parameters?.installation ?? parameters?.application ?? "") || null,
    motionType: String(parameters?.motion_type ?? "") || null,
    standardRefs: [],
    typeSpecificMissingHints: streamWorkspace.ui.v92.seal_system?.missing_fields ?? [],
    notes: streamWorkspace.ui.v92.seal_system?.validity_boundaries ?? [],
    source: "stream_workspace_projection",
  };
}

function coverageFromParameters(parameters: WorkspaceParameters): number {
  const tracked = [
    "medium",
    "temperature_c",
    "pressure_bar",
    "sealing_type",
    "installation",
    "shaft_diameter_mm",
    "speed_rpm",
  ];
  const known = tracked.filter((key) => hasValue(parameters?.[key])).length;
  return tracked.length ? Math.round((known / tracked.length) * 100) / 100 : 0;
}

function rfqStatus(streamWorkspace: StreamWorkspaceView): WorkspaceView["rfq"]["status"] {
  if (streamWorkspace.ui.rfq.rfq_ready) return "ready";
  if (streamWorkspace.ui.rfq.status && streamWorkspace.ui.rfq.status !== "pending") return "draft";
  return "unavailable";
}

export function streamWorkspaceToWorkspaceView(
  streamWorkspace: StreamWorkspaceView | null,
): WorkspaceView | null {
  if (!streamWorkspace) {
    return null;
  }

  const parameters = streamParameters(streamWorkspace);
  const {
    assumption,
    compute,
    matching,
    medium_classification: mediumClassification,
    medium_context: mediumContext,
    parameter: parameterTile,
    recommendation,
    rfq,
    v92,
  } = streamWorkspace.ui;
  const engineeringPath = engineeringPathFromStream(streamWorkspace, parameters);
  const assumptionOpenPoints = assumption.open_points ?? [];
  const recommendationOpenPoints = recommendation.open_points ?? [];
  const engineeringBlockers = v92.engineering?.blockers ?? [];
  const validityNotes = recommendation.validity_notes ?? [];
  const assumptionItems = assumption.items ?? [];
  const matchingNotes = matching.notes ?? [];
  const rfqNotes = rfq.notes ?? [];
  const openPoints = [
    ...assumptionOpenPoints,
    ...recommendationOpenPoints,
    ...engineeringBlockers,
  ].filter((value, index, values) => value && values.indexOf(value) === index);
  const coverageScore = coverageFromParameters(parameters);

  return {
    caseId: streamWorkspace.caseId,
    caseType: "stream_projection",
    requestType: streamWorkspace.responseClass,
    engineeringPath,
    sealApplicationProfile: sealProfileFromStream(streamWorkspace, parameters, engineeringPath),
    designIntake: undefined,
    decisionUnderstanding: undefined,
    rfqReadinessProjection: streamWorkspace.rfqReadinessProjection,
    cockpit: null,
    communication: {
      conversationPhase: streamWorkspace.turnContext?.conversationPhase ?? null,
      turnGoal: streamWorkspace.turnContext?.turnGoal ?? null,
      primaryQuestion: streamWorkspace.turnContext?.primaryQuestion ?? null,
      supportingReason: streamWorkspace.turnContext?.supportingReason ?? null,
      responseMode: streamWorkspace.turnContext?.responseMode ?? null,
      confirmedFactsSummary: streamWorkspace.turnContext?.confirmedFactsSummary ?? [],
      openPointsSummary: streamWorkspace.turnContext?.openPointsSummary ?? [],
    },
    parameters,
    lifecycle: {
      currentStep: "stream_projection",
      completedSteps: [],
      steps: [],
    },
    summary: {
      turnCount: 0,
      maxTurns: 12,
      analysisCycleId: 0,
      stateRevision: 0,
      assertedProfileRevision: 0,
      derivedArtifactsStale: false,
      staleReason: null,
    },
    completeness: {
      coverageScore,
      coveragePercent: Math.round(coverageScore * 100),
      coverageGaps: openPoints,
      completenessDepth: parameterTile.needs_confirmation ? "candidate" : "stream",
      missingCriticalParameters: openPoints,
      analysisComplete: false,
      recommendationReady: Boolean(recommendation.rfq_admissible),
    },
    governance: {
      releaseStatus: recommendation.rfq_admissible
        ? "precheck_only"
        : "inadmissible",
      releaseClass: null,
      scopeOfValidity: validityNotes,
      assumptions: assumptionItems.map((item) => item.text ?? "").filter(Boolean),
      unknownsBlocking: openPoints,
      unknownsManufacturerValidation: recommendationOpenPoints,
      gateFailures: [],
      notes: [],
      requiredDisclaimers: validityNotes,
      verificationPassed: false,
    },
    mediumCapture: {
      rawMentions: mediumClassification.raw_mentions ?? [],
      primaryRawText: mediumClassification.primary_raw_text ?? null,
      sourceTurnRef: null,
      sourceTurnIndex: null,
    },
    mediumClassification: {
      canonicalLabel: mediumClassification.canonical_label ?? null,
      family: mediumClassification.family ?? "unknown",
      confidence: mediumClassification.confidence ?? "low",
      status: mediumClassification.status ?? "unavailable",
      normalizationSource: mediumClassification.normalization_source ?? null,
      mappingConfidence: mediumClassification.mapping_confidence ?? null,
      matchedAlias: mediumClassification.matched_alias ?? null,
      sourceRegistryKey: mediumClassification.source_registry_key ?? null,
      followupQuestion: mediumClassification.followup_question ?? null,
    },
    mediumContext: {
      mediumLabel: mediumContext.medium_label ?? null,
      status: mediumContext.status ?? "unavailable",
      scope: mediumContext.scope ?? "orientierend",
      summary: mediumContext.summary ?? null,
      properties: mediumContext.properties ?? [],
      challenges: mediumContext.challenges ?? [],
      followupPoints: mediumContext.followup_points ?? [],
      confidence: mediumContext.confidence ?? null,
      sourceType: mediumContext.source_type ?? null,
      notForReleaseDecisions: mediumContext.not_for_release_decisions ?? true,
      disclaimer: mediumContext.disclaimer ?? null,
    },
    v92Dashboard: streamWorkspace.v92Dashboard,
    technicalDerivations: (compute.items ?? []).map((item) => ({
      calcType: item.calc_type ?? "unknown",
      status: item.status ?? "insufficient_data",
      vSurfaceMPerS: numberOrNull(item.v_surface_m_s),
      pvValueMpaMPerS: numberOrNull(item.pv_value_mpa_m_s),
      dnValue: numberOrNull(item.dn_value),
      temperatureHeadroomC: null,
      pressureWindow: null,
      notes: item.notes ?? [],
    })),
    deepDiveTabs: [],
    specificity: {
      materialSpecificityRequired: "unknown",
      completenessDepth: parameterTile.needs_confirmation ? "candidate" : "stream",
      elevationPossible: false,
      elevationTarget: null,
      elevationHints: [],
    },
    candidates: {
      viable: [],
      manufacturerValidationRequired: [],
      excluded: [],
      total: 0,
    },
    conflicts: {
      total: 0,
      open: 0,
      resolved: 0,
      bySeverity: {},
      items: [],
    },
    claims: {
      total: 0,
      byType: {},
      byOrigin: {},
      items: [],
    },
    evidence: {
      evidencePresent: false,
      evidenceCount: 0,
      trustedSourcesPresent: false,
      evidenceSupportedTopics: [],
      sourceBackedFindings: [],
      deterministicFindings: [],
      assumptionBasedFindings: [],
      unresolvedOpenPoints: openPoints,
      evidenceGaps: openPoints,
    },
    manufacturerQuestions: {
      mandatory: matchingNotes,
      openQuestions: [],
      totalOpen: matchingNotes.length,
    },
    matching: {
      ready: matching.status !== "pending",
      shortlistReady: (matching.manufacturer_count ?? 0) > 0,
      inquiryReady: Boolean(rfq.rfq_ready),
      notReadyReasons: matchingNotes,
      blockingReasons: matchingNotes,
      items: [],
      openManufacturerQuestions: matchingNotes,
      selectedPartnerId: matching.selected_manufacturer ?? null,
      dataSource: "stream_workspace_projection",
    },
    rfq: {
      status: rfqStatus(streamWorkspace),
      rfq_ready: Boolean(rfq.rfq_ready),
      releaseStatus: rfq.rfq_admissible ? "precheck_only" : "inadmissible",
      confirmed: false,
      blockers: rfqNotes,
      openPoints,
      hasPdf: false,
      hasHtmlReport: false,
      hasDraft: false,
      documentUrl: null,
      handoverReady: Boolean(rfq.dispatch_ready),
      handoverInitiated: rfq.dispatch_status !== "pending",
      package: {
        rfqId: null,
        basisStatus: rfq.status ?? "pending",
        operatingContextRedacted: parameters ?? {},
        manufacturerQuestionsMandatory: matchingNotes,
        conflictsVisibleCount: 0,
        buyerAssumptionsAcknowledged: [],
      },
    },
  };
}
