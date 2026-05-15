import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";
import type { SealCockpitOverview } from "@/lib/engineering/sealCockpitViewModel";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

import {
  ChallengeIntelligencePanel,
  DesignIntakePanel,
  SealCockpit,
  V91IntelligencePanel,
} from "./SealCockpit";

function workspaceWithDesignIntake(overrides: Partial<WorkspaceView["designIntake"]> = {}): WorkspaceView {
  return {
    caseId: "case-design",
    designIntake: {
      schemaVersion: "seal_design_intake_v0.8.3",
      status: "minimal_dataset_missing",
      knownFields: [
        {
          key: "medium",
          label: "Medium",
          status: "provided_not_released",
          criticality: "critical",
          value: "HLP 46",
          reason: "Medium bestimmt den Nachweisbedarf.",
        },
      ],
      missingFields: [
        {
          key: "leakage_target",
          label: "Leckageziel",
          status: "not_specified",
          criticality: "critical",
          value: null,
          reason: "Ohne Leckageziel bleibt die Anfrage offen.",
        },
      ],
      screeningChecks: [
        {
          checkId: "oring.squeeze_pct",
          label: "Verpressung",
          status: "screening_ok",
          value: 15.5,
          unit: "%",
          inputs: ["cross_section_mm", "groove_depth_mm"],
          message: "Vorprüfung.",
        },
      ],
      escalationTriggers: [
        {
          triggerId: "high_pressure_large_gap",
          label: "Hochdruck und grosser Spalt",
          severity: "critical",
          reason: "Stützringbedarf prüfen.",
        },
      ],
      nextRequiredFields: ["leakage_target"],
      boundaryNotice: "Read-only Vorqualifikation fuer Herstellerpruefung.",
      eventNames: ["SealDesignIntakeGenerated"],
      ...overrides,
    },
  } as unknown as WorkspaceView;
}

describe("DesignIntakePanel", () => {
  it("renders read-only design intake facts from the backend projection", () => {
    render(<DesignIntakePanel workspace={workspaceWithDesignIntake()} />);

    expect(screen.getByRole("heading", { name: "Neuauslegung" })).toBeInTheDocument();
    expect(screen.getByText("Mindestdaten fehlen")).toBeInTheDocument();
    expect(screen.getByText("Medium: HLP 46")).toBeInTheDocument();
    expect(screen.getByText("Leckageziel")).toBeInTheDocument();
    expect(screen.getByText(/Verpressung: 15.5 %/)).toBeInTheDocument();
    expect(screen.getByText(/Hochdruck und grosser Spalt/)).toBeInTheDocument();
    expect(screen.getByText(/Read-only Vorqualifikation/)).toBeInTheDocument();
  });

  it("stays hidden until backend projection contains design-intake content", () => {
    const workspace = workspaceWithDesignIntake({
      status: "no_design_dataset",
      knownFields: [],
      missingFields: [],
      screeningChecks: [],
      escalationTriggers: [],
      nextRequiredFields: [],
    });

    render(<DesignIntakePanel workspace={workspace} />);

    expect(screen.queryByRole("heading", { name: "Neuauslegung" })).not.toBeInTheDocument();
  });
});

function workspaceWithChallengeIntelligence(): WorkspaceView {
  return {
    caseId: "case-challenge",
    challengeIntelligence: {
      schemaVersion: "challenge_engine_v9.0",
      status: "available",
      findings: [
        {
          findingId: "missing.pressure_bar.0",
          kind: "missing_information",
          severity: "blocking",
          status: "open",
          title: "Druck oder Druckdifferenz fehlt für eine belastbare Einordnung",
          summary: "Druck oder Druckdifferenz ist noch nicht als belastbarer Wert im Fall vorhanden.",
          rfqRelevance: "Der Punkt gehört sichtbar in die Anfragebasis.",
          relatedFields: ["pressure_bar"],
          evidenceRefIds: [],
          actionMode: "ASK_NEXT_BEST_QUESTION",
          source: "challenge_engine_v9",
        },
      ],
      hypotheses: [
        {
          hypothesisId: "hypothesis.ptfe",
          label: "PTFE als Prüfhypothese",
          plausibilityClass: "medium",
          status: "active",
          basis: ["Salzhaltiges Wasser verlangt frühe Prüfung."],
          counterindicators: ["Kriechen, Füllung und Vorspannung bleiben offen."],
          blockingUnknowns: ["Druck"],
          requiredChecks: ["Mediumdatenblatt"],
          rfqRelevance: "Nur als Kontext für die Herstellerprüfung sichtbar machen.",
          forbiddenClaims: ["geeignet", "freigegeben"],
          source: "challenge_engine_v9",
        },
      ],
      nextBestQuestion: {
        question: "Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
        reason: "Der Druck verschiebt Bauform, Stützringbedarf und Spaltmaß.",
        focusKey: "pressure_bar",
        priority: 1,
        expectedAnswerType: "number",
        closesFindings: ["missing.pressure_bar.0"],
        source: "challenge_engine_v9",
        maxQuestionsPolicy: "ask_one_highest_leverage_question",
      },
      actionModesRun: ["CHALLENGE_KNOWN_INPUTS", "ASK_NEXT_BEST_QUESTION"],
      boundaryNotice: "Prüfhypothesen dienen der technischen Vorqualifikation; keine Freigabe.",
    },
  } as unknown as WorkspaceView;
}

describe("ChallengeIntelligencePanel", () => {
  it("renders V9 findings, hypotheses and the next best question", () => {
    render(<ChallengeIntelligencePanel workspace={workspaceWithChallengeIntelligence()} />);

    expect(screen.getByRole("heading", { name: "Challenger" })).toBeInTheDocument();
    expect(screen.getByText("Nächste beste Frage")).toBeInTheDocument();
    expect(screen.getByText(/Welcher Druck oder welche Druckdifferenz/)).toBeInTheDocument();
    expect(screen.getByText(/Druck oder Druckdifferenz fehlt/)).toBeInTheDocument();
    expect(screen.getByText("PTFE als Prüfhypothese")).toBeInTheDocument();
    expect(screen.getAllByText("Blocker")[0]).toBeInTheDocument();
    expect(screen.getByText("Gegenchecks")).toBeInTheDocument();
    expect(screen.getByText("Aktionen")).toBeInTheDocument();
    expect(screen.getByText("offene Angabe")).toBeInTheDocument();
    expect(screen.getAllByText("Druck")[0]).toBeInTheDocument();
    expect(screen.getAllByText("nächste Frage")[0]).toBeInTheDocument();
    expect(screen.getByText(/RFQ: Der Punkt gehört sichtbar/)).toBeInTheDocument();
    expect(screen.getByText("Mediumdatenblatt")).toBeInTheDocument();
    expect(screen.getByText(/keine Freigabe/)).toBeInTheDocument();
  });

  it("stays hidden until the backend challenge projection is available", () => {
    render(
      <ChallengeIntelligencePanel workspace={{ caseId: "empty" } as unknown as WorkspaceView} />,
    );

    expect(screen.queryByRole("heading", { name: "Challenger" })).not.toBeInTheDocument();
  });
});

describe("V91IntelligencePanel", () => {
  it("renders backend-owned intelligence slices and next action", () => {
    const workspace = {
      caseId: "case-v91",
      communication: {
        primaryQuestion: "Welches Medium berührt die Dichtung genau?",
      },
      v91Workspace: {
        intelligenceState: {
          schemaVersion: "sealing_intelligence_v9_1",
          caseRevision: 3,
          overallStatus: "review_needed",
          medium: {
            sliceId: "medium",
            status: "available",
            claimLevel: "screening",
            summary: "Salzwasser ist korrosiv relevant.",
            signals: ["salzhaltig"],
            blockers: ["Konzentration fehlt"],
            evidenceRefIds: [],
            notForReleaseDecisions: true,
            source: "workspace_projection_v9_1",
          },
          material: {
            sliceId: "material",
            status: "insufficient_context",
            claimLevel: "screening",
            summary: "Werkstoff-Screening braucht mehr Fallkontext.",
            signals: [],
            blockers: [],
            evidenceRefIds: [],
            notForReleaseDecisions: true,
            source: "workspace_projection_v9_1",
          },
          challenge: {
            sliceId: "challenge",
            status: "available",
            claimLevel: "case_projection",
            summary: "Ein kritischer Befund.",
            signals: ["Druck fehlt"],
            blockers: ["Druck fehlt"],
            evidenceRefIds: [],
            notForReleaseDecisions: true,
            source: "workspace_projection_v9_1",
          },
          document: {
            sliceId: "document",
            status: "documented",
            claimLevel: "screening",
            summary: "2 Dokumentpunkte sichtbar.",
            signals: ["PTFE Deep Research"],
            blockers: [],
            evidenceRefIds: [],
            notForReleaseDecisions: true,
            source: "workspace_projection_v9_1",
          },
          rfq: {
            sliceId: "rfq",
            status: "not_ready",
            claimLevel: "manufacturer_review",
            summary: "Anfragebasis bleibt blockiert.",
            signals: [],
            blockers: ["Druck fehlt"],
            evidenceRefIds: [],
            notForReleaseDecisions: true,
            source: "workspace_projection_v9_1",
          },
        },
        tabState: [
          {
            tabId: "overview",
            label: "Überblick",
            status: "review_needed",
            sourceSliceId: "challenge",
            summary: "Überblick",
            primaryItems: [],
            warnings: ["Druck fehlt"],
            nextAction: "Welcher Druck liegt an?",
            evidenceRefIds: [],
            notForReleaseDecisions: true,
          },
        ],
      },
    } as unknown as WorkspaceView;

    render(<V91IntelligencePanel workspace={workspace} />);

    expect(screen.getByRole("heading", { name: "Sealing Intelligence" })).toBeInTheDocument();
    expect(screen.getByText("Prüfung nötig")).toBeInTheDocument();
    expect(screen.getByText("Salzwasser ist korrosiv relevant.")).toBeInTheDocument();
    expect(screen.getByText(/Nächster sinnvoller Schritt/)).toBeInTheDocument();
    expect(screen.getByText("Welcher Druck liegt an?")).toBeInTheDocument();
  });
});

const cockpitData: SealCockpitOverview = {
  tabs: [
    { id: "overview", label: "Übersicht" },
    { id: "parameters", label: "Parameter" },
    { id: "medium", label: "Medium" },
    { id: "application", label: "Anwendung" },
    { id: "material", label: "Werkstoff" },
    { id: "calculation", label: "Berechnung" },
    { id: "briefing", label: "Briefing" },
  ],
  statusStrip: [],
  parameters: { rows: [], warning: "" },
  criticalDrivers: [],
  solution: { assessmentTitle: "", assessment: "", rows: [] },
  calculations: [],
  footerNote: "",
};

function workspaceWithMedium(): WorkspaceView {
  return {
    caseId: "case-medium",
    parameters: { medium: "Salzwasser" },
    mediumClassification: {
      canonicalLabel: "Salzwasser",
      family: "waessrig_salzhaltig",
      confidence: "medium",
      status: "recognized",
      normalizationSource: null,
      mappingConfidence: null,
      matchedAlias: null,
      sourceRegistryKey: "salzwasser",
      followupQuestion: "Welche Salzkonzentration liegt vor?",
    },
    mediumContext: {
      mediumLabel: "Salzwasser",
      status: "available",
      scope: "orientierend",
      summary: "Salzwasser ist korrosionsrelevant.",
      properties: ["salzhaltig"],
      challenges: ["Korrosion"],
      followupPoints: ["Salzkonzentration"],
      confidence: "medium",
      sourceType: "deterministic",
      validationStatus: "system_derived",
      notForReleaseDecisions: true,
      disclaimer: "Keine Freigabe.",
    },
    completeness: { coverageGaps: [] },
    communication: { primaryQuestion: null },
  } as unknown as WorkspaceView;
}

function workspaceWithMaterialIntelligence(): WorkspaceView {
  return {
    caseId: "case-material",
    parameters: { medium: "Hydraulikoel HLP 46" },
    mediumClassification: {
      canonicalLabel: "Hydraulikoel",
      family: "hydraulikoel",
      confidence: "medium",
      status: "recognized",
      normalizationSource: null,
      mappingConfidence: null,
      matchedAlias: null,
      sourceRegistryKey: "hydraulikoel",
      followupQuestion: null,
    },
    mediumContext: {
      mediumLabel: "Hydraulikoel",
      status: "available",
      scope: "orientierend",
      summary: "Oelkontakt.",
      properties: [],
      challenges: [],
      followupPoints: [],
      confidence: "medium",
      sourceType: "deterministic",
      validationStatus: "system_derived",
      notForReleaseDecisions: true,
      disclaimer: null,
    },
    materialIntelligence: {
      capabilityId: "material_seal_type_context",
      status: "available",
      inputSummary: {
        medium: "Hydraulikoel",
        mediumFamily: "hydraulikoel",
        knownMaterial: null,
        temperatureC: 60,
        pressureBar: 120,
        sealType: "Hydraulikdichtung",
        motionType: "linear",
      },
      candidateMaterials: [
        {
          materialKey: "nbr",
          label: "NBR",
          family: "Elastomer",
          status: "candidate_to_check",
          statusLabel: "Kandidat im Prueffenster",
          confidence: "medium",
          plausibility: "high",
          plausibilityScore: 78,
          plausibilityLabel: "hohe Pruefprioritaet",
          counterindicators: ["Druck oder Druckdifferenz bleiben fuer Bauformgrenzen offen."],
          allowedClaim: "Vorlaeufige Pruefhypothese fuer die Anfragebasis.",
          forbiddenClaims: ["geeignet", "freigegeben", "sicher"],
          rfqRelevance: "Als Kontext fuer die Herstellerpruefung sichtbar machen, nicht als Vorgabe verwenden.",
          scoreDrivers: ["Oel- oder Hydraulikoelkontakt stuetzt dieses Werkstofffenster."],
          scoreCautions: ["Druck oder Druckdifferenz bleiben fuer Bauformgrenzen offen."],
          whyConsidered: ["Oelkontakt grenzt das elastomere Prueffenster ein."],
          limits: ["Wasser und Dampf sind fruehe Ausschlussfragen."],
          blockingUnknowns: ["Temperatur"],
          requiredChecks: ["Mediumdatenblatt und Additive"],
          evidenceRefIds: ["material-nbr"],
        },
        {
          materialKey: "epdm",
          label: "EPDM",
          family: "Elastomer",
          status: "excluded_by_known_constraint",
          statusLabel: "bekannte Angabe spricht dagegen",
          confidence: "low",
          plausibility: "low",
          plausibilityScore: 18,
          plausibilityLabel: "niedrige Pruefprioritaet",
          counterindicators: ["Oel- oder Hydraulikoelkontakt spricht deutlich gegen EPDM als fruehe Richtung."],
          allowedClaim: "Vorlaeufige Pruefhypothese fuer die Anfragebasis.",
          forbiddenClaims: ["geeignet", "freigegeben", "sicher"],
          rfqRelevance: "Als Gegenhypothese fuer die Herstellerpruefung sichtbar machen.",
          scoreDrivers: [],
          scoreCautions: ["Oel- oder Hydraulikoelkontakt spricht deutlich gegen EPDM als fruehe Richtung."],
          whyConsidered: ["Wassernahe Vergleichsfamilie."],
          limits: ["Mineraloel ist eine fruehe Ausschlussfrage."],
          blockingUnknowns: [],
          requiredChecks: ["Herstellerdaten pruefen"],
          evidenceRefIds: ["material-epdm"],
        },
      ],
      alternatives: [
        {
          fromMaterial: "NBR",
          toMaterial: "FKM",
          comparison: "NBR und FKM liegen in unterschiedlichen Prueffenstern.",
          tradeoffs: ["NBR: Kandidat im Prueffenster", "FKM: Daten fehlen"],
          missingForDecision: ["Temperatur"],
        },
      ],
      missingFieldHints: ["Temperatur"],
      rfqRelevanceNotes: ["Werkstofffamilie, Mischung/Compound und Nachweise gehoeren spaeter in die Anfragebasis."],
      evidence: [
        {
          id: "material-nbr",
          sourceType: "deterministic",
          validationStatus: "system_derived",
          title: "SeaLAI Werkstoffrahmen: NBR",
          excerpt: "Mineraloele und viele Hydraulikoele im ueblichen Vorqualifikationsfenster.",
          confidence: "medium",
        },
      ],
      safety: {
        mutatesCaseState: false,
        createsEngineeringTruth: false,
        finalApprovalClaimAllowed: false,
        dispatchAllowed: false,
        externalContactAllowed: false,
        exportAllowed: false,
      },
      notForReleaseDecisions: true,
      disclaimer: "Werkstofffenster nur zur Orientierung.",
    },
    completeness: { coverageGaps: [] },
    communication: { primaryQuestion: null },
  } as unknown as WorkspaceView;
}

describe("SealCockpit medium deep dive", () => {
  beforeEach(() => {
    useWorkspaceStore.getState().reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads and renders source-marked medium intelligence from the BFF", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        medium: "Salzwasser",
        resolved_medium: "Salzwasser",
        summary: "Salzwasser ist salzhaltig.",
        answer_markdown:
          "### Medium-Deep-Dive: Salzwasser\n\nChloride, Korrosion, Welle und Feder sind zentrale Pruefpunkte.",
        answer_markdown_source: "medium_composer",
        composer: {
          enabled: true,
          attempted: true,
          succeeded: true,
          source: "medium_composer",
          fallback_reason: null,
        },
        sections: [
          {
            id: "saltwater_deep_dive",
            title: "Salzwasser-spezifische Pruefpunkte",
            content: "Chloride und Korrosion sind zentrale Punkte.",
            bullets: ["Welle und Feder pruefen", "Kristallisation beachten"],
            evidence_ref_ids: ["medium-context"],
          },
        ],
        evidence: [
          {
            id: "medium-context",
            source_type: "deterministic",
            validation_status: "system_derived",
            title: "SeaLAI Medium-Kontext: Salzwasser",
            source_name: "SeaLAI kuratierter Medium-Kontext",
            excerpt: "Salzwasser ist wasserbasiert und salzhaltig.",
            confidence: "medium",
          },
        ],
        research_status: {
          rag: { attempted: true, status: "no_hits", hit_count: 0, tier: "tier3_empty", note: "Keine Treffer" },
          web: { attempted: false, status: "not_requested", hit_count: 0, note: "nur auf Wunsch" },
        },
        limitations: ["Technische Orientierung, keine Auslegungsfreigabe."],
        not_for_release_decisions: true,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SealCockpit data={cockpitData} workspace={workspaceWithMedium()} preferredTab="medium" />);

    expect(await screen.findByText("Salzwasser-spezifische Pruefpunkte")).toBeInTheDocument();
    expect(screen.getByText("Medium-Deep-Dive")).toBeInTheDocument();
    expect(screen.getByText("LLM-Deep-Dive")).toBeInTheDocument();
    expect(screen.getByText(/LLM formuliert/)).toBeInTheDocument();
    expect(screen.getByText(/Chloride, Korrosion, Welle und Feder/)).toBeInTheDocument();
    expect(screen.getByText("Quellen & Nachweise")).toBeInTheDocument();
    expect(screen.getByText(/RAG: keine Treffer/)).toBeInTheDocument();
    expect(screen.getByText(/Web: nur auf Wunsch/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Websearch starten/ })).toBeInTheDocument();
    expect(screen.getByText(/System · systemseitig abgeleitet/)).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bff/medium-intelligence",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ medium: "Salzwasser", include_web_research: false }),
        }),
      );
    });
  });

  it("starts live web research only after an explicit medium-tab action", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          medium: "Salzwasser",
          resolved_medium: "Salzwasser",
          summary: "Salzwasser ist salzhaltig.",
          answer_markdown: "### Salzwasser\n\nInstant-Antwort ohne Live-Websearch.",
          answer_markdown_source: "medium_composer",
          composer: {
            enabled: true,
            attempted: true,
            succeeded: true,
            source: "medium_composer",
            fallback_reason: null,
          },
          sections: [],
          evidence: [],
          research_status: {
            rag: { attempted: true, status: "no_hits", hit_count: 0, tier: "tier3_empty", note: "Keine Treffer" },
            web: { attempted: false, status: "not_requested", hit_count: 0, note: "nur auf Wunsch" },
          },
          limitations: ["Live-Websearch wurde nicht automatisch gestartet."],
          not_for_release_decisions: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          medium: "Salzwasser",
          resolved_medium: "Salzwasser",
          summary: "Salzwasser ist salzhaltig.",
          answer_markdown: "### Salzwasser\n\nVertiefung mit explizit gestarteter Websearch.",
          answer_markdown_source: "medium_composer",
          composer: {
            enabled: true,
            attempted: true,
            succeeded: true,
            source: "medium_composer",
            fallback_reason: null,
          },
          sections: [],
          evidence: [
            {
              id: "web-1",
              source_type: "web",
              validation_status: "web_retrieved",
              title: "Live-Websearch zum Medium",
              source_name: "Live-Websearch",
              excerpt: "Webhinweis.",
              confidence: "low",
            },
          ],
          research_status: {
            rag: { attempted: true, status: "no_hits", hit_count: 0, tier: "tier3_empty", note: "Keine Treffer" },
            web: { attempted: true, status: "ok", hit_count: 1, note: "Live-Webquelle wurde abgerufen." },
          },
          limitations: ["Technische Orientierung, keine Auslegungsfreigabe."],
          not_for_release_decisions: true,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    render(<SealCockpit data={cockpitData} workspace={workspaceWithMedium()} preferredTab="medium" />);

    const webButton = await screen.findByRole("button", { name: /Websearch starten/ });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/bff/medium-intelligence",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ medium: "Salzwasser", include_web_research: false }),
      }),
    );

    fireEvent.click(webButton);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/bff/medium-intelligence",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ medium: "Salzwasser", include_web_research: true }),
      }),
    );
    expect(await screen.findByText(/Web: 1 Treffer/)).toBeInTheDocument();
    expect(screen.getByText(/Vertiefung mit explizit gestarteter Websearch/)).toBeInTheDocument();
  });
});

describe("SealCockpit material intelligence", () => {
  it("renders material candidates and alternatives as a read-only check window", () => {
    render(
      <SealCockpit
        data={cockpitData}
        workspace={workspaceWithMaterialIntelligence()}
        preferredTab="material"
      />,
    );

    expect(screen.getByRole("heading", { name: "Werkstoff" })).toBeInTheDocument();
    expect(screen.getByText("Werkstofffenster")).toBeInTheDocument();
    expect(screen.getAllByText("Prüfhypothese")[0]).toBeInTheDocument();
    expect(screen.getByText("hoch")).toBeInTheDocument();
    expect(screen.queryByText("78 / 100")).not.toBeInTheDocument();
    expect(screen.getAllByText("Stützende Signale")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Prüfpunkte")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Gegenindikatoren")[0]).toBeInTheDocument();
    expect(screen.getByText("NBR")).toBeInTheDocument();
    expect(screen.getByText("EPDM")).toBeInTheDocument();
    expect(screen.getByText(/bekannte Angabe spricht dagegen/)).toBeInTheDocument();
    expect(screen.getByText(/NBR und FKM liegen/)).toBeInTheDocument();
    expect(screen.getByText(/SeaLAI Werkstoffrahmen: NBR/)).toBeInTheDocument();
    expect(screen.getByText(/SeaLAI setzt daraus keine Materialentscheidung/)).toBeInTheDocument();
  });
});
