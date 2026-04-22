import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import type { WorkspaceView } from "@/lib/contracts/workspace";
import { useCockpitData } from "./useCockpitData";

function workspaceFixture(): WorkspaceView {
  return {
    caseId: "case-1",
    requestType: "retrofit",
    engineeringPath: "static",
    cockpit: {
      path: "rwdr",
      requestType: "validation_check",
      routingMetadata: {
        phase: "clarification",
        lastNode: "facade_hydration",
        routing: {},
      },
      sections: {
        core_intake: {
          id: "core_intake",
          title: "A. Grunddaten",
          properties: [
            {
              key: "medium",
              label: "Medium / Fluid",
              value: "Salzwasser",
              origin: "user_override",
              confidence: "confirmed",
              isConfirmed: true,
              isMandatory: true,
            },
          ],
          completion: {
            mandatoryPresent: 1,
            mandatoryTotal: 2,
            percent: 50,
          },
        },
        failure_drivers: {
          id: "failure_drivers",
          title: "B. Technische Risikofaktoren",
          properties: [],
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
        },
        geometry_fit: {
          id: "geometry_fit",
          title: "C. Geometrie & Einbauraum",
          properties: [],
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
        },
        rfq_liability: {
          id: "rfq_liability",
          title: "D. Anfrage- & Freigabereife",
          properties: [],
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
        },
      },
      checks: [
        {
          calcId: "rwdr_circumferential_speed",
          label: "RWDR circumferential speed",
          formulaVersion: "rwdr_calc_v1",
          requiredInputs: ["shaft_diameter_mm", "speed_rpm"],
          missingInputs: [],
          validPaths: ["rwdr"],
          outputKey: "v_surface_m_s",
          unit: "m/s",
          status: "ok",
          value: 3.93,
          fallbackBehavior: "insufficient_data_when_required_inputs_missing",
          guardrails: ["diameter and speed must be present and non-negative"],
          notes: [],
        },
      ],
      readiness: {
        isRfqReady: false,
        missingMandatoryKeys: ["pressure_bar"],
        blockers: ["manufacturer_validation_required"],
        status: "preliminary",
        releaseStatus: "manufacturer_validation_required",
        coverageScore: 0.5,
      },
      mediumContext: {
        canonicalName: "Salzwasser",
        isConfirmed: true,
        properties: ["wasserbasiert"],
        riskFlags: ["Korrosion beachten"],
      },
    },
    parameters: {
      medium: "Salzwasser",
      motion_type: "static",
    },
    lifecycle: {
      currentStep: null,
      completedSteps: [],
      steps: [],
    },
    summary: {
      turnCount: 1,
      maxTurns: 12,
      analysisCycleId: 0,
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
    mediumCapture: {
      rawMentions: ["salzwasser"],
      primaryRawText: "salzwasser",
      sourceTurnRef: "turn:1",
      sourceTurnIndex: 1,
    },
    mediumClassification: {
      canonicalLabel: "Salzwasser",
      family: "waessrig_salzhaltig",
      confidence: "high",
      status: "recognized",
      normalizationSource: "deterministic_alias_map",
      mappingConfidence: "confirmed",
      matchedAlias: "salzwasser",
      sourceRegistryKey: "salzwasser",
      followupQuestion: null,
    },
    mediumContext: {
      mediumLabel: "Salzwasser",
      status: "available",
      scope: "orientierend",
      summary: null,
      properties: ["wasserbasiert"],
      challenges: ["Korrosion beachten"],
      followupPoints: [],
      confidence: "medium",
      sourceType: "llm_general_knowledge",
      notForReleaseDecisions: true,
      disclaimer: null,
    },
    specificity: {
      materialSpecificityRequired: "family_only",
      completenessDepth: "precheck",
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
      releaseStatus: "manufacturer_validation_required",
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
}

describe("useCockpitData", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().reset();
  });


  it("keeps PTFE-RWDR fallback ahead of generic hydraulic wording", () => {
    const workspace = workspaceFixture();
    workspace.cockpit = null;
    workspace.engineeringPath = null;
    workspace.parameters = {
      medium: "HLP46",
      sealing_type: "PTFE-RWDR",
      application_context: "Hydraulik Getriebe",
      motion_type: "rotary",
    } as WorkspaceView["parameters"];

    useWorkspaceStore.setState({
      workspace,
      streamWorkspace: null,
      streamAssertions: null,
    });

    const { result } = renderHook(() => useCockpitData());

    expect(result.current?.view.path).toBe("rwdr");
  });

  it("prefers backend cockpit view over local fallback reconstruction", () => {
    useWorkspaceStore.setState({
      workspace: workspaceFixture(),
      streamWorkspace: null,
      streamAssertions: null,
    });

    const { result } = renderHook(() => useCockpitData());

    expect(result.current?.view.path).toBe("rwdr");
    expect(result.current?.view.requestType).toBe("validation_check");
    expect(result.current?.view.checks[0]?.calcId).toBe("rwdr_circumferential_speed");
    expect(result.current?.view.readiness.missingMandatoryKeys).toEqual(["pressure_bar"]);
  });
});
