import type { EngineeringCockpitView } from "@/lib/engineering/cockpitModel";

export type WorkspaceLifecycleStep = {
  label: string;
  status: "done" | "active" | "pending";
  detail?: string;
  iconName: string;
};

export type WorkspaceElevationHint = {
  label: string;
  fieldKey: string | null;
  reason: string;
  priority: number;
  actionType: string;
};

export type WorkspaceCandidate = Record<string, unknown>;

export type WorkspaceConflict = {
  conflictType: string;
  severity: string;
  summary: string;
  resolutionStatus: string;
};

export type WorkspaceClaim = {
  value: string | null;
  claimType: string;
  claimOrigin: string;
};

export type WorkspaceEvidenceSummary = {
  evidencePresent: boolean;
  evidenceCount: number;
  trustedSourcesPresent: boolean;
  evidenceSupportedTopics: string[];
  sourceBackedFindings: string[];
  deterministicFindings: string[];
  assumptionBasedFindings: string[];
  unresolvedOpenPoints: string[];
  evidenceGaps: string[];
};

export type WorkspaceManufacturerQuestion = {
  id: string;
  question: string;
  reason: string;
  priority: string;
  category: string;
};

export type WorkspaceFactVariant = {
  value: string;
  source: string;
  sourceRank: number;
};

export type WorkspaceGroundedFact = {
  name: string;
  value: string;
  unit: string | null;
  source: string;
  sourceRank: number;
  groundingBasis: string;
  isDivergent: boolean;
  variants: WorkspaceFactVariant[];
};

export type WorkspaceTechnicalDerivation = {
  calcType: string;
  status: string;
  vSurfaceMPerS: number | null;
  pvValueMpaMPerS: number | null;
  dnValue: number | null;
  temperatureHeadroomC: number | null;
  pressureWindow?: string | null;
  notes: string[];
};

export type WorkspaceMatchItem = {
  material: string;
  cluster: string;
  specificity: string;
  requiresValidation: boolean;
  fitBasis: string;
  groundedFacts: WorkspaceGroundedFact[];
};

export type WorkspaceManufacturerFitRow = {
  manufacturerId: string;
  fitScore: number | null;
  verificationLevel: string;
  fitReasons: string[];
  gaps: string[];
  missingRequirements: string[];
  sourceClaimIds: string[];
};

export type WorkspaceManufacturerFitMatrix = {
  status: string;
  disclosure: string;
  rows: WorkspaceManufacturerFitRow[];
  noSuitablePartnerReason: string | null;
  eligiblePartnerCount: number;
};


export type WorkspaceDeepDiveTabId = "analysis" | "medium" | "material" | "seal_type";

export type WorkspaceDeepDiveCard = {
  title: string;
  body: string;
  items: string[];
};

export type WorkspaceDeepDiveTab = {
  tabId: WorkspaceDeepDiveTabId;
  label: string;
  status: string;
  detected: string[];
  relevance: string;
  opportunities: string[];
  risks: string[];
  derivedDirection: string;
  missing: string[];
  nextAction: string | null;
  returnToAnalysis: string;
  cards: WorkspaceDeepDiveCard[];
};

export type WorkspaceNeedsAnalysis = {
  primaryNeed: string;
  secondaryNeeds: string[];
  urgency: string;
  userSide: string | null;
  contextSide: string | null;
  confidence: number;
  notes: string[];
};

export type WorkspaceCurrentStateAnalysis = {
  knownFields: string[];
  missingFields: string[];
  uncertainFields: string[];
  conflictingFields: string[];
  evidenceBackedFields: string[];
  sealTypeStatus: string;
  readinessHint: string;
  confidence: number;
};

export type WorkspaceNextBestQuestion = {
  question: string;
  reason: string;
  focusKey: string;
  priority: number;
  expectedAnswerType: string;
  appliesToCaseType: string;
  appliesToSealType: string;
  source: string;
  maxQuestionsPolicy: string;
};

export type WorkspaceCompletenessScore = {
  score: number;
  missingCriticalCount: number;
  knownCriticalCount: number;
  uncertaintyCount: number;
  conflictCount: number;
  notes: string[];
};

export type WorkspaceDecisionUnderstanding = {
  caseSummary: string;
  understoodNow: string[];
  technicalMeaning: string[];
  plausibleDirections: string[];
  notYetDecidable: string[];
  keyRisks: string[];
  confidenceNotes: string[];
  nextBestQuestion: string | null;
  manufacturerReviewNeeds: string[];
  needsAnalysis: WorkspaceNeedsAnalysis;
  currentStateAnalysis: WorkspaceCurrentStateAnalysis;
  nextBestQuestions: WorkspaceNextBestQuestion[];
  completenessScore: WorkspaceCompletenessScore;
};

export type WorkspaceSealApplicationProfile = {
  sealFamily: string;
  sealType: string;
  sealTypeConfidence: number;
  confidenceBand: string;
  matchedAlias: string | null;
  ambiguous: boolean;
  candidateTypes: string[];
  applicationDomain: string | null;
  motionType: string | null;
  standardRefs: string[];
  typeSpecificMissingHints: string[];
  notes: string[];
  source: string;
};

export type WorkspaceDesignFieldStatus = {
  key: string;
  label: string;
  status: string;
  criticality: string;
  value: unknown;
  reason: string;
};

export type WorkspaceDesignScreeningCheck = {
  checkId: string;
  label: string;
  status: string;
  value: number | null;
  unit: string | null;
  inputs: string[];
  message: string;
};

export type WorkspaceDesignEscalationTrigger = {
  triggerId: string;
  label: string;
  severity: string;
  reason: string;
};

export type WorkspaceSealDesignIntake = {
  schemaVersion: string;
  status: string;
  knownFields: WorkspaceDesignFieldStatus[];
  missingFields: WorkspaceDesignFieldStatus[];
  screeningChecks: WorkspaceDesignScreeningCheck[];
  escalationTriggers: WorkspaceDesignEscalationTrigger[];
  nextRequiredFields: string[];
  boundaryNotice: string;
  eventNames: string[];
};

export type WorkspaceRfqPendingQuestion = {
  question_text: string;
  target_field?: string | null;
  label?: string | null;
  reason?: string | null;
  required_for_rfq?: boolean;
  expected_answer_type?: string | null;
  source?: string | null;
  status?: string | null;
};

export type WorkspaceRfqReadinessProjection = {
  manufacturer_review_ready: boolean;
  rfq_basis_ready: boolean;
  known_missing_fields: string[];
  open_points: string[];
  blocking_reasons: string[];
  pending_question: WorkspaceRfqPendingQuestion | null;
  consent_required: boolean;
  dispatch_allowed: boolean;
  external_contact_allowed: boolean;
  final_approval_claim_allowed: boolean;
  preview_available: boolean;
  preview_possible: boolean;
  preview_action_available: boolean;
  preview_action_name: string | null;
  preview_endpoint: string | null;
  preview_creation_requires_explicit_user_intent: boolean;
  preview_export_requires_consent: boolean;
  preview_requires_explicit_endpoint: boolean;
  preview_service_boundary: string | null;
  projection_version: string | null;
};

export type WorkspaceView = {
  caseId: string;
  caseType?: string | null;
  requestType?: string | null;
  engineeringPath?: string | null;
  sealApplicationProfile?: WorkspaceSealApplicationProfile;
  designIntake?: WorkspaceSealDesignIntake;
  decisionUnderstanding?: WorkspaceDecisionUnderstanding;
  rfqReadinessProjection?: WorkspaceRfqReadinessProjection | null;
  cockpit?: EngineeringCockpitView | null;
  communication?: {
    conversationPhase?: string | null;
    turnGoal?: string | null;
    primaryQuestion?: string | null;
    supportingReason?: string | null;
    responseMode?: string | null;
    confirmedFactsSummary?: string[];
    openPointsSummary?: string[];
  };
  parameters?: {
    [key: string]: string | number | string[] | null | undefined;
    medium?: string | null;
    temperature_c?: number | string | null;
    pressure_bar?: number | string | null;
    sealing_type?: string | null;
    pressure_direction?: string | null;
    duty_profile?: string | null;
    shaft_diameter_mm?: number | string | null;
    speed_rpm?: number | string | null;
    installation?: string | null;
    geometry_context?: string | null;
    contamination?: string | string[] | null;
    counterface_surface?: string | null;
    tolerances?: string | null;
    industry?: string | null;
    compliance?: string | string[] | null;
    medium_qualifiers?: string | string[] | null;
    motion_type?: string | null;
  };
  lifecycle: {
    currentStep: string | null;
    completedSteps: string[];
    steps: WorkspaceLifecycleStep[];
  };
  summary: {
    turnCount: number;
    maxTurns: number;
    analysisCycleId: number;
    stateRevision: number;
    assertedProfileRevision: number;
    derivedArtifactsStale: boolean;
    staleReason: string | null;
  };
  completeness: {
    coverageScore: number;
    coveragePercent: number;
    coverageGaps: string[];
    completenessDepth: string;
    missingCriticalParameters: string[];
    analysisComplete: boolean;
    recommendationReady: boolean;
  };
  governance: {
    releaseStatus: string;
    releaseClass: "A" | "B" | "C" | "D" | null;
    scopeOfValidity: string[];
    assumptions: string[];
    unknownsBlocking: string[];
    unknownsManufacturerValidation: string[];
    gateFailures: string[];
    notes: string[];
    requiredDisclaimers: string[];
    verificationPassed: boolean;
  };
  mediumCapture: {
    rawMentions: string[];
    primaryRawText: string | null;
    sourceTurnRef: string | null;
    sourceTurnIndex: number | null;
  };
  mediumClassification: {
    canonicalLabel: string | null;
    family: string;
    confidence: string;
    status: string;
    normalizationSource: string | null;
    mappingConfidence: string | null;
    matchedAlias: string | null;
    sourceRegistryKey: string | null;
    followupQuestion: string | null;
  };
  mediumContext: {
    mediumLabel: string | null;
    status: string;
    scope: string;
    summary: string | null;
    properties: string[];
    challenges: string[];
    followupPoints: string[];
    confidence: string | null;
    sourceType: string | null;
    validationStatus?: string | null;
    notForReleaseDecisions: boolean;
    disclaimer: string | null;
  };
  technicalDerivations?: WorkspaceTechnicalDerivation[];
  deepDiveTabs: WorkspaceDeepDiveTab[];
  specificity: {
    materialSpecificityRequired: string;
    completenessDepth: string;
    elevationPossible: boolean;
    elevationTarget: string | null;
    elevationHints: WorkspaceElevationHint[];
  };
  candidates: {
    viable: WorkspaceCandidate[];
    manufacturerValidationRequired: WorkspaceCandidate[];
    excluded: WorkspaceCandidate[];
    total: number;
  };
  conflicts: {
    total: number;
    open: number;
    resolved: number;
    bySeverity: Record<string, number>;
    items: WorkspaceConflict[];
  };
  claims: {
    total: number;
    byType: Record<string, number>;
    byOrigin: Record<string, number>;
    items: WorkspaceClaim[];
  };
  evidence: WorkspaceEvidenceSummary;
  manufacturerQuestions: {
    mandatory: string[];
    openQuestions: WorkspaceManufacturerQuestion[];
    totalOpen: number;
  };
  matching: {
    ready: boolean;
    shortlistReady: boolean;
    inquiryReady: boolean;
    notReadyReasons: string[];
    blockingReasons: string[];
    items: WorkspaceMatchItem[];
    openManufacturerQuestions: string[];
    selectedPartnerId: string | null;
    dataSource: string;
    manufacturerFitMatrix?: WorkspaceManufacturerFitMatrix | null;
  };
  rfq: {
    status: "unavailable" | "draft" | "ready";
    rfq_ready: boolean;
    releaseStatus: string;
    confirmed: boolean;
    blockers: string[];
    openPoints: string[];
    hasPdf: boolean;
    hasHtmlReport: boolean;
    hasDraft: boolean;
    documentUrl: string | null;
    handoverReady: boolean;
    handoverInitiated: boolean;
    package: {
      rfqId: string | null;
      basisStatus: string;
      operatingContextRedacted: Record<string, unknown>;
      manufacturerQuestionsMandatory: string[];
      conflictsVisibleCount: number;
      buyerAssumptionsAcknowledged: string[];
    };
  };
};
