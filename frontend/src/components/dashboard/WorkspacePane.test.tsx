import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import WorkspacePane from "@/components/dashboard/WorkspacePane";
import type { WorkspaceView } from "@/lib/contracts/workspace";

const workspace: WorkspaceView = {
  caseId: "case-123",
  communication: {
    conversationPhase: "clarification",
    turnGoal: "clarify_primary_open_point",
    primaryQuestion: null,
    supportingReason: null,
    responseMode: "single_question",
    confirmedFactsSummary: ["Medium: Dampf"],
    openPointsSummary: [],
  },
  lifecycle: { currentStep: null, completedSteps: [], steps: [] },
  summary: {
    turnCount: 1,
    maxTurns: 12,
    analysisCycleId: 1,
    stateRevision: 1,
    assertedProfileRevision: 1,
    derivedArtifactsStale: false,
    staleReason: null,
  },
  completeness: {
    coverageScore: 0.5,
    coveragePercent: 50,
    coverageGaps: [],
    completenessDepth: "precheck",
    missingCriticalParameters: [],
    analysisComplete: false,
    recommendationReady: false,
  },
  governance: {
    releaseStatus: "precheck_only",
    releaseClass: "B",
    scopeOfValidity: [],
    assumptions: [],
    unknownsBlocking: [],
    unknownsManufacturerValidation: [],
    gateFailures: [],
    notes: [],
    requiredDisclaimers: [],
    verificationPassed: true,
  },
  mediumCapture: {
    rawMentions: [],
    primaryRawText: null,
    sourceTurnRef: null,
    sourceTurnIndex: null,
  },
  mediumClassification: {
    canonicalLabel: "Dampf",
    family: "gasfoermig",
    confidence: "high",
    status: "recognized",
    normalizationSource: "deterministic_alias_map",
    mappingConfidence: "confirmed",
    matchedAlias: "dampf",
    sourceRegistryKey: "dampf",
    followupQuestion: null,
  },
  mediumContext: {
    mediumLabel: "Dampf",
    status: "available",
    scope: "orientierend",
    summary: "Orientierender Medium-Kontext.",
    properties: [],
    challenges: [],
    followupPoints: [],
    confidence: "medium",
    sourceType: "catalog",
    notForReleaseDecisions: true,
    disclaimer: "Allgemeiner Medium-Kontext, nicht als Freigabe.",
  },
  specificity: {
    materialSpecificityRequired: "family_only",
    completenessDepth: "precheck",
    elevationPossible: false,
    elevationTarget: null,
    elevationHints: [],
  },
  candidates: { viable: [], manufacturerValidationRequired: [], excluded: [], total: 0 },
  conflicts: { total: 0, open: 0, resolved: 0, bySeverity: {}, items: [] },
  claims: { total: 0, byType: {}, byOrigin: {}, items: [] },
  manufacturerQuestions: { mandatory: [], openQuestions: [], totalOpen: 0 },
  matching: {
    ready: false,
    notReadyReasons: [],
    items: [],
    openManufacturerQuestions: [],
    selectedPartnerId: null,
    dataSource: "candidate_derived",
  },
  rfq: {
    status: "unavailable",
    releaseStatus: "precheck_only",
    confirmed: false,
    blockers: [],
    openPoints: [],
    hasPdf: false,
    hasHtmlReport: false,
    hasDraft: false,
    documentUrl: null,
    handoverReady: false,
    handoverInitiated: false,
    package: {
      rfqId: null,
      basisStatus: "inadmissible",
      operatingContextRedacted: {},
      manufacturerQuestionsMandatory: [],
      conflictsVisibleCount: 0,
      buyerAssumptionsAcknowledged: [],
    },
  },
};

const workspaceStoreState = {
  workspace,
  workspaceLoading: false,
  streamWorkspace: null,
  isSidebarOpen: true,
  isDesktopViewport: true,
  closeSidebar: vi.fn(),
};

const chatStoreState = {
  isStreaming: false,
};

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: typeof workspaceStoreState) => unknown) =>
    selector(workspaceStoreState),
}));

vi.mock("@/lib/store/chatStore", () => ({
  useChatStore: (selector: (state: typeof chatStoreState) => unknown) =>
    selector(chatStoreState),
}));

vi.mock("@/lib/mediumStatusView", () => ({
  buildMediumStatusViewFromWorkspace: () => ({
    statusLabel: "erkannt",
    label: "Dampf",
    tone: "success",
    family: "gasfoermig",
    confidence: "hoch",
    rawMention: null,
    summary: "Das Medium wurde erkannt.",
    nextStepHint: null,
    status: "recognized",
  }),
}));

vi.mock("@/components/dashboard/CaseLifecyclePanel", () => ({
  default: () => <div>Lifecycle Panel</div>,
}));
vi.mock("@/components/dashboard/CaseStatusPanel", () => ({
  default: () => <div>Case Status Panel</div>,
}));
vi.mock("@/components/dashboard/MediumStatusPanel", () => ({
  default: () => <div>Medium Status Panel</div>,
}));
vi.mock("@/components/dashboard/PartnerMatchingPanel", () => ({
  default: () => <div>Matching Panel</div>,
}));
vi.mock("@/components/dashboard/RfqPackagePanel", () => ({
  default: () => <div>RFQ Panel</div>,
}));
vi.mock("@/components/dashboard/workspace", () => ({
  MediumContextPanel: () => <div>Medium Context Panel</div>,
  PanelSkeleton: () => null,
  ParameterTablePanel: () => <div>Parameter Panel</div>,
  StreamWorkspaceCards: () => null,
}));

describe("WorkspacePane", () => {
  it("does not render a separate next-step card in the right sidebar", () => {
    render(<WorkspacePane />);

    expect(screen.getByText("Technischer Status")).toBeInTheDocument();
    expect(screen.getByText("Case Status Panel")).toBeInTheDocument();
    expect(screen.queryByText("Nächste Schritte")).not.toBeInTheDocument();
  });
});
