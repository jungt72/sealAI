import { describe, expect, it } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";

import { buildSealCockpitViewModel } from "./buildSealCockpitViewModel";

function workspaceWithCockpit(
  cockpit: WorkspaceView["cockpit"],
  overrides: Partial<WorkspaceView> = {},
): WorkspaceView {
  return {
    caseId: "case-metrics",
    engineeringPath: "rwdr",
    parameters: { medium: "Oel", sealing_type: "RWDR" },
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
    deepDiveTabs: [],
    specificity: {
      materialSpecificityRequired: "partial",
      completenessDepth: "partial",
      elevationPossible: false,
      elevationTarget: null,
      elevationHints: [],
    },
    candidates: { viable: [], manufacturerValidationRequired: [], excluded: [], total: 0 },
    conflicts: { total: 0, open: 0, resolved: 0, bySeverity: {}, items: [] },
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
    manufacturerQuestions: { mandatory: [], openQuestions: [], totalOpen: 0 },
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
    cockpit,
    ...overrides,
  } as WorkspaceView;
}

function cockpitFixture(): NonNullable<WorkspaceView["cockpit"]> {
  const section = (id: "application_function" | "medium_environment" | "operating_geometry" | "risk_readiness") => ({
    id,
    title: id,
    properties: [],
    completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
  });
  return {
    path: "rwdr",
    requestType: "validation_check",
    routingMetadata: { phase: "clarification", lastNode: "projection", routing: {} },
    sections: {
      application_function: section("application_function"),
      medium_environment: section("medium_environment"),
      operating_geometry: section("operating_geometry"),
      risk_readiness: section("risk_readiness"),
    },
    checks: [],
    checkMetrics: {
      checkTotal: 5,
      checkAvailableCount: 3,
      checkBlockedCount: 2,
      checkPendingCount: 0,
      checkFailedCount: 0,
      checkPassedCount: 3,
      source: "backend_check_registry",
    },
    completenessMetrics: {
      completenessPercent: 62,
      requiredTotal: 8,
      requiredKnown: 5,
      requiredMissing: ["pressure_at_seal_bar"],
      requiredInvalid: [],
      requiredFields: [],
      source: "backend_required_field_policy",
    },
    riskEvaluations: [],
    readiness: {
      isRfqReady: false,
      missingMandatoryKeys: [],
      blockers: [],
      status: "preliminary",
      releaseStatus: "precheck_only",
      coverageScore: 0,
    },
    mediumContext: {
      canonicalName: "Oel",
      isConfirmed: true,
      properties: [],
      riskFlags: [],
    },
  };
}

describe("buildSealCockpitViewModel backend metrics", () => {
  it("uses backend check metrics when present", () => {
    const viewModel = buildSealCockpitViewModel(workspaceWithCockpit(cockpitFixture()));

    expect(viewModel.statusStrip).toContainEqual({ label: "Stand", value: "62 % geklärt" });
    expect(viewModel.statusStrip).toContainEqual({ label: "Gerechnet", value: "3 von 5 Checks verfügbar" });
  });

  it("does not fabricate check metrics when backend metrics are missing", () => {
    const cockpit = cockpitFixture();
    cockpit.checkMetrics = null;
    cockpit.completenessMetrics = null;
    const viewModel = buildSealCockpitViewModel(workspaceWithCockpit(cockpit));

    expect(viewModel.statusStrip).toContainEqual({ label: "Stand", value: "Backend-Metrik fehlt" });
    expect(viewModel.statusStrip).toContainEqual({ label: "Gerechnet", value: "Backend-Metrik fehlt" });
  });

  it("keeps backend compatibility evidence metadata on calculation metrics", () => {
    const cockpit = cockpitFixture();
    cockpit.checks = [
      {
        calcId: "material.compatibility_precheck",
        checkId: "material.compatibility_precheck",
        label: "Werkstoff-/Medium-Precheck",
        formulaVersion: "compatibility_precheck_v1",
        requiredInputs: ["medium", "sealing_material_family"],
        requiredFields: ["medium", "sealing_material_family"],
        missingInputs: [],
        missingFields: ["concentration"],
        validPaths: ["rwdr"],
        outputKey: "compatibility_precheck",
        unit: null,
        status: "screening",
        value: null,
        fallbackBehavior: "precheck_only_when_evidence_is_limited",
        guardrails: ["Keine Freigabeaussage"],
        evidenceFields: [],
        derivedFrom: [],
        severity: "screening",
        humanReadableReason: "Backend meldet nur einen Precheck.",
        rawStatus: null,
        notes: [],
        compatibilityStatus: "candidate_supported",
        evidenceStatus: "evidence_found",
        evidenceRefs: [{ refId: "ref-1", sourceTitle: "Material evidence card" }],
        evidenceSummary: "Backend meldet eine quellenmarkierte Screening-Grundlage.",
        evidenceLimitations: ["Hersteller-/Datenblattnachweis erforderlich"],
        ambiguousFields: ["temperature_c"],
        finalApprovalClaimAllowed: false,
      },
    ];

    const viewModel = buildSealCockpitViewModel(workspaceWithCockpit(cockpit));
    const metric = viewModel.calculations[0];

    expect(metric.compatibilityStatus).toBe("candidate_supported");
    expect(metric.evidenceStatus).toBe("evidence_found");
    expect(metric.evidenceRefs).toEqual([{ refId: "ref-1", sourceTitle: "Material evidence card" }]);
    expect(metric.evidenceSummary).toBe("Backend meldet eine quellenmarkierte Screening-Grundlage.");
    expect(metric.evidenceLimitations).toEqual(["Hersteller-/Datenblattnachweis erforderlich"]);
    expect(metric.missingFields).toEqual(["concentration"]);
    expect(metric.ambiguousFields).toEqual(["temperature_c"]);
    expect(metric.finalApprovalClaimAllowed).toBe(false);
  });

  it("adds persisted deterministic derivations beside cockpit checks", () => {
    const cockpit = cockpitFixture();
    cockpit.checks = [
      {
        calcId: "material.compatibility_precheck",
        checkId: "material.compatibility_precheck",
        label: "Material/Medium-Vertraeglichkeits-Precheck",
        formulaVersion: "material_medium_compatibility_precheck_v1",
        requiredInputs: ["medium", "material"],
        requiredFields: ["medium", "material"],
        missingInputs: ["medium"],
        missingFields: ["medium"],
        validPaths: ["rwdr"],
        outputKey: "material_medium_compatibility",
        unit: null,
        status: "blocked",
        value: null,
        fallbackBehavior: "precheck_only",
        guardrails: ["Keine Freigabeaussage"],
        evidenceFields: [],
        derivedFrom: [],
        severity: "screening",
        humanReadableReason: "Mediumangabe ist zu generisch.",
        rawStatus: null,
        notes: [],
      },
    ];
    cockpit.checkMetrics = {
      checkTotal: 1,
      checkAvailableCount: 0,
      checkBlockedCount: 1,
      checkPendingCount: 0,
      checkFailedCount: 0,
      checkPassedCount: 0,
      source: "backend_check_registry",
    };

    const viewModel = buildSealCockpitViewModel(
      workspaceWithCockpit(cockpit, {
        parameters: {
          medium: "Oel",
          pressure_bar: 5,
          temperature_c: 80,
          sealing_type: "rwdr",
          shaft_diameter_mm: 50,
          speed_rpm: 3000,
        },
        technicalDerivations: [
          {
            calcType: "rwdr",
            status: "ok",
            vSurfaceMPerS: 7.853981633974483,
            pvValueMpaMPerS: null,
            dnValue: 150000,
            temperatureHeadroomC: 180,
            notes: ["Calculated value is a screening intermediate."],
          },
        ],
      }),
    );

    expect(viewModel.statusStrip).toContainEqual({
      label: "Gerechnet",
      value: "3 Rechenwerte · 0 von 1 Checks verfügbar",
    });
    expect(viewModel.calculations).toContainEqual(
      expect.objectContaining({
        label: "Umfangsgeschwindigkeit",
        value: "7.854 m/s",
        status: "backend-berechnet",
      }),
    );
    expect(viewModel.calculations).toContainEqual(
      expect.objectContaining({
        label: "Drehzahl x Durchmesser",
        value: "150000",
        status: "backend-berechnet",
      }),
    );
  });
});
