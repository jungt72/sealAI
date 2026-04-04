import assert from "node:assert/strict";
import test from "node:test";

import { deriveLifecycleSteps } from "./lifecycleSteps.ts";
import type { WorkspaceView } from "./contracts/workspace.ts";

function workspaceView(): WorkspaceView {
  return {
    caseId: "case-123",
    lifecycle: {
      currentStep: "Partner Matching",
      completedSteps: ["Case Started", "Governed Review"],
      steps: [
        { label: "Case Started", status: "done", iconName: "Layers" },
        { label: "Governed Review", status: "done", iconName: "Shield" },
        { label: "Partner Matching", status: "active", iconName: "Factory" },
      ],
    },
    summary: {
      turnCount: 3,
      maxTurns: 12,
      analysisCycleId: 1,
      stateRevision: 2,
      assertedProfileRevision: 2,
      derivedArtifactsStale: false,
      staleReason: null,
    },
    completeness: {
      coverageScore: 0.5,
      coveragePercent: 50,
      coverageGaps: [],
      completenessDepth: "prequalification",
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
    specificity: {
      materialSpecificityRequired: "family_only",
      completenessDepth: "prequalification",
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
    manufacturerQuestions: {
      mandatory: [],
      openQuestions: [],
      totalOpen: 0,
    },
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
      releaseStatus: "precheck_only",
      confirmed: false,
      blockers: [],
      openPoints: [],
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
}

test("deriveLifecycleSteps returns the vNext lifecycle sequence unchanged", () => {
  const workspace = workspaceView();
  assert.deepEqual(deriveLifecycleSteps(workspace), workspace.lifecycle.steps);
});
