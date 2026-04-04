import assert from "node:assert/strict";
import test from "node:test";

import type { WorkspaceView } from "@/lib/contracts/workspace";
import {
  getUnavailableMatchingActions,
  getUnavailableRfqActions,
} from "./workspaceActionAvailability.ts";

function makeWorkspace(
  overrides: Partial<WorkspaceView> = {},
): WorkspaceView {
  return {
    caseId: "case-123",
    lifecycle: {
      currentStep: null,
      completedSteps: [],
      steps: [],
    },
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
      coverageScore: 0.75,
      coveragePercent: 75,
      coverageGaps: [],
      completenessDepth: "prequalification",
      missingCriticalParameters: [],
      analysisComplete: false,
      recommendationReady: false,
    },
    governance: {
      releaseStatus: "manufacturer_validation_required",
      releaseClass: "C",
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
      ready: true,
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
      blockers: [],
      openPoints: [],
      hasPdf: false,
      hasHtmlReport: false,
      hasDraft: true,
      documentUrl: null,
      handoverReady: false,
      handoverInitiated: false,
      package: {
        rfqId: "rfq-1",
        basisStatus: "provisional",
        operatingContextRedacted: {},
        manufacturerQuestionsMandatory: [],
        conflictsVisibleCount: 0,
        buyerAssumptionsAcknowledged: [],
      },
    },
    ...overrides,
  };
}

test("RFQ actions stay explicitly unavailable while only reads are closed", () => {
  const workspace = makeWorkspace();

  assert.deepEqual(
    getUnavailableRfqActions(workspace).map((action) => action.id),
    ["rfq_confirm", "rfq_generate_document", "rfq_handover"],
  );
});

test("RFQ unavailable actions are still shown when the panel is relevant without a draft", () => {
  const workspace = makeWorkspace({
    rfq: {
      ...makeWorkspace().rfq,
      hasDraft: false,
    },
  });

  assert.deepEqual(
    getUnavailableRfqActions(workspace).map((action) => action.id),
    ["rfq_confirm", "rfq_generate_document", "rfq_handover"],
  );
});

test("RFQ document download does not create a fake unavailable action once the read is present", () => {
  const workspace = makeWorkspace({
    rfq: {
      ...makeWorkspace().rfq,
      confirmed: true,
      hasHtmlReport: true,
      documentUrl: "/api/bff/rfq/case-123/document",
    },
  });

  assert.deepEqual(
    getUnavailableRfqActions(workspace).map((action) => action.id),
    ["rfq_handover"],
  );
});

test("RFQ unavailable actions only clear per fulfilled state", () => {
  const workspace = makeWorkspace({
    rfq: {
      ...makeWorkspace().rfq,
      confirmed: true,
      handoverInitiated: true,
    },
  });

  assert.deepEqual(
    getUnavailableRfqActions(workspace).map((action) => action.id),
    ["rfq_generate_document"],
  );
});

test("partner selection stays explicitly unavailable while no canonical action exists", () => {
  const workspace = makeWorkspace({
    matching: {
      ...makeWorkspace().matching,
      items: [
        {
          material: "FKM",
          cluster: "viable",
          specificity: "family_only",
          requiresValidation: false,
          fitBasis: "evidence",
          groundedFacts: [],
        },
      ],
    },
  });

  assert.deepEqual(
    getUnavailableMatchingActions(workspace).map((action) => action.id),
    ["partner_select"],
  );
});

test("partner selection stays explicitly unavailable even when no candidates are listed yet", () => {
  const workspace = makeWorkspace();

  assert.deepEqual(
    getUnavailableMatchingActions(workspace).map((action) => action.id),
    ["partner_select"],
  );
});

test("selected partners do not advertise a dead selection action", () => {
  const workspace = makeWorkspace({
    matching: {
      ...makeWorkspace().matching,
      items: [
        {
          material: "FKM",
          cluster: "viable",
          specificity: "family_only",
          requiresValidation: false,
          fitBasis: "evidence",
          groundedFacts: [],
        },
      ],
      selectedPartnerId: "FKM",
    },
  });

  assert.deepEqual(getUnavailableMatchingActions(workspace), []);
});
