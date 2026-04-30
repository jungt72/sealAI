import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";

import { DecisionUnderstandingPanel } from "./DecisionUnderstandingPanel";

function workspaceFixture(overrides: Partial<WorkspaceView> = {}): WorkspaceView {
  return {
    caseId: "case-du-1",
    communication: {
      primaryQuestion: "Liegt der Druck direkt an der Dichtstelle an?",
      supportingReason: "Der Systemdruck ist nicht automatisch der Dichtstellendruck.",
    },
    completeness: {
      coverageScore: 0.62,
      coveragePercent: 62,
      coverageGaps: [],
      completenessDepth: "prequalification",
      missingCriticalParameters: ["shaft_diameter_mm"],
      analysisComplete: false,
      recommendationReady: false,
    },
    governance: {
      releaseStatus: "manufacturer_validation_required",
      releaseClass: "C",
      scopeOfValidity: [],
      assumptions: [],
      unknownsBlocking: [],
      unknownsManufacturerValidation: ["ATEX-Kontext"],
      gateFailures: [],
      notes: [],
      requiredDisclaimers: [],
      verificationPassed: true,
    },
    mediumContext: {
      mediumLabel: "Ethanol",
      status: "available",
      scope: "case",
      summary: "Ethanol ist im Fallkontext relevant.",
      properties: [],
      challenges: [],
      followupPoints: [],
      confidence: "medium",
      sourceType: "user_stated",
      validationStatus: "user_stated",
      notForReleaseDecisions: false,
      disclaimer: null,
    },
    sealApplicationProfile: {
      sealFamily: "mechanical_seal",
      sealType: "mechanical_seal",
      sealTypeConfidence: 0.72,
      confidenceBand: "medium",
      matchedAlias: "Gleitringdichtung",
      ambiguous: false,
      candidateTypes: [],
      applicationDomain: "pump",
      motionType: "rotary",
      standardRefs: [],
      typeSpecificMissingHints: ["shaft_diameter_mm", "seal_chamber_pressure"],
      notes: [],
      source: "seal_type_normalizer",
    },
    decisionUnderstanding: {
      caseSummary: "Pumpenanwendung mit Ethanol, 150 °C und 10 bar.",
      understoodNow: ["Anlage: Pumpe", "Medium: Ethanol", "Temperatur: 150 °C"],
      technicalMeaning: ["Ethanol und Temperatur machen Herstellerprüfung wichtig."],
      plausibleDirections: ["Gleitringdichtung prüfen"],
      notYetDecidable: ["Druck an der Dichtstelle", "ATEX-Zone"],
      keyRisks: [
        "{'risk name': 'temperature risk', 'score': 3, 'label': 'high', 'missing inputs': [], 'explanation short': 'Temperatur wird gegen MVP-Schwellen bewertet.'}",
        "Druck",
      ],
      confidenceNotes: ["Dichtstelle noch offen"],
      nextBestQuestion: "Liegen die 10 bar direkt an der Dichtstelle an?",
      manufacturerReviewNeeds: ["Pumpentyp", "Drehzahl"],
      needsAnalysis: {
        primaryNeed: "new_rfq",
        secondaryNeeds: ["technical_clarification"],
        urgency: "normal",
        userSide: "buyer",
        contextSide: "pump",
        confidence: 0.8,
        notes: [],
      },
      currentStateAnalysis: {
        knownFields: ["medium", "temperature_c"],
        missingFields: ["shaft_diameter_mm"],
        uncertainFields: ["pressure_location"],
        conflictingFields: [],
        evidenceBackedFields: ["temperature_c"],
        sealTypeStatus: "candidate",
        readinessHint: "prequalification",
        confidence: 0.65,
      },
      nextBestQuestions: [
        {
          question: "Liegt der Druck direkt an der Dichtstelle an?",
          reason: "Das trennt Systemdruck von Dichtstellenbelastung.",
          focusKey: "pressure_location",
          priority: 1,
          expectedAnswerType: "text",
          appliesToCaseType: "new_rfq",
          appliesToSealType: "mechanical_seal",
          source: "next_best_question_service",
          maxQuestionsPolicy: "ask_1_to_3_targeted_questions",
        },
      ],
      completenessScore: {
        score: 0.62,
        missingCriticalCount: 1,
        knownCriticalCount: 3,
        uncertaintyCount: 1,
        conflictCount: 0,
        notes: [],
      },
    },
    rfq: {
      status: "draft",
      rfq_ready: false,
      releaseStatus: "manufacturer_validation_required",
      confirmed: false,
      blockers: [],
      openPoints: ["shaft_diameter_mm"],
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
    conflicts: {
      total: 0,
      open: 0,
      resolved: 0,
      bySeverity: {},
      items: [],
    },
    ...overrides,
  } as WorkspaceView;
}

describe("DecisionUnderstandingPanel", () => {
  it("renders understood content, missing fields and next-best-question with reason", () => {
    render(<DecisionUnderstandingPanel workspace={workspaceFixture()} />);

    expect(screen.getByRole("heading", { name: "Verstanden" })).toBeInTheDocument();
    expect(screen.getByText("Pumpenanwendung mit Ethanol, 150 °C und 10 bar.")).toBeInTheDocument();
    expect(screen.getByText("Anlage: Pumpe")).toBeInTheDocument();
    expect(screen.getAllByText("Wellendurchmesser").length).toBeGreaterThan(0);
    expect(screen.getByText("Liegt der Druck direkt an der Dichtstelle an?")).toBeInTheDocument();
    expect(screen.getByText("Das trennt Systemdruck von Dichtstellenbelastung.")).toBeInTheDocument();
  });

  it("renders source and validation badges without hiding unvalidated LLM fallback", () => {
    render(
      <DecisionUnderstandingPanel
        workspace={workspaceFixture({
          mediumContext: {
            ...workspaceFixture().mediumContext,
            sourceType: "llm_research_fallback",
            validationStatus: "unvalidated",
            notForReleaseDecisions: true,
          },
        })}
      />,
    );

    expect(screen.getByText("Woher: KI-Hinweis")).toBeInTheDocument();
    expect(screen.getByText("Stand: noch nicht geprüft")).toBeInTheDocument();
    expect(screen.getByText("Dieser KI-Hinweis ist noch nicht geprüft und bleibt nur Orientierung.")).toBeInTheDocument();
  });

  it("uses a human label for generic LLM synthesis sources", () => {
    render(
      <DecisionUnderstandingPanel
        workspace={workspaceFixture({
          mediumContext: {
            ...workspaceFixture().mediumContext,
            sourceType: "llm_synthesis",
            validationStatus: "unvalidated",
            notForReleaseDecisions: true,
          },
        })}
      />,
    );

    expect(screen.getByText("Woher: KI-Hinweis")).toBeInTheDocument();
    expect(screen.queryByText(/LLM Synthesis/i)).not.toBeInTheDocument();
  });

  it("renders the seal application profile as read-only context", () => {
    render(<DecisionUnderstandingPanel workspace={workspaceFixture()} />);

    expect(screen.getByText("Dichtungstyp-Profil")).toBeInTheDocument();
    expect(screen.getAllByText("Gleitringdichtung").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Wellendurchmesser/).length).toBeGreaterThan(0);
  });

  it("renders runtime risk strings without leaking backend dict syntax", () => {
    render(<DecisionUnderstandingPanel workspace={workspaceFixture()} />);

    expect(screen.getByText("Temperatur: hoch - Temperatur wird gegen MVP-Schwellen bewertet.")).toBeInTheDocument();
    expect(screen.queryByText(/risk name/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\{'/i)).not.toBeInTheDocument();
  });

  it("does not crash when optional backend fields are missing", () => {
    render(
      <DecisionUnderstandingPanel
        workspace={workspaceFixture({
          decisionUnderstanding: undefined,
          sealApplicationProfile: undefined,
          communication: undefined,
          completeness: {
            coverageScore: 0,
            coveragePercent: 0,
            coverageGaps: [],
            completenessDepth: "empty",
            missingCriticalParameters: [],
            analysisComplete: false,
            recommendationReady: false,
          },
          governance: {
            releaseStatus: "pending",
            releaseClass: null,
            scopeOfValidity: [],
            assumptions: [],
            unknownsBlocking: [],
            unknownsManufacturerValidation: [],
            gateFailures: [],
            notes: [],
            requiredDisclaimers: [],
            verificationPassed: false,
          },
          mediumContext: {
            ...workspaceFixture().mediumContext,
            mediumLabel: null,
            summary: null,
          },
          rfq: {
            ...workspaceFixture().rfq,
            openPoints: [],
          },
        })}
      />,
    );

    expect(screen.getByText("Sobald du einen konkreten Dichtungsfall beschreibst, zeigt SeaLAI hier den aktuellen Stand.")).toBeInTheDocument();
  });

  it("renders safe workspace facts when the dedicated decision-understanding projection is absent", () => {
    render(
      <DecisionUnderstandingPanel
        workspace={workspaceFixture({
          decisionUnderstanding: undefined,
          parameters: {
            medium: "Ethanol",
            temperature_c: 150,
            pressure_bar: 10,
            installation: "pump",
            motion_type: "rotary",
          },
          communication: {
            primaryQuestion: "Liegt der Druck direkt an der Dichtstelle an?",
            supportingReason: "Der Systemdruck ist nicht automatisch der Dichtstellendruck.",
            confirmedFactsSummary: ["Medium: Ethanol", "Temperatur: 150 °C"],
            openPointsSummary: ["Wellendurchmesser"],
          },
        })}
      />,
    );

    expect(screen.getByRole("heading", { name: "Verstanden" })).toBeInTheDocument();
    expect(screen.getAllByText("Medium: Ethanol").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Temperatur: 150 °C").length).toBeGreaterThan(0);
    expect(screen.getByText("Druck: 10 bar")).toBeInTheDocument();
    expect(screen.getByText("Liegt der Druck direkt an der Dichtstelle an?")).toBeInTheDocument();
    expect(screen.getByText("Diese Ansicht zeigt nur den aktuellen Stand. Die Auslegung muss später vom Hersteller geprüft werden.")).toBeInTheDocument();
  });

  it("does not render unsafe product copy", () => {
    render(<DecisionUnderstandingPanel workspace={workspaceFixture()} />);

    expect(screen.queryByText(/sicher passend/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/bester Hersteller/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/An Hersteller senden/i)).not.toBeInTheDocument();
  });
});
