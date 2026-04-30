import { describe, expect, it } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";

import { buildSealCockpitViewModel } from "./buildSealCockpitViewModel";

function workspaceFixture(overrides: Partial<WorkspaceView> = {}): WorkspaceView {
  return {
    caseId: "case-temperature",
    engineeringPath: "rwdr",
    parameters: {
      medium: "Oel",
      temperature_c: 120,
      sealing_type: "PTFE-RWDR",
    },
    lifecycle: { currentStep: null, completedSteps: [], steps: [] },
    summary: {
      turnCount: 1,
      maxTurns: 8,
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
      completenessDepth: "partial",
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
      verificationPassed: false,
    },
    mediumCapture: {
      rawMentions: [],
      primaryRawText: null,
      sourceTurnRef: null,
      sourceTurnIndex: null,
    },
    mediumClassification: {
      canonicalLabel: "Oel",
      family: "oil",
      confidence: "medium",
      status: "recognized",
      normalizationSource: null,
      mappingConfidence: null,
      matchedAlias: null,
      sourceRegistryKey: null,
      followupQuestion: null,
    },
    mediumContext: {
      mediumLabel: "Oel",
      status: "recognized",
      scope: "orientierend",
      summary: null,
      properties: [],
      challenges: [],
      followupPoints: [],
      confidence: null,
      sourceType: null,
      validationStatus: null,
      notForReleaseDecisions: true,
      disclaimer: null,
    },
    technicalDerivations: [
      {
        calcType: "rwdr",
        status: "ok",
        vSurfaceMPerS: null,
        pvValueMpaMPerS: null,
        dnValue: null,
        temperatureHeadroomC: 140,
        notes: ["Backend-Ableitung aus Werkstofffamilie und Temperatur."],
      },
    ],
    deepDiveTabs: [],
    specificity: {
      materialSpecificityRequired: "partial",
      completenessDepth: "partial",
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
    claims: { total: 0, byType: {}, byOrigin: {}, items: [] },
    evidence: {
      evidencePresent: false,
      evidenceCount: 0,
      trustedSourcesPresent: false,
      evidenceSupportedTopics: [],
      sourceBackedFindings: [],
      deterministicFindings: [],
      assumptionBasedFindings: [],
      unresolvedOpenPoints: [],
      evidenceGaps: [],
    },
    manufacturerQuestions: {
      mandatory: [],
      openQuestions: [],
      totalOpen: 0,
    },
    matching: {
      ready: false,
      shortlistReady: false,
      inquiryReady: false,
      notReadyReasons: [],
      blockingReasons: [],
      items: [],
      openManufacturerQuestions: [],
      selectedPartnerId: null,
      dataSource: "candidate_derived",
    },
    rfq: {
      status: "draft",
      rfq_ready: false,
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
        basisStatus: "draft",
        operatingContextRedacted: {},
        manufacturerQuestionsMandatory: [],
        conflictsVisibleCount: 0,
        buyerAssumptionsAcknowledged: [],
      },
    },
    ...overrides,
  };
}

describe("buildSealCockpitViewModel", () => {
  it("renders temperature headroom from backend derivations", () => {
    const viewModel = buildSealCockpitViewModel(workspaceFixture());

    expect(viewModel.calculations).toContainEqual(
      expect.objectContaining({
        label: "Temperaturfenster",
        value: "140 °C",
        status: "backend-berechnet",
      }),
    );
  });

  it("keeps the temperature calculation open when material family is missing", () => {
    const viewModel = buildSealCockpitViewModel(
      workspaceFixture({ technicalDerivations: [] }),
    );

    expect(viewModel.calculations).toContainEqual(
      expect.objectContaining({
        label: "Temperaturfenster",
        value: "Nicht berechenbar",
        limit: "Fehlende Eingaben: Werkstofffamilie",
      }),
    );
  });

  it("does not render an empty missing-input label when a backend check is not registered", () => {
    const viewModel = buildSealCockpitViewModel(
      workspaceFixture({
        parameters: {
          medium: "Oel",
          temperature_c: 120,
          pressure_bar: 5,
          sealing_type: "PTFE-RWDR",
          shaft_diameter_mm: 50,
          speed_rpm: 1500,
        },
        technicalDerivations: [
          {
            calcType: "rwdr",
            status: "ok",
            vSurfaceMPerS: 3.93,
            pvValueMpaMPerS: 1.96,
            dnValue: 75000,
            temperatureHeadroomC: 140,
            notes: ["Backend-Ableitung aus Workspace-Parametern."],
          },
        ],
      }),
    );

    expect(viewModel.calculations).toContainEqual(
      expect.objectContaining({
        label: "Druckfenster",
        value: "Nicht berechenbar",
        limit: "Backend-Nachweis noch nicht registriert",
      }),
    );
    expect(viewModel.calculations).not.toContainEqual(
      expect.objectContaining({ limit: "Fehlende Eingaben: " }),
    );
  });

  it("renders pressure-window evidence when the backend projection provides it", () => {
    const viewModel = buildSealCockpitViewModel(
      workspaceFixture({
        technicalDerivations: [
          {
            calcType: "rwdr",
            status: "ok",
            vSurfaceMPerS: 3.93,
            pvValueMpaMPerS: 1.96,
            dnValue: 75000,
            temperatureHeadroomC: 140,
            pressureWindow: "5 bar · RWDR-Druckfenster herstellerseitig prüfen",
            notes: ["Backend-Ableitung aus Workspace-Parametern."],
          },
        ],
      }),
    );

    expect(viewModel.calculations).toContainEqual(
      expect.objectContaining({
        label: "Druckfenster",
        value: "5 bar · RWDR-Druckfenster herstellerseitig prüfen",
        status: "backend-berechnet",
      }),
    );
  });
});
