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

export type WorkspaceView = {
  caseId: string;
  communication?: {
    conversationPhase?: string | null;
    turnGoal?: string | null;
    primaryQuestion?: string | null;
    supportingReason?: string | null;
    responseMode?: string | null;
    confirmedFactsSummary?: string[];
    openPointsSummary?: string[];
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
    notForReleaseDecisions: boolean;
    disclaimer: string | null;
  };
  technicalDerivations?: WorkspaceTechnicalDerivation[];
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
  manufacturerQuestions: {
    mandatory: string[];
    openQuestions: WorkspaceManufacturerQuestion[];
    totalOpen: number;
  };
  matching: {
    ready: boolean;
    notReadyReasons: string[];
    items: WorkspaceMatchItem[];
    openManufacturerQuestions: string[];
    selectedPartnerId: string | null;
    dataSource: string;
  };
  rfq: {
    status: "unavailable" | "draft" | "ready";
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
