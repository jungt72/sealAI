import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";

import { ManufacturerFitPanel } from "./ManufacturerFitPanel";

function workspaceFixture(overrides: Partial<WorkspaceView> = {}): WorkspaceView {
  return {
    caseId: "case-fit-1",
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
    mediumCapture: { rawMentions: [], primaryRawText: null, sourceTurnRef: null, sourceTurnIndex: null },
    mediumClassification: {
      canonicalLabel: null,
      family: "unknown",
      confidence: "unknown",
      status: "unknown",
      normalizationSource: null,
      mappingConfidence: null,
      matchedAlias: null,
      sourceRegistryKey: null,
      followupQuestion: null,
    },
    mediumContext: {
      mediumLabel: null,
      status: "unknown",
      scope: "case",
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
      materialSpecificityRequired: "unknown",
      completenessDepth: "prequalification",
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
      ready: true,
      shortlistReady: false,
      inquiryReady: false,
      notReadyReasons: [],
      blockingReasons: [],
      items: [],
      openManufacturerQuestions: [],
      selectedPartnerId: null,
      dataSource: "manufacturer_fit_matrix",
      manufacturerFitMatrix: {
        status: "fit_computed",
        disclosure: "Partnernetzwerk-Disclosure. Der Hersteller muss prüfen.",
        eligiblePartnerCount: 2,
        noSuitablePartnerReason: null,
        rows: [
          {
            manufacturerId: "partner-a",
            fitScore: 96,
            verificationLevel: "verified",
            fitReasons: ["seal_type:rwdr", "material_family:ptfe_glass_filled"],
            gaps: [],
            missingRequirements: [],
            sourceClaimIds: ["claim-a"],
          },
        ],
      },
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
        basisStatus: "draft",
        operatingContextRedacted: {},
        manufacturerQuestionsMandatory: [],
        conflictsVisibleCount: 0,
        buyerAssumptionsAcknowledged: [],
      },
    },
    ...overrides,
  } as WorkspaceView;
}

describe("ManufacturerFitPanel", () => {
  it("renders fit rows with disclosure, reasons and verification level", () => {
    render(<ManufacturerFitPanel workspace={workspaceFixture()} />);

    expect(screen.getByRole("heading", { name: "Partner-Fit" })).toBeInTheDocument();
    expect(screen.getByText("Partnernetzwerk-Disclosure. Der Hersteller muss prüfen.")).toBeInTheDocument();
    expect(screen.getByText("partner-a")).toBeInTheDocument();
    expect(screen.getByText("96")).toBeInTheDocument();
    expect(screen.getByText("Belegstatus: geprüft")).toBeInTheDocument();
    expect(screen.getByText("seal type:rwdr")).toBeInTheDocument();
  });

  it("renders a no-fit state without creating a fake partner", () => {
    render(
      <ManufacturerFitPanel
        workspace={workspaceFixture({
          matching: {
            ...workspaceFixture().matching,
            manufacturerFitMatrix: {
              status: "no_suitable_partner",
              disclosure: "Partnernetzwerk-Disclosure. Der Hersteller muss prüfen.",
              eligiblePartnerCount: 0,
              noSuitablePartnerReason: "no_active_paid_partner",
              rows: [],
            },
          },
        })}
      />,
    );

    expect(screen.getByText(/Aktuell wurde kein passendes Partnerprofil gemeldet/)).toBeInTheDocument();
    expect(screen.getByText(/no active paid partner/)).toBeInTheDocument();
    expect(screen.queryByText("partner-a")).not.toBeInTheDocument();
  });

  it("renders an empty state when backend has no fit matrix yet", () => {
    render(
      <ManufacturerFitPanel
        workspace={workspaceFixture({
          matching: {
            ...workspaceFixture().matching,
            manufacturerFitMatrix: null,
          },
        })}
      />,
    );

    expect(screen.getByText(/sobald dafür genügend geprüfte Informationen vorliegen/)).toBeInTheDocument();
  });

  it("does not render unsafe marketplace or dispatch copy", () => {
    render(<ManufacturerFitPanel workspace={workspaceFixture()} />);

    expect(screen.queryByText(/bester Hersteller/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/An Hersteller senden/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/versendet/i)).not.toBeInTheDocument();
  });
});
