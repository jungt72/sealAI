import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";
import type { SealCockpitOverview } from "@/lib/engineering/sealCockpitViewModel";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

import { DesignIntakePanel, SealCockpit } from "./SealCockpit";

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
  } as WorkspaceView;
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
  } as WorkspaceView;
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
  } as WorkspaceView;
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
    expect(screen.getByText("NBR")).toBeInTheDocument();
    expect(screen.getByText("EPDM")).toBeInTheDocument();
    expect(screen.getByText(/bekannte Angabe spricht dagegen/)).toBeInTheDocument();
    expect(screen.getByText(/NBR und FKM liegen/)).toBeInTheDocument();
    expect(screen.getByText(/SeaLAI Werkstoffrahmen: NBR/)).toBeInTheDocument();
    expect(screen.getByText(/SeaLAI setzt daraus keine Materialentscheidung/)).toBeInTheDocument();
  });
});
