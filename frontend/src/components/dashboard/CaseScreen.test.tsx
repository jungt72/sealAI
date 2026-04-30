import { render, screen } from "@testing-library/react";
import { within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";

import CaseScreen from "./CaseScreen";

const workspaceHookState = vi.hoisted((): { workspace: WorkspaceView | null } => ({
  workspace: null,
}));

const patchAgentOverridesMock = vi.hoisted(() => vi.fn());
const workspaceRefreshMock = vi.hoisted(() => vi.fn());

vi.mock("@/components/dashboard/ChatPane", () => ({
  default: ({ caseId, parameterConfirmation }: { caseId?: string; parameterConfirmation?: string | null }) => (
    <div data-testid="chat-pane">
      ChatPane {caseId ?? "new"}
      {parameterConfirmation ? <div>{parameterConfirmation}</div> : null}
    </div>
  ),
}));

vi.mock("@/lib/bff/parameterOverride", () => ({
  patchAgentOverrides: patchAgentOverridesMock,
}));

vi.mock("@/hooks/useWorkspace", () => ({
  useWorkspace: () => ({
    workspace: workspaceHookState.workspace,
    isLoading: false,
    refresh: workspaceRefreshMock,
  }),
}));

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      setWorkspace: vi.fn(),
      setWorkspaceLoading: vi.fn(),
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
    workspaceRefreshMock.mockReset();
    workspaceRefreshMock.mockResolvedValue(undefined);
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

  it("renders the open chat surface beside the tabbed SealAI cockpit", () => {
    render(<CaseScreen caseId="case-42" initialRequestType="retrofit" />);

    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");

    const tabs = screen.getByRole("tablist", { name: "SealAI Cockpit" });
    expect(within(tabs).getByRole("tab", { name: "Übersicht" })).toHaveAttribute("aria-selected", "true");
    expect(within(tabs).getByRole("tab", { name: "Parameter" })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: "Medium" })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: "Anwendung" })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: "Werkstoff" })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: "Berechnung" })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: "Briefing" })).toBeInTheDocument();
  });

  it("renders the requested overview status strip and four cockpit cards", () => {
    render(<CaseScreen caseId="case-42" />);

    expect(screen.getByText("Dichtungsfall")).toBeInTheDocument();
    expect(screen.getByText("Noch nicht eingeordnet")).toBeInTheDocument();
    expect(screen.getByText("Datenreife")).toBeInTheDocument();
    expect(screen.getByText("0 % belastbar")).toBeInTheDocument();
    expect(screen.getAllByText("Lösungsraum").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Noch offen").length).toBeGreaterThan(0);
    expect(screen.getByText("Kritische Lücken")).toBeInTheDocument();
    expect(screen.getByText("Medium · Temperatur · Anwendung · Druck · Drehzahl")).toBeInTheDocument();
    expect(screen.getByText("Berechnungsstatus")).toBeInTheDocument();
    expect(screen.getByText("0 von 5 Nachweisen belastbar")).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Parameter & Datenlage" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Kritische Treiber" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Lösung & Konsequenz" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Berechnungen & Nachweise" })).toBeInTheDocument();
  });

  it("renders an honest empty and missing state without productive mock values", () => {
    render(<CaseScreen caseId="case-42" />);

    expect(screen.getByText("Kritisch offen: Medium · Temperatur · Anwendung · Druck · Drehzahl")).toBeInTheDocument();
    expect(screen.getByText("Anfragebasis noch offen")).toBeInTheDocument();
    expect(screen.getByText("Umfangsgeschwindigkeit")).toBeInTheDocument();
    expect(screen.getAllByText("Nicht berechenbar")).toHaveLength(5);
    expect(screen.getAllByText("Fehlende Eingaben: Wellendurchmesser · Drehzahl").length).toBeGreaterThan(0);
    expect(screen.getByText(/Wichtig für Wärmeentwicklung und dynamische Beanspruchung/i)).toBeInTheDocument();

    expect(screen.queryByText("Glykolhaltiges Prozessmedium")).not.toBeInTheDocument();
    expect(screen.queryByText("PTFE-RWDR vorqualifiziert")).not.toBeInTheDocument();
    expect(screen.queryByText(/PTFE-RWDR ist plausibel/i)).not.toBeInTheDocument();
    expect(screen.queryByText("3,0 m/s")).not.toBeInTheDocument();

    expect(screen.queryByText(["An Hersteller", "senden"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["finalisieren", "und versenden"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(["Technische", "Validierung"].join(" "))).not.toBeInTheDocument();
  });

  it("renders /dashboard/new without legacy cockpit mock values", () => {
    render(<CaseScreen />);

    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane new");
    expect(screen.getByText("0 % belastbar")).toBeInTheDocument();
    expect(screen.getByText("0 von 5 Nachweisen belastbar")).toBeInTheDocument();
    expect(screen.queryByText("Glykolhaltiges Prozessmedium")).not.toBeInTheDocument();
    expect(screen.queryByText("35-90 °C")).not.toBeInTheDocument();
    expect(screen.queryByText("2,5 bar")).not.toBeInTheDocument();
    expect(screen.queryByText("1.450 rpm")).not.toBeInTheDocument();
    expect(screen.queryByText("40 mm")).not.toBeInTheDocument();
    expect(screen.queryByText(/PTFE-RWDR ist plausibel/i)).not.toBeInTheDocument();
  });

  it("maps a real workspace fixture into the cockpit ViewModel", () => {
    workspaceHookState.workspace = workspaceFixture();

    render(<CaseScreen caseId="case-42" />);

    expect(screen.getAllByText("Rotierende Welle / RWDR").length).toBeGreaterThan(0);
    expect(screen.getByText("72 % belastbar")).toBeInTheDocument();
    expect(screen.getByText("Wasser-Glykol")).toBeInTheDocument();
    expect(screen.getByText("85 °C")).toBeInTheDocument();
    expect(screen.getByText("1.8 bar")).toBeInTheDocument();
    expect(screen.getByText("1200 rpm")).toBeInTheDocument();
    expect(screen.getByText("42 mm")).toBeInTheDocument();
    expect(screen.getByText("2.64 m/s")).toBeInTheDocument();
    expect(screen.getByText("0.48 MPa·m/s")).toBeInTheDocument();
    expect(screen.getByText("50400")).toBeInTheDocument();
    expect(screen.getByText("RWDR-Arbeitsstand mit Wasser-Glykol, 85 °C und offener Gegenlauffläche.")).toBeInTheDocument();
    expect(screen.getByText("Datenherkunft: Wissensbasis")).toBeInTheDocument();
    expect(screen.getByText("Validierungsstatus: nicht validiert")).toBeInTheDocument();
    expect(screen.getAllByText("Welche Gegenlauffläche und Oberflächenrauheit sind dokumentiert?").length).toBeGreaterThan(0);
    expect(screen.getByText(/keine finale technische Freigabe/i)).toBeInTheDocument();

    expect(screen.queryByText("Glykolhaltiges Prozessmedium")).not.toBeInTheDocument();
    expect(screen.queryByText(/PTFE-RWDR ist plausibel/i)).not.toBeInTheDocument();
  });

  it("switches cockpit tabs in place without leaving the dashboard shell", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();
    render(<CaseScreen caseId="case-42" />);

    await user.click(screen.getByRole("tab", { name: "Parameter" }));

    expect(screen.getByRole("tab", { name: "Parameter" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Parameter im Fall bearbeiten" })).toBeInTheDocument();
    expect(screen.getByText(/SeaLAI übernimmt nur neue oder geänderte Angaben in den governed Case-State/i)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Berechnung" }));

    expect(screen.getByRole("tab", { name: "Berechnung" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Berechnung" })).toBeInTheDocument();
    expect(screen.getByText("2.64 m/s")).toBeInTheDocument();
    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");

    await user.click(screen.getByRole("tab", { name: "Medium" }));

    expect(screen.getByRole("heading", { name: "Medium" })).toBeInTheDocument();
    expect(screen.getByText("Wasser-Glykol")).toBeInTheDocument();
    expect(screen.queryByText(/Dieser Cockpit-Tab ist vorbereitet/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Briefing" }));

    expect(screen.getByRole("heading", { name: "Briefing" })).toBeInTheDocument();
    expect(screen.getByText(/Kompakte Anfragebasis/i)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Übersicht" }));

    expect(screen.getByRole("tab", { name: "Übersicht" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Berechnungen & Nachweise" })).toBeInTheDocument();
  });

  it("sends only changed parameter values and mirrors the governed confirmation in chat", async () => {
    const user = userEvent.setup();
    workspaceHookState.workspace = workspaceFixture();
    render(<CaseScreen caseId="case-42" />);

    await user.click(screen.getByRole("tab", { name: "Parameter" }));
    await user.clear(screen.getByLabelText("Drehzahl"));
    await user.type(screen.getByLabelText("Drehzahl"), "1450");
    await user.click(screen.getByRole("button", { name: "Als Nutzerangaben übernehmen" }));

    expect(patchAgentOverridesMock).toHaveBeenCalledWith("case-42", {
      overrides: [{ field_name: "speed_rpm", value: 1450, unit: "rpm" }],
    });
    expect(workspaceRefreshMock).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("chat-pane")).toHaveTextContent(
      "Parameter als Nutzerangaben übernommen: Drehzahl: 1450 rpm.",
    );
    expect(screen.getByTestId("chat-pane")).toHaveTextContent("offene Herstellerprüfpunkte weiter sichtbar");
  });
});
