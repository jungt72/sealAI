import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";

import { ParameterWorkspaceTab } from "./ParameterWorkspaceTab";

function workspaceFixture(): WorkspaceView {
  return {
    caseId: "case-parameter",
    requestType: "new_design",
    engineeringPath: "ms_pump",
    sealApplicationProfile: {
      sealFamily: "mechanical_face",
      sealType: "mechanical_seal",
      sealTypeConfidence: 0.9,
      confidenceBand: "high",
      matchedAlias: "Gleitringdichtung",
      ambiguous: false,
      candidateTypes: ["mechanical_seal"],
      applicationDomain: "pump",
      motionType: "rotary",
      standardRefs: [],
      typeSpecificMissingHints: [
        "pump_or_aggregate_type",
        "shaft_diameter",
        "flush_or_barrier_fluid",
        "solids_or_gas_content",
        "atex_or_leakage_requirement",
      ],
      notes: [],
      source: "seal_type_normalizer",
    },
    decisionUnderstanding: {
      caseSummary: "Pumpenfall mit Ethanol, 150 °C und 10 bar.",
      understoodNow: ["Medium Ethanol", "Temperatur 150 °C"],
      technicalMeaning: [],
      plausibleDirections: [],
      notYetDecidable: ["Dichtstellendruck unklar"],
      keyRisks: [],
      confidenceNotes: [],
      nextBestQuestion: "Ist eine Spülung, Sperrflüssigkeit oder Barriere vorgesehen?",
      manufacturerReviewNeeds: [],
      needsAnalysis: {
        primaryNeed: "prepare_manufacturer_review_ready_rfq_basis",
        secondaryNeeds: ["rfq_readiness"],
        urgency: "normal",
        userSide: null,
        contextSide: null,
        confidence: 0.6,
        notes: [],
      },
      currentStateAnalysis: {
        knownFields: ["medium", "temperature", "pressure"],
        missingFields: ["flush_or_barrier_fluid", "solids_or_gas_content"],
        uncertainFields: [],
        conflictingFields: [],
        evidenceBackedFields: [],
        sealTypeStatus: "known_not_confirmed",
        readinessHint: "precheck",
        confidence: 0.5,
      },
      nextBestQuestions: [
        {
          question: "Ist eine Spülung, Sperrflüssigkeit oder Barriere vorgesehen?",
          reason: "Bei Gleitringdichtungen beeinflusst die Versorgung das Dichtprinzip und die Prüfbarkeit.",
          focusKey: "flush_or_barrier_fluid",
          priority: 1,
          expectedAnswerType: "text",
          appliesToCaseType: "new_rfq",
          appliesToSealType: "mechanical_seal",
          source: "next_best_question_service",
          maxQuestionsPolicy: "ask_1_to_3_targeted_questions",
        },
      ],
      completenessScore: {
        score: 0.5,
        missingCriticalCount: 2,
        knownCriticalCount: 3,
        uncertaintyCount: 0,
        conflictCount: 0,
        notes: [],
      },
    },
    parameters: {
      medium: "Ethanol",
      temperature_c: 150,
      pressure_bar: 10,
      speed_rpm: null,
      shaft_diameter_mm: null,
      installation: "Pumpe",
      sealing_type: "mechanical_seal",
      counterface_surface: null,
    },
    cockpit: {
      path: "rwdr",
      requestType: "new_design",
      routingMetadata: { phase: "clarification", lastNode: "workspace", routing: {} },
      sections: {
        application_function: {
          id: "application_function",
          title: "1. Anlage & Funktion",
          completion: { mandatoryPresent: 1, mandatoryTotal: 1, percent: 100 },
          properties: [
            {
              key: "installation",
              label: "Anlage",
              value: "Pumpe",
              origin: "user_stated",
              confidence: "confirmed",
              sourceType: "user_stated",
              validationStatus: "user_stated",
              isConfirmed: true,
              isMandatory: true,
            },
          ],
        },
        medium_environment: {
          id: "medium_environment",
          title: "2. Medium & Umgebung",
          completion: { mandatoryPresent: 1, mandatoryTotal: 1, percent: 100 },
          properties: [
            {
              key: "medium",
              label: "Medium",
              value: "Ethanol",
              origin: "user_stated",
              confidence: "confirmed",
              sourceType: "user_stated",
              validationStatus: "user_stated",
              isConfirmed: true,
              isMandatory: true,
            },
            {
              key: "temperature_c",
              label: "Temperatur",
              value: 150,
              unit: "°C",
              origin: "user_stated",
              confidence: "confirmed",
              sourceType: "user_stated",
              validationStatus: "user_stated",
              isConfirmed: true,
              isMandatory: true,
            },
            {
              key: "pressure_bar",
              label: "Druck",
              value: 10,
              unit: "bar",
              origin: "llm_research_fallback",
              confidence: "candidate",
              sourceType: "llm_research_fallback",
              validationStatus: "unvalidated",
              isConfirmed: false,
              isMandatory: true,
            },
          ],
        },
        operating_geometry: {
          id: "operating_geometry",
          title: "3. Betriebsdaten & Geometrie",
          completion: { mandatoryPresent: 0, mandatoryTotal: 2, percent: 0 },
          properties: [],
        },
        risk_readiness: {
          id: "risk_readiness",
          title: "4. Risiken & Anfrage-Reife",
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 100 },
          properties: [],
        },
      },
      checks: [],
      riskEvaluations: [],
      readiness: {
        isRfqReady: false,
        missingMandatoryKeys: ["speed_rpm"],
        blockers: [],
        status: "preliminary",
      },
      mediumContext: {
        canonicalName: "Ethanol",
        isConfirmed: false,
        properties: [],
        riskFlags: [],
      },
    },
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
      coverageScore: 0.5,
      coveragePercent: 50,
      coverageGaps: ["speed_rpm", "shaft_diameter_mm"],
      completenessDepth: "prequalification",
      missingCriticalParameters: ["speed_rpm"],
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
    mediumCapture: {
      rawMentions: [],
      primaryRawText: null,
      sourceTurnRef: null,
      sourceTurnIndex: null,
    },
    mediumClassification: {
      canonicalLabel: "Ethanol",
      family: "solvent",
      confidence: "medium",
      status: "available",
      normalizationSource: "backend",
      mappingConfidence: "medium",
      matchedAlias: null,
      sourceRegistryKey: null,
      followupQuestion: null,
    },
    mediumContext: {
      mediumLabel: "Ethanol",
      status: "available",
      scope: "case",
      summary: null,
      properties: [],
      challenges: [],
      followupPoints: [],
      confidence: "medium",
      sourceType: "user_stated",
      validationStatus: "user_stated",
      notForReleaseDecisions: true,
      disclaimer: null,
    },
    deepDiveTabs: [],
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
      dataSource: "none",
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
  };
}

describe("ParameterWorkspaceTab", () => {
  it("renders parameter explanations and current case values", () => {
    render(<ParameterWorkspaceTab workspace={workspaceFixture()} onSubmit={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Angaben direkt eintragen" })).toBeInTheDocument();
    expect(screen.getByLabelText("Medium")).toHaveValue("Ethanol");
    expect(screen.getByLabelText("Temperatur")).toHaveValue("150");
    expect(screen.getByText(/Das Medium beeinflusst Werkstoff/i)).toBeInTheDocument();
    expect(screen.getByText(/Hersteller muss später prüfen/i)).toBeInTheDocument();
    expect(screen.getAllByText("Woher: Nutzerangabe").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Status: Nutzerangabe").length).toBeGreaterThan(0);
    expect(screen.getByText("Woher: KI-Hinweis")).toBeInTheDocument();
    expect(screen.getByText("Status: noch nicht geprüft")).toBeInTheDocument();
    expect(screen.getAllByText("bestätigt").length).toBeGreaterThan(0);
    expect(screen.getByText("Passende Zusatzangaben")).toBeInTheDocument();
    expect(screen.getByText("Pumpe / Aggregat")).toBeInTheDocument();
    expect(screen.getByText("Spülung / Sperrmedium")).toBeInTheDocument();
    expect(screen.getByText(/Ist eine Spülung, Sperrflüssigkeit oder Barriere vorgesehen/i)).toBeInTheDocument();
  });

  it("submits canonical user override fields for governed state processing", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<ParameterWorkspaceTab workspace={workspaceFixture()} onSubmit={onSubmit} />);

    await user.clear(screen.getByLabelText("Drehzahl"));
    await user.type(screen.getByLabelText("Drehzahl"), "1450");
    await user.clear(screen.getByLabelText("Wellendurchmesser"));
    await user.type(screen.getByLabelText("Wellendurchmesser"), "42");
    await user.click(screen.getByRole("button", { name: "Als Nutzerangaben übernehmen" }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const [overrides, summary] = onSubmit.mock.calls[0];
    expect(overrides).toEqual(
      expect.arrayContaining([
        { field_name: "speed_rpm", value: 1450, unit: "rpm" },
        { field_name: "shaft_diameter_mm", value: 42, unit: "mm" },
      ]),
    );
    expect(overrides).not.toEqual(expect.arrayContaining([{ field_name: "medium", value: "Ethanol", unit: null }]));
    expect(summary).toContain("Drehzahl: 1450 rpm");
    expect(summary).toContain("Wellendurchmesser: 42 mm");
    expect(screen.getAllByText("Status: wird als Nutzerangabe übernommen")).toHaveLength(2);
    expect(screen.getAllByText("Woher: Nutzerangabe").length).toBeGreaterThan(0);
  });

  it("guards numeric fields before sending overrides", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<ParameterWorkspaceTab workspace={workspaceFixture()} onSubmit={onSubmit} />);

    await user.clear(screen.getByLabelText("Druck"));
    await user.type(screen.getByLabelText("Druck"), "hoch");
    await user.click(screen.getByRole("button", { name: "Als Nutzerangaben übernehmen" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Druck braucht einen numerischen Wert.")).toBeInTheDocument();
  });

  it("does not submit unchanged projected values as overrides", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<ParameterWorkspaceTab workspace={workspaceFixture()} onSubmit={onSubmit} />);

    await user.click(screen.getByRole("button", { name: "Als Nutzerangaben übernehmen" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Keine neuen oder geänderten Parameter erkannt.")).toBeInTheDocument();
  });
});
