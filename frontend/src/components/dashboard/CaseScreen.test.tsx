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
  appendAssistantMessage: vi.fn(),
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
      appendAssistantMessage: chatStoreMock.appendAssistantMessage,
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
    chatStoreMock.appendAssistantMessage.mockReset();
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

  it("renders an existing case with the cockpit overview as the first surface", () => {
    render(<CaseScreen caseId="case-42" initialRequestType="retrofit" />);

    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");
    expect(screen.getByRole("tablist", { name: "SealingAI Cockpit" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Übersicht" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Parameter" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Übersicht" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Medium" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Werkstoff" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Arbeitsbereich einklappen" })).toBeInTheDocument();
  });

  it("constrains the desktop cockpit layout so the chat composer can stay in the visible viewport", () => {
    render(<CaseScreen caseId="case-42" initialRequestType="retrofit" />);

    const chatSection = screen.getByTestId("chat-pane").closest("section");
    const layout = chatSection?.parentElement;
    const content = layout?.parentElement;
    const root = content?.parentElement;

    expect(root).toHaveClass("lg:overflow-hidden");
    expect(content).toHaveClass("min-h-0", "flex-1");
    expect(layout).toHaveClass("lg:h-full", "lg:min-h-0");
    expect(chatSection).toHaveClass("overflow-hidden", "lg:min-h-0");
  });

  it("loads the durable workspace when opening an existing case URL", async () => {
    render(<CaseScreen caseId="case-42" />);

    await waitFor(() => expect(fetchWorkspaceMock).toHaveBeenCalledWith("case-42"));
    expect(workspaceStoreMock.setWorkspaceLoading).toHaveBeenCalledWith(true);
    expect(workspaceStoreMock.setWorkspace).toHaveBeenCalledWith(
      expect.objectContaining({ caseId: "case-42" }),
    );
    expect(workspaceStoreMock.setWorkspaceLoading).toHaveBeenLastCalledWith(false);
  });

  it("keeps /dashboard/new chat-focused and opens the intake surface on demand", async () => {
    const user = userEvent.setup();

    render(<CaseScreen />);

    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane new");
    expect(screen.queryByRole("tab", { name: "Parameter" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Arbeitsbereich einblenden" })).toHaveTextContent("Arbeitsbereich öffnen");

    await user.click(screen.getByRole("button", { name: "Arbeitsbereich einblenden" }));

    expect(screen.getByRole("tab", { name: "Parameter" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "Als Nutzerangaben übernehmen" })).toBeDisabled();
    expect(screen.queryByText("Glykolhaltiges Prozessmedium")).not.toBeInTheDocument();
    expect(screen.queryByText("PTFE-RWDR vorqualifiziert")).not.toBeInTheDocument();
    expect(screen.queryByText(/PTFE-RWDR ist plausibel/i)).not.toBeInTheDocument();
    expect(screen.queryByText(["An Hersteller", "senden"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["finalisieren", "und versenden"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["Technische", "Validierung"].join(" "))).not.toBeInTheDocument();
  });

  it("maps a real workspace fixture into the RFQ workspace view", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();

    render(<CaseScreen caseId="case-42" />);

    expect(screen.getByRole("tab", { name: "Übersicht" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Direkteingabe")).toBeInTheDocument();
    expect(screen.getByText("Bekannte Parameter in den State schreiben")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Angaben zum Fall" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Was noch wichtig ist" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rechencheck" })).toBeInTheDocument();
    expect(screen.getAllByText("Wasser-Glykol").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Temperatur · °C")).toHaveValue("85");
    expect(screen.getByLabelText("Druck · bar")).toHaveValue("1.8");
    expect(screen.getByLabelText("Drehzahl · rpm")).toHaveValue("1200");
    expect(screen.getByLabelText("Welle · mm")).toHaveValue("42");
    expect(screen.getByText("2.64 m/s")).toBeInTheDocument();
    expect(screen.getByText("0.48 MPa·m/s")).toBeInTheDocument();
    expect(screen.getByText("50400")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Berechnung" }));
    expect(screen.getByText("2.64 m/s")).toBeInTheDocument();
    expect(screen.getByText("0.48 MPa·m/s")).toBeInTheDocument();
    expect(screen.getByText("50400")).toBeInTheDocument();
    expect(screen.getAllByText(/Backend-Ableitung aus Durchmesser und Drehzahl/).length).toBeGreaterThan(0);
    expect(screen.queryByText("Glykolhaltiges Prozessmedium")).not.toBeInTheDocument();
    expect(screen.queryByText(/PTFE-RWDR ist plausibel/i)).not.toBeInTheDocument();
  });

  it("switches cockpit tabs without leaving the dashboard shell", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();
    render(<CaseScreen caseId="case-42" />);

    await user.click(screen.getByRole("tab", { name: "Medium" }));
    expect(screen.getByRole("tab", { name: "Medium" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Medium" })).toBeInTheDocument());
    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");

    await user.click(screen.getByRole("tab", { name: "Werkstoff" }));
    expect(screen.getByRole("tab", { name: "Werkstoff" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Werkstoff" })).toBeInTheDocument());

    await user.click(screen.getByRole("tab", { name: "Anfragebasis" }));
    expect(screen.getByRole("tab", { name: "Anfragebasis" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Anfragebasis" })).toBeInTheDocument());
  });

  it("collapses and restores the right workspace column", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();

    render(<CaseScreen caseId="case-42" />);

    expect(screen.getByRole("tablist", { name: "SealingAI Cockpit" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Arbeitsbereich einklappen" }));

    expect(screen.queryByRole("tablist", { name: "SealingAI Cockpit" })).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");
    expect(screen.getByRole("button", { name: "Arbeitsbereich einblenden" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Arbeitsbereich einblenden" }));

    expect(screen.getByRole("tablist", { name: "SealingAI Cockpit" })).toBeInTheDocument();
  });

  it("persists prepared parameter intake values into the case file", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();
    patchAgentOverridesMock.mockResolvedValueOnce({
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
      answer_markdown: "Ich habe die Angaben eingeordnet und sehe als nächsten Punkt die Gegenlauffläche.",
      reply: null,
    });

    render(<CaseScreen caseId="case-42" />);

    await user.click(screen.getByRole("tab", { name: "Parameter" }));
    const speedInput = screen.getByLabelText("Drehzahl");
    await user.clear(speedInput);
    await user.type(speedInput, "1450");
    await user.click(screen.getByRole("button", { name: "Als Nutzerangaben übernehmen" }));

    await waitFor(() => expect(patchAgentOverridesMock).toHaveBeenCalledWith("case-42", {
      overrides: expect.arrayContaining([{ field_name: "speed_rpm", value: 1450, unit: "rpm" }]),
      run_analysis: true,
    }));
    expect(chatStoreMock.appendAssistantMessage).toHaveBeenCalledWith(
      "Ich habe die Angaben eingeordnet und sehe als nächsten Punkt die Gegenlauffläche.",
    );
    expect(fetchWorkspaceMock).toHaveBeenCalledWith("case-42");
    expect(workspaceStoreMock.setWorkspace).toHaveBeenCalledWith(expect.objectContaining({ caseId: "case-42" }));
  });

  it("sends filled intake values to the chat when no case is bound yet", async () => {
    const user = userEvent.setup();

    render(<CaseScreen />);

    await user.click(screen.getByRole("button", { name: "Arbeitsbereich einblenden" }));
    await user.type(screen.getByLabelText("Medium"), "Wasser");
    await user.type(screen.getByLabelText("Temperatur"), "80");
    await user.click(screen.getByRole("button", { name: "Als Nutzerangaben übernehmen" }));

    expect(chatStoreMock.sendMessage).toHaveBeenCalledWith(expect.stringContaining("- medium: Wasser"));
    expect(chatStoreMock.sendMessage).toHaveBeenCalledWith(expect.stringContaining("- temperature_c: 80 °C"));
    expect(patchAgentOverridesMock).not.toHaveBeenCalled();
  });
});
