import assert from "node:assert/strict";
import test from "node:test";

import * as workspaceBff from "./workspace.ts";

test("workspace reads target the workspace BFF path", async (t) => {
  const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const fetchMock = t.mock.method(globalThis, "fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ input, init });
    return new Response(
      JSON.stringify({
        caseId: "case/42",
        lifecycle: { currentStep: null, completedSteps: [], steps: [] },
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
          coverageScore: 0,
          coveragePercent: 0,
          coverageGaps: [],
          completenessDepth: "discovery",
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
          verificationPassed: false,
        },
        specificity: {
          materialSpecificityRequired: "family_only",
          completenessDepth: "discovery",
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
          dataSource: "none",
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
            basisStatus: "none",
            operatingContextRedacted: {},
            manufacturerQuestionsMandatory: [],
            conflictsVisibleCount: 0,
            buyerAssumptionsAcknowledged: [],
          },
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  const workspace = await workspaceBff.fetchWorkspace("case/42");

  assert.equal(workspace.caseId, "case/42");
  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.input, "/api/bff/workspace/case%2F42");
  assert.deepEqual(calls[0]?.init, { cache: "no-store" });
  fetchMock.mock.restore();
});

test("workspace path builders target canonical agent read contracts", () => {
  assert.equal(
    workspaceBff.buildWorkspaceBackendReadPath("case/42"),
    "/api/agent/workspace/case%2F42",
  );
  assert.equal(
    workspaceBff.buildRfqDocumentBackendReadPath("case/42"),
    "/api/agent/workspace/case%2F42/rfq-document",
  );
});

test("workspace path builders keep RFQ document reads on BFF while actions stay absent", () => {
  assert.equal(
    workspaceBff.buildWorkspaceReadPath("case/42"),
    "/api/bff/workspace/case%2F42",
  );
  assert.equal(
    workspaceBff.buildRfqDocumentReadPath("case/42"),
    "/api/bff/rfq/case%2F42/document",
  );

  const exportedKeys = Object.keys(workspaceBff).sort();
  assert.deepEqual(exportedKeys, [
    "buildRfqDocumentBackendReadPath",
    "buildRfqDocumentReadPath",
    "buildWorkspaceBackendReadPath",
    "buildWorkspaceReadPath",
    "fetchWorkspace",
  ]);
});
