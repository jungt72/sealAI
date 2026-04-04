import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MediumContextPanel from "@/components/dashboard/MediumContextPanel";
import type { WorkspaceView } from "@/lib/contracts/workspace";

const workspace: WorkspaceView = {
  caseId: "case-123",
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
    coverageScore: 0.4,
    coveragePercent: 40,
    coverageGaps: [],
    completenessDepth: "precheck",
    missingCriticalParameters: [],
    analysisComplete: false,
    recommendationReady: false,
  },
  governance: {
    releaseStatus: "inadmissible",
    releaseClass: "D",
    scopeOfValidity: [],
    assumptions: [],
    unknownsBlocking: [],
    unknownsManufacturerValidation: [],
    gateFailures: [],
    notes: [],
    requiredDisclaimers: [],
    verificationPassed: true,
  },
  mediumContext: {
    mediumLabel: "Salzwasser",
    status: "available",
    scope: "orientierend",
    summary: "Allgemeiner Medium-Kontext fuer salzhaltige wasserbasierte Anwendungen.",
    properties: ["wasserbasiert", "salzhaltig"],
    challenges: ["Korrosionsrisiko an Metallkomponenten beachten"],
    followupPoints: ["Salzkonzentration", "Temperatur"],
    confidence: "medium",
    sourceType: "llm_general_knowledge",
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
    releaseStatus: "inadmissible",
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

describe("MediumContextPanel", () => {
  it("renders the orienting medium context card from structured workspace data", () => {
    render(<MediumContextPanel workspace={workspace} />);

    expect(screen.getByText("Salzwasser")).toBeInTheDocument();
    expect(screen.getByText("orientierend")).toBeInTheDocument();
    expect(screen.getByText("Typische Eigenschaften")).toBeInTheDocument();
    expect(screen.getByText("Korrosionsrisiko an Metallkomponenten beachten")).toBeInTheDocument();
    expect(screen.getByText("Allgemeiner Medium-Kontext, nicht als Freigabe.")).toBeInTheDocument();
    expect(screen.queryByText("Wichtige Folgepunkte")).not.toBeInTheDocument();
    expect(screen.queryByText("Salzkonzentration")).not.toBeInTheDocument();
  });
});
