import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";

import CaseScreen from "./CaseScreen";

const workspaceHookState = vi.hoisted((): { workspace: WorkspaceView | null } => ({
  workspace: null,
}));

const patchAgentOverridesMock = vi.hoisted(() => vi.fn());
const fetchWorkspaceMock = vi.hoisted(() => vi.fn());
const workspaceStoreMock = vi.hoisted(() => ({
  userParameterOverrides: {} as Record<string, string>,
  activeResponseClass: null as string | null,
  streamWorkspace: null,
  streamAssertions: null,
  setWorkspace: vi.fn(),
  setWorkspaceLoading: vi.fn(),
  setUserParameterOverride: vi.fn(),
  resetUserParameterOverrides: vi.fn(),
  setMediumIntelligence: vi.fn(),
  setMediumIntelligenceLoading: vi.fn(),
  setMediumIntelligenceFor: vi.fn(),
  setMediumIntelligenceResult: vi.fn(),
}));
const chatStoreMock = vi.hoisted(() => ({
  activeCaseId: null as string | null,
  sendMessage: vi.fn(),
  isStreaming: false,
}));

vi.mock("@/components/dashboard/ChatPane", () => ({
  default: ({ caseId }: { caseId?: string }) => <div data-testid="chat-pane">ChatPane {caseId ?? "new"}</div>,
}));

vi.mock("@/lib/bff/parameterOverride", () => ({
  patchAgentOverrides: patchAgentOverridesMock,
}));

vi.mock("@/lib/bff/workspace", () => ({
  fetchWorkspace: fetchWorkspaceMock,
}));

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      workspace: workspaceHookState.workspace,
      streamWorkspace: workspaceStoreMock.streamWorkspace,
      streamAssertions: workspaceStoreMock.streamAssertions,
      userParameterOverrides: workspaceStoreMock.userParameterOverrides,
      activeResponseClass: workspaceStoreMock.activeResponseClass,
      mediumIntelligence: null,
      mediumIntelligenceLoading: false,
      mediumIntelligenceFor: null,
      setWorkspace: workspaceStoreMock.setWorkspace,
      setWorkspaceLoading: workspaceStoreMock.setWorkspaceLoading,
      setUserParameterOverride: workspaceStoreMock.setUserParameterOverride,
      resetUserParameterOverrides: workspaceStoreMock.resetUserParameterOverrides,
      setMediumIntelligence: workspaceStoreMock.setMediumIntelligence,
      setMediumIntelligenceLoading: workspaceStoreMock.setMediumIntelligenceLoading,
      setMediumIntelligenceFor: workspaceStoreMock.setMediumIntelligenceFor,
      setMediumIntelligenceResult: workspaceStoreMock.setMediumIntelligenceResult,
    }),
}));

vi.mock("@/lib/store/chatStore", () => ({
  useChatStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      activeCaseId: chatStoreMock.activeCaseId,
      sendMessage: chatStoreMock.sendMessage,
      isStreaming: chatStoreMock.isStreaming,
    }),
}));

function workspaceFixture(): WorkspaceView {
  return {
    caseId: "case-42",
    requestType: "retrofit",
    engineeringPath: "rwdr",
    cockpit: null,
    communication: {
      conversationPhase: "clarification",
      primaryQuestion: "Welche Gegenlauffläche ist dokumentiert?",
      supportingReason: "Temperatur und Drehzahl erlauben eine erste Belastungseinordnung, aber die Oberfläche bleibt prüfungsrelevant.",
      confirmedFactsSummary: ["Medium: Wasser-Glykol"],
      openPointsSummary: ["Gegenlauffläche"],
    },
    parameters: {
      medium: "Wasser-Glykol",
      temperature_c: 85,
      pressure_bar: 1.8,
      sealing_type: "RWDR",
      shaft_diameter_mm: 42,
      speed_rpm: 1200,
      geometry_context: "rotierende Welle im Pumpenkopf",
      counterface_surface: "noch zu bestätigen",
      motion_type: "rotary",
    },
    lifecycle: {
      currentStep: null,
      completedSteps: [],
      steps: [],
    },
    summary: {
      turnCount: 3,
      maxTurns: 12,
      analysisCycleId: 1,
      stateRevision: 2,
      assertedProfileRevision: 1,
      derivedArtifactsStale: false,
      staleReason: null,
    },
    completeness: {
      coverageScore: 0.72,
      coveragePercent: 72,
      coverageGaps: ["counterface_surface"],
      completenessDepth: "prequalification",
      missingCriticalParameters: ["runout_mm"],
      analysisComplete: false,
      recommendationReady: false,
    },
    governance: {
      releaseStatus: "manufacturer_validation_required",
      releaseClass: "C",
      scopeOfValidity: [],
      assumptions: [],
      unknownsBlocking: [],
      unknownsManufacturerValidation: ["Gegenlauffläche"],
      gateFailures: [],
      notes: [],
      requiredDisclaimers: ["Keine finale technische Freigabe."],
      verificationPassed: true,
    },
    mediumCapture: {
      rawMentions: ["Wasser-Glykol"],
      primaryRawText: "Wasser-Glykol",
      sourceTurnRef: "turn-1",
      sourceTurnIndex: 1,
    },
    mediumClassification: {
      canonicalLabel: "Wasser-Glykol",
      family: "glycol_water",
      confidence: "medium",
      status: "available",
      normalizationSource: "backend",
      mappingConfidence: "medium",
      matchedAlias: null,
      sourceRegistryKey: null,
      followupQuestion: null,
    },
    mediumContext: {
      mediumLabel: "Wasser-Glykol",
      status: "available",
      scope: "case",
      summary: "Medium für Herstellerprüfung dokumentieren.",
      properties: ["wasserbasiert"],
      challenges: ["Schmierfähigkeit"],
      followupPoints: [],
      confidence: "medium",
      sourceType: "rag_verified",
      validationStatus: "user_stated",
      notForReleaseDecisions: true,
      disclaimer: "Herstellerprüfung erforderlich.",
    },
    sealApplicationProfile: {
      sealFamily: "radial_shaft_seal",
      sealType: "radial_shaft_seal",
      sealTypeConfidence: 0.82,
      confidenceBand: "high",
      matchedAlias: "RWDR",
      ambiguous: false,
      candidateTypes: [],
      applicationDomain: "shaft_sealing",
      motionType: "rotary",
      standardRefs: [],
      typeSpecificMissingHints: ["counterface_surface"],
      notes: [],
      source: "seal_type_normalizer",
    },
    decisionUnderstanding: {
      caseSummary: "RWDR-Arbeitsstand mit Wasser-Glykol, 85 °C und offener Gegenlauffläche.",
      understoodNow: ["Medium: Wasser-Glykol", "Drehzahl: 1200 rpm"],
      technicalMeaning: ["Die Gegenlauffläche bleibt prüfungsrelevant."],
      plausibleDirections: ["RWDR-Anfragebasis für Herstellerprüfung"],
      notYetDecidable: ["Oberflächenqualität"],
      keyRisks: ["Gegenlauffläche offen"],
      confidenceNotes: ["Datenlage ist vorläufig."],
      nextBestQuestion: "Welche Gegenlauffläche und Oberflächenrauheit sind dokumentiert?",
      manufacturerReviewNeeds: ["Gegenlauffläche bestätigen"],
      needsAnalysis: {
        primaryNeed: "retrofit",
        secondaryNeeds: ["technical_clarification"],
        urgency: "normal",
        userSide: "buyer",
        contextSide: "maintenance",
        confidence: 0.72,
        notes: [],
      },
      currentStateAnalysis: {
        knownFields: ["medium", "temperature_c", "speed_rpm"],
        missingFields: ["counterface_surface"],
        uncertainFields: [],
        conflictingFields: [],
        evidenceBackedFields: ["calculated_speed"],
        sealTypeStatus: "candidate",
        readinessHint: "prequalification",
        confidence: 0.72,
      },
      nextBestQuestions: [
        {
          question: "Welche Gegenlauffläche und Oberflächenrauheit sind dokumentiert?",
          reason: "Die Dichtkante hängt stark an Oberfläche und Gegenlauffläche.",
          focusKey: "counterface_surface",
          priority: 1,
          expectedAnswerType: "text",
          appliesToCaseType: "retrofit",
          appliesToSealType: "radial_shaft_seal",
          source: "next_best_question_service",
          maxQuestionsPolicy: "ask_1_to_3_targeted_questions",
        },
      ],
      completenessScore: {
        score: 0.72,
        missingCriticalCount: 1,
        knownCriticalCount: 5,
        uncertaintyCount: 1,
        conflictCount: 0,
        notes: [],
      },
    },
    technicalDerivations: [
      {
        calcType: "rwdr",
        status: "ok",
        vSurfaceMPerS: 2.64,
        pvValueMpaMPerS: 0.48,
        dnValue: 50400,
        temperatureHeadroomC: null,
        notes: ["Backend-Ableitung aus Durchmesser und Drehzahl."],
      },
    ],
    deepDiveTabs: [
      {
        tabId: "analysis",
        label: "Analyse",
        status: "available",
        detected: ["RWDR"],
        relevance: "Herstellerprüfung vorbereiten.",
        opportunities: [],
        risks: ["Gegenlauffläche offen"],
        derivedDirection: "RWDR-Anfragebasis für Herstellerprüfung, keine finale technische Freigabe.",
        missing: ["counterface_surface"],
        nextAction: "Gegenlauffläche klären",
        returnToAnalysis: "Zurück zur Analyse",
        cards: [],
      },
    ],
    specificity: {
      materialSpecificityRequired: "compound_required",
      completenessDepth: "prequalification",
      elevationPossible: true,
      elevationTarget: "compound_required",
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
      deterministicFindings: ["v_surface_m_s"],
      assumptionBasedFindings: [],
      unresolvedOpenPoints: ["counterface_surface"],
      evidenceGaps: ["counterface_surface"],
    },
    manufacturerQuestions: {
      mandatory: ["Welche Gegenlauffläche und Oberflächenrauheit sind dokumentiert?"],
      openQuestions: [],
      totalOpen: 1,
    },
    matching: {
      ready: false,
      shortlistReady: false,
      inquiryReady: false,
      notReadyReasons: [],
      blockingReasons: ["manufacturer_validation_required"],
      items: [],
      openManufacturerQuestions: [],
      selectedPartnerId: null,
      dataSource: "none",
    },
    rfq: {
      status: "draft",
      rfq_ready: false,
      releaseStatus: "manufacturer_validation_required",
      confirmed: false,
      blockers: ["counterface_surface"],
      openPoints: ["counterface_surface"],
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

describe("CaseScreen", () => {
  beforeEach(() => {
    workspaceHookState.workspace = null;
    workspaceStoreMock.userParameterOverrides = {};
    workspaceStoreMock.activeResponseClass = null;
    workspaceStoreMock.streamWorkspace = null;
    workspaceStoreMock.streamAssertions = null;
    chatStoreMock.activeCaseId = null;
    chatStoreMock.isStreaming = false;
    chatStoreMock.sendMessage.mockReset();
    workspaceStoreMock.setWorkspace.mockReset();
    workspaceStoreMock.setWorkspaceLoading.mockReset();
    workspaceStoreMock.setUserParameterOverride.mockReset();
    workspaceStoreMock.resetUserParameterOverrides.mockReset();
    workspaceStoreMock.setMediumIntelligence.mockReset();
    workspaceStoreMock.setMediumIntelligenceLoading.mockReset();
    workspaceStoreMock.setMediumIntelligenceFor.mockReset();
    workspaceStoreMock.setMediumIntelligenceResult.mockReset();
    fetchWorkspaceMock.mockReset();
    fetchWorkspaceMock.mockResolvedValue(workspaceFixture());
    patchAgentOverridesMock.mockReset();
    patchAgentOverridesMock.mockResolvedValue({
      session_id: "case-42",
      applied_fields: ["speed_rpm"],
      governance: {
        gov_class: "B",
        rfq_admissible: false,
        blocking_unknowns: [],
        conflict_flags: [],
        validity_limits: [],
        open_validation_points: [],
      },
    });
  });

  it("renders chat and the persistent RFQ workspace with parameter intake", () => {
    render(<CaseScreen caseId="case-42" initialRequestType="retrofit" />);

    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");
    expect(screen.getByRole("heading", { name: "RFQ-Qualifikationsraum" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Schnelleingabe für vorbereitete Fälle" })).toBeInTheDocument();
    expect(screen.getByLabelText("Medium")).toBeInTheDocument();
    expect(screen.getByLabelText("Drehzahl")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "In Fallakte speichern" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Mit sealingAI analysieren" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Anfragebasis" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "Parameter & Application" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Medium Intelligence" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Calculations" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Open Points / Next Step" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Arbeitsbereich einklappen" })).toBeInTheDocument();
  });

  it("keeps /dashboard/new free of legacy mock values while showing the new intake surface", () => {
    render(<CaseScreen />);

    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane new");
    expect(screen.getByRole("heading", { name: "RFQ-Qualifikationsraum" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mit sealingAI analysieren" })).toBeDisabled();
    expect(screen.queryByText("Glykolhaltiges Prozessmedium")).not.toBeInTheDocument();
    expect(screen.queryByText("PTFE-RWDR vorqualifiziert")).not.toBeInTheDocument();
    expect(screen.queryByText(/PTFE-RWDR ist plausibel/i)).not.toBeInTheDocument();
    expect(screen.queryByText(["An Hersteller", "senden"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["finalisieren", "und versenden"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["Technische", "Validierung"].join(" "))).not.toBeInTheDocument();
  });

  it("maps a real workspace fixture into the RFQ workspace view", () => {
    workspaceHookState.workspace = workspaceFixture();

    render(<CaseScreen caseId="case-42" />);

    expect(screen.getAllByText("72%").length).toBeGreaterThan(0);
    expect(screen.getByText("Wasser-Glykol")).toBeInTheDocument();
    expect(screen.getByText("85 °C")).toBeInTheDocument();
    expect(screen.getByText("1.8 bar")).toBeInTheDocument();
    expect(screen.getByText("1200 rpm")).toBeInTheDocument();
    expect(screen.getByText("42 mm")).toBeInTheDocument();
    expect(screen.getByText("2.64")).toBeInTheDocument();
    expect(screen.getByText("0.48")).toBeInTheDocument();
    expect(screen.getByText("50400")).toBeInTheDocument();
    expect(screen.getAllByText("Gegenlauffläche").length).toBeGreaterThan(0);
    expect(screen.queryByText("Glykolhaltiges Prozessmedium")).not.toBeInTheDocument();
    expect(screen.queryByText(/PTFE-RWDR ist plausibel/i)).not.toBeInTheDocument();
  });

  it("switches workspace modes without leaving the dashboard shell", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();
    render(<CaseScreen caseId="case-42" />);

    await user.click(screen.getByRole("button", { name: "Vergleich" }));
    expect(screen.getByRole("button", { name: "Vergleich" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Vergleich NBR vs PTFE" })).toBeInTheDocument());
    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");

    await user.click(screen.getByRole("button", { name: "Deep Dive" }));
    expect(screen.getByRole("button", { name: "Deep Dive" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Material Profile" })).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Anfragebasis" }));
    expect(screen.getByRole("button", { name: "Anfragebasis" })).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Parameter & Application" })).toBeInTheDocument());
  });

  it("collapses and restores the right workspace column", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();

    render(<CaseScreen caseId="case-42" />);

    expect(screen.getByRole("heading", { name: "RFQ-Qualifikationsraum" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Arbeitsbereich einklappen" }));

    expect(screen.queryByRole("heading", { name: "RFQ-Qualifikationsraum" })).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");
    expect(screen.getByRole("button", { name: "Arbeitsbereich einblenden" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Arbeitsbereich einblenden" }));

    expect(screen.getByRole("heading", { name: "RFQ-Qualifikationsraum" })).toBeInTheDocument();
  });

  it("persists prepared parameter intake values into the case file", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();
    workspaceStoreMock.userParameterOverrides = {
      speed_rpm: "1450",
    };

    render(<CaseScreen caseId="case-42" />);

    expect(screen.getByLabelText("Drehzahl")).toHaveValue("1450");
    await user.click(screen.getByRole("button", { name: "In Fallakte speichern" }));

    await waitFor(() => expect(patchAgentOverridesMock).toHaveBeenCalledWith("case-42", {
      overrides: expect.arrayContaining([{ field_name: "speed_rpm", value: 1450, unit: "rpm" }]),
    }));
    expect(fetchWorkspaceMock).toHaveBeenCalledWith("case-42");
    expect(workspaceStoreMock.setWorkspace).toHaveBeenCalledWith(expect.objectContaining({ caseId: "case-42" }));
    expect(screen.getByText("1 Parameter in der Fallakte gespeichert.")).toBeInTheDocument();
  });

  it("sends filled intake values to the chat when no case is bound yet", async () => {
    const user = userEvent.setup();
    workspaceStoreMock.userParameterOverrides = {
      medium: "Wasser",
      temperature_c: "80",
    };

    render(<CaseScreen />);

    await user.click(screen.getByRole("button", { name: "Mit sealingAI analysieren" }));

    expect(chatStoreMock.sendMessage).toHaveBeenCalledWith(expect.stringContaining("- Medium: Wasser"));
    expect(chatStoreMock.sendMessage).toHaveBeenCalledWith(expect.stringContaining("- Temperatur: 80"));
    expect(patchAgentOverridesMock).not.toHaveBeenCalled();
  });
});
