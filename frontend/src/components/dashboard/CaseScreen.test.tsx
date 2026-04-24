import { render, screen } from "@testing-library/react";
import { within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CaseScreen from "./CaseScreen";

vi.mock("@/components/dashboard/ChatPane", () => ({
  default: ({ caseId }: { caseId?: string }) => (
    <div data-testid="chat-pane">ChatPane {caseId ?? "new"}</div>
  ),
}));

vi.mock("@/hooks/useCockpitData", () => ({
  useCockpitData: () => ({
    parameters: {
      temperature_c: 80,
      motion_type: "rotierend",
    },
    coverage: 0.58,
    releaseStatus: "manufacturer_validation_required",
    mediumStatus: {
      status: "available",
      statusLabel: "verfuegbar",
      tone: "success",
      label: "Hydraulikoel",
      family: "oel",
      confidence: "high",
      rawMention: "Hydraulikoel",
      summary: "Mineraloelbasiertes Medium mit typischen Anforderungen an Temperatur und Alterung.",
      nextStepHint: "Bitte Temperaturbereich und Druckspitzen bestaetigen.",
    },
    view: {
      path: "rwdr",
      requestType: "retrofit",
      routingMetadata: {
        phase: "parameter_clarification",
        lastNode: null,
        routing: {},
      },
      sections: {
        core_intake: {
          id: "core_intake",
          title: "A. Grunddaten",
          properties: [
            {
              key: "installation",
              label: "Application",
              value: "Hydraulikpumpe",
              unit: "",
              origin: "user_override",
              confidence: "confirmed",
              isConfirmed: true,
              isMandatory: true,
            },
            {
              key: "pressure_bar",
              label: "Druck",
              value: 25,
              unit: "bar",
              origin: "user_override",
              confidence: "confirmed",
              isConfirmed: true,
              isMandatory: true,
            },
            {
              key: "speed_rpm",
              label: "Drehzahl",
              value: 1500,
              unit: "rpm",
              origin: "fast_brain_extracted",
              confidence: "extracted",
              isConfirmed: false,
              isMandatory: true,
            },
          ],
          completion: {
            mandatoryPresent: 3,
            mandatoryTotal: 5,
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
          label: "Umlaufgeschwindigkeit",
          formulaVersion: "v1",
          requiredInputs: [],
          missingInputs: [],
          validPaths: ["rwdr"],
          outputKey: "v_surface_m_s",
          unit: "m/s",
          status: "ok",
          value: 5.2,
          fallbackBehavior: "insufficient_input",
          guardrails: [],
          notes: [],
        },
      ],
      readiness: {
        isRfqReady: false,
        missingMandatoryKeys: ["shaft_diameter_mm"],
        blockers: [],
        status: "preliminary",
        releaseStatus: "manufacturer_validation_required",
        coverageScore: 0.58,
      },
      mediumContext: {
        canonicalName: "Hydraulikoel",
        isConfirmed: true,
        properties: ["schmierend", "waermealterung beachten"],
        riskFlags: ["Temperaturspitzen"],
      },
    },
  }),
}));

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      workspace: {
        caseId: "case-42",
        cockpit: null,
        communication: {
          primaryQuestion: "Welcher Wellendurchmesser liegt vor?",
          openPointsSummary: ["Wellendurchmesser fehlt"],
        },
        mediumContext: {
          summary: "Hydraulikoel ist als oelhaltiges Medium nur orientierend eingeordnet.",
          followupPoints: ["Additivpaket pruefen", "Viskositaet bei Betriebstemperatur nennen"],
        },
        summary: {
          derivedArtifactsStale: true,
          staleReason: "Upstream-Werte wurden geaendert.",
        },
        technicalDerivations: [
          {
            calcType: "rwdr",
            status: "ok",
            vSurfaceMPerS: 5.2,
            pvValueMpaMPerS: 0.41,
            dnValue: 75000,
            notes: [],
          },
        ],
        mediumClassification: {
          canonicalLabel: "Hydraulikoel",
        },
        matching: {
          items: [
            {
              material: "FKM",
              cluster: "preferred",
              specificity: "family_only",
              requiresValidation: false,
              fitBasis: "Gute Baseline fuer oelhaltige Anwendungen.",
              groundedFacts: [
                {
                  name: "Temperaturfenster",
                  value: "80",
                  unit: "C",
                  source: "registry",
                  sourceRank: 1,
                  groundingBasis: "source_backed",
                  isDivergent: false,
                  variants: [],
                },
              ],
            },
            {
              material: "PTFE",
              cluster: "secondary",
              specificity: "compound_required",
              requiresValidation: true,
              fitBasis: "Hohe chemische Robustheit, aber Validierung noetig.",
              groundedFacts: [
                {
                  name: "Chemische Robustheit",
                  value: "hoch",
                  unit: null,
                  source: "medium_context",
                  sourceRank: 2,
                  groundingBasis: "summary",
                  isDivergent: false,
                  variants: [],
                },
              ],
            },
          ],
        },
        specificity: {
          materialSpecificityRequired: "compound_required",
        },
        manufacturerQuestions: {
          mandatory: ["Werkstofffreigabe"],
        },
        evidence: {
          sourceBackedFindings: ["Registry-backed medium mapping vorhanden"],
          deterministicFindings: ["Pfad RWDR ist gesetzt"],
        },
        governance: {
          notes: ["Produktive Compare-Projektion steht noch aus."],
          unknownsBlocking: ["Compound-Freigabe offen"],
        },
        parameters: {
          installation: "Hydraulikpumpe",
        },
      },
      activeResponseClass: null,
      setWorkspace: vi.fn(),
      setWorkspaceLoading: vi.fn(),
    }),
}));

describe("CaseScreen", () => {
  it("renders the workspace shell with timeline, stable context header and collapsible utility rail", async () => {
    const user = userEvent.setup();
    render(<CaseScreen caseId="case-42" initialRequestType="retrofit" />);

    expect(screen.getByText("Frage verstehen")).toBeInTheDocument();
    expect(screen.getByText("Empfehlung ableiten")).toBeInTheDocument();
    expect(screen.getByText("PTFE-RWDR Entscheidungsraum")).toBeInTheDocument();
    expect(screen.getAllByText("Hydraulikpumpe").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Hydraulikoel").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId("chat-pane")).toHaveTextContent("ChatPane case-42");

    const toggle = screen.getByRole("button", { name: /utility rail aufklappen/i });
    await user.click(toggle);

    expect(screen.getByRole("button", { name: /utility rail einklappen/i })).toBeInTheDocument();
    expect(screen.getByText("Utility Rail")).toBeInTheDocument();
    expect(screen.getByText("Kontext ohne Chat-Duplikat")).toBeInTheDocument();
    expect(screen.getByText("Welcher Wellendurchmesser liegt vor?")).toBeInTheDocument();
  });

  it("renders productive parameter tabs and field statuses without mutating business state", async () => {
    const user = userEvent.setup();
    render(<CaseScreen caseId="case-42" initialRequestType="retrofit" />);

    expect(screen.getByText("Aktiver technischer Pfad")).toBeInTheDocument();
    const parameterCard = screen.getByText("Parameter & Application").closest("section");
    expect(parameterCard).not.toBeNull();
    const scoped = within(parameterCard as HTMLElement);

    expect(scoped.getByText("Rwdr")).toBeInTheDocument();
    expect(scoped.getAllByText("confirmed").length).toBeGreaterThan(0);
    expect(scoped.getByRole("tab", { name: "RWDR" })).toHaveAttribute("aria-selected", "true");
    expect(scoped.getByText("Kernparameter")).toBeInTheDocument();
    expect(scoped.getByText("Pfadspezifische Zusatzparameter")).toBeInTheDocument();
    expect(scoped.getAllByText("Hydraulikpumpe").length).toBeGreaterThan(0);
    expect(scoped.getAllByText("inferred").length).toBeGreaterThan(0);
    expect(scoped.getAllByText("missing").length).toBeGreaterThan(0);
    expect(scoped.getAllByText("optional").length).toBeGreaterThan(0);

    const rwdrTab = scoped.getByRole("tab", { name: "RWDR" });
    rwdrTab.focus();
    await user.keyboard("{ArrowRight}");

    expect(scoped.getByRole("tab", { name: "Hydraulik" })).toHaveAttribute("aria-selected", "true");
    expect(scoped.getByText("ui view")).toBeInTheDocument();
    expect(screen.getByText("PTFE-RWDR Entscheidungsraum")).toBeInTheDocument();
    expect(screen.getByText("Welcher Wellendurchmesser liegt vor?")).toBeInTheDocument();
  });

  it("renders productive medium, calculation and open-point cards from existing projections", () => {
    render(<CaseScreen caseId="case-42" initialRequestType="retrofit" />);

    const mediumCard = screen.getByText("Medium Intelligence").closest("section");
    expect(mediumCard).not.toBeNull();
    const mediumScoped = within(mediumCard as HTMLElement);
    expect(mediumScoped.getByText("Hydraulikoel")).toBeInTheDocument();
    expect(mediumScoped.getByText(/Hydraulikoel ist als oelhaltiges Medium/i)).toBeInTheDocument();
    expect(mediumScoped.getByText("Additivpaket pruefen")).toBeInTheDocument();

    const calculationsCard = screen.getByText("Calculations").closest("section");
    expect(calculationsCard).not.toBeNull();
    const calculationsScoped = within(calculationsCard as HTMLElement);
    expect(calculationsScoped.getByText("Umlaufgeschwindigkeit")).toBeInTheDocument();
    expect(calculationsScoped.getByText("5.2 m/s")).toBeInTheDocument();
    expect(calculationsScoped.getAllByText("stale").length).toBeGreaterThan(0);
    expect(calculationsScoped.getByText("Upstream-Werte wurden geaendert.")).toBeInTheDocument();

    const openPointsCard = screen.getByText("Open Points / Next Step").closest("section");
    expect(openPointsCard).not.toBeNull();
    const openPointsScoped = within(openPointsCard as HTMLElement);
    expect(openPointsScoped.getByText("shaft diameter mm")).toBeInTheDocument();
    expect(openPointsScoped.getByText("Wellendurchmesser fehlt")).toBeInTheDocument();
    expect(openPointsScoped.getByText("Welcher Wellendurchmesser liegt vor?")).toBeInTheDocument();
  });

  it("switches the right cockpit column in place while keeping the context header stable", async () => {
    const user = userEvent.setup();
    render(<CaseScreen caseId="case-42" initialRequestType="retrofit" />);

    expect(screen.getByText("PTFE-RWDR Entscheidungsraum")).toBeInTheDocument();
    expect(screen.getByText("Vergleichsarbeitsstand")).toBeInTheDocument();
    expect(screen.getByText("Parameter & Application")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Compare" }));

    expect(await screen.findByText("Vergleich NBR vs PTFE")).toBeInTheDocument();
    expect(await screen.findByText("Kurzfazit")).toBeInTheDocument();
    expect(await screen.findByText("FKM")).toBeInTheDocument();
    expect(await screen.findByText("PTFE")).toBeInTheDocument();
    expect(screen.getByText("PTFE-RWDR Entscheidungsraum")).toBeInTheDocument();
    expect(screen.getByText("Case ID")).toBeInTheDocument();
    expect(screen.getByText("case-42")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Deep Dive" }));

    expect(await screen.findByText("Material Profile")).toBeInTheDocument();
    expect(await screen.findByText("Properties")).toBeInTheDocument();
    expect(await screen.findByText("Typical Applications & Limits")).toBeInTheDocument();
    expect(await screen.findByText("Deep Notes / Sources")).toBeInTheDocument();
    expect((await screen.findAllByText("Hydraulikoel")).length).toBeGreaterThan(0);
    expect(screen.getByText("Vergleichsarbeitsstand")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Case" }));

    expect(await screen.findByText("Parameter & Application")).toBeInTheDocument();
    expect(await screen.findByText("Medium Intelligence")).toBeInTheDocument();
    expect(screen.getByText("PTFE-RWDR Entscheidungsraum")).toBeInTheDocument();
  });
});
