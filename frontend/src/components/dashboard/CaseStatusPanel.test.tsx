import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CaseStatusPanel from "@/components/dashboard/CaseStatusPanel";
import type { WorkspaceView } from "@/lib/contracts/workspace";

const workspace: WorkspaceView = {
  caseId: "case-123",
  communication: {
    conversationPhase: "clarification",
    turnGoal: "clarify_primary_open_point",
    primaryQuestion: "Koennen Sie den Betriebsdruck noch einordnen?",
    supportingReason: "Dann kann ich die technische Einengung sauber weiterfuehren.",
    responseMode: "single_question",
    confirmedFactsSummary: ["Medium: Dampf", "Betriebsdruck: 12 bar"],
    openPointsSummary: ["Betriebsdruck"],
  },
  lifecycle: { currentStep: null, completedSteps: [], steps: [] },
  summary: {
    turnCount: 2,
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
    coverageGaps: ["pressure"],
    completenessDepth: "prequalification",
    missingCriticalParameters: ["pressure"],
    analysisComplete: false,
    recommendationReady: false,
  },
  governance: {
    releaseStatus: "manufacturer_validation_required",
    releaseClass: "B",
    scopeOfValidity: ["Temperaturfenster bis 180 C belastbar"],
    assumptions: ["temperature steady"],
    unknownsBlocking: [],
    unknownsManufacturerValidation: [],
    gateFailures: [],
    notes: [],
    requiredDisclaimers: ["Nur vorlaeufige Einordnung"],
    verificationPassed: false,
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
    summary: "Orientierende Einordnung fuer dampffuehrende Anwendungen.",
    properties: ["gasfoermig"],
    challenges: ["Temperatur- und Kondensatwechsel beachten"],
    followupPoints: ["Temperatur"],
    confidence: "medium",
    sourceType: "catalog",
    notForReleaseDecisions: true,
    disclaimer: "Allgemeiner Medium-Kontext, nicht als Freigabe.",
  },
  technicalDerivations: [
    {
      calcType: "rwdr",
      status: "ok",
      vSurfaceMPerS: 3.93,
      pvValueMpaMPerS: 0.39,
      dnValue: 75000,
      notes: ["Dn-Wert liegt im ueblichen Richtbereich."],
    },
  ],
  specificity: {
    materialSpecificityRequired: "compound_required",
    completenessDepth: "prequalification",
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
    status: "draft",
    releaseStatus: "manufacturer_validation_required",
    confirmed: false,
    blockers: ["pressure"],
    openPoints: ["pressure"],
    hasPdf: false,
    hasHtmlReport: false,
    hasDraft: true,
    documentUrl: null,
    handoverReady: false,
    handoverInitiated: false,
    package: {
      rfqId: null,
      basisStatus: "draft",
      operatingContextRedacted: {},
      manufacturerQuestionsMandatory: [],
      conflictsVisibleCount: 0,
      buyerAssumptionsAcknowledged: [],
    },
  },
};

describe("CaseStatusPanel", () => {
  it("renders a declarative technical state view without a second chat prompt", () => {
    render(<CaseStatusPanel workspace={workspace} />);

    expect(screen.getByText("Gezielte Klaerung")).toBeInTheDocument();
    expect(screen.getByText("Ermittelte Parameter")).toBeInTheDocument();
    expect(screen.getByText("Medium: Dampf")).toBeInTheDocument();
    expect(screen.getByText("Technischer Rahmen")).toBeInTheDocument();
    expect(screen.getByText("Medium eingeordnet: Dampf")).toBeInTheDocument();
    expect(screen.getByText("Technische Ableitungen")).toBeInTheDocument();
    expect(screen.getByText("3.93 m/s")).toBeInTheDocument();
    expect(screen.queryByText("Aktueller Fokus")).not.toBeInTheDocument();
    expect(screen.queryByText("Koennen Sie den Betriebsdruck noch einordnen?")).not.toBeInTheDocument();
  });
});
