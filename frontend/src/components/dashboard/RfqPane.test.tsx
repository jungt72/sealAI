import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import RfqPane from "./RfqPane";
import type { CockpitData } from "@/hooks/useCockpitData";
import type { WorkspaceRfqReadinessProjection, WorkspaceView } from "@/lib/contracts/workspace";

function readinessProjection(
  overrides: Partial<WorkspaceRfqReadinessProjection> = {},
): WorkspaceRfqReadinessProjection {
  return {
    manufacturer_review_ready: false,
    rfq_basis_ready: false,
    known_missing_fields: ["shaft_diameter_mm"],
    open_points: ["Druckspitzen offen"],
    blocking_reasons: ["Medium noch nicht bestaetigt"],
    pending_question: "Welche Wellendurchmesser-Dokumentation liegt vor?",
    consent_required: true,
    dispatch_allowed: false,
    external_contact_allowed: false,
    final_approval_claim_allowed: false,
    preview_available: true,
    preview_possible: true,
    preview_action_available: true,
    preview_action_name: "create_preview",
    preview_endpoint: "/api/v1/rfq/preview",
    preview_creation_requires_explicit_user_intent: true,
    preview_export_requires_consent: true,
    preview_requires_explicit_endpoint: true,
    preview_service_boundary: "RfqPreviewService.create_preview_for_case",
    projection_version: "rfq_readiness_projection_v1",
    ...overrides,
  };
}

function workspaceWithReadiness(
  projection: WorkspaceRfqReadinessProjection,
  stateRevision: number | null = 6,
): WorkspaceView {
  return {
    caseId: "case-1",
    rfqReadinessProjection: projection,
    summary: stateRevision === null ? {} : { stateRevision },
  } as WorkspaceView;
}

function cockpitData(): CockpitData {
  return {
    parameters: {},
    coverage: 0,
    releaseStatus: "backend_cockpit_pending",
    mediumStatus: {
      status: "unavailable",
      statusLabel: "noch offen",
      tone: "neutral",
      label: null,
      family: null,
      confidence: null,
      rawMention: null,
      summary: "Für die weitere Einordnung fehlt noch eine Angabe zum Medium.",
      nextStepHint: "Als Nächstes das Medium angeben.",
    },
    view: {
      path: null,
      requestType: "backend pending",
      sections: {
        application_function: {
          id: "application_function",
          title: "1. Anlage & Funktion",
          properties: [],
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
        },
        medium_environment: {
          id: "medium_environment",
          title: "2. Medium & Umgebung",
          properties: [],
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
        },
        operating_geometry: {
          id: "operating_geometry",
          title: "3. Betriebsdaten & Geometrie",
          properties: [],
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
        },
        risk_readiness: {
          id: "risk_readiness",
          title: "4. Risiken & Anfrage-Reife",
          properties: [],
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
        },
      },
      checks: [],
      riskEvaluations: [],
      readiness: {
        isRfqReady: true,
        missingMandatoryKeys: [],
        blockers: [],
        status: "rfq_ready",
      },
      mediumContext: {
        canonicalName: null,
        isConfirmed: false,
        properties: [],
        riskFlags: [],
      },
    },
  };
}

describe("RfqPane", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the backend RFQ preview with frozen revision, open points and consent boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          preview_id: "preview-1",
          case_id: "case-1",
          case_revision: 7,
          current_case_revision: 8,
          stale: true,
          consent_status: "not_requested",
          dispatch_enabled: false,
          created_at: "2026-04-28T00:00:00Z",
          payload: {
            rfq_preview: {
              sections: [
                {
                  index: 10,
                  title: "Offene Punkte / unbestaetigte Annahmen",
                  content: ["Wellendurchmesser bestaetigen"],
                  status: "open",
                },
                {
                  index: 8,
                  title: "Erkannte Risiken",
                  content: ["Temperaturspitzen offen"],
                  status: "available",
                },
                {
                  index: 12,
                  title: "Fragen an den Hersteller",
                  content: ["Bitte Werkstofffenster pruefen"],
                  status: "available",
                },
              ],
              technical_field_groups: [
                {
                  key: "documented",
                  title: "Documented values",
                  fields: [
                    {
                      field: "medium_name",
                      value: "Salzwasser",
                      engineering_value: { unit: null },
                      status: "documented",
                      provenance: "documented",
                      confidence: "confirmed",
                      confirmation_required: false,
                      evidence_refs: ["doc-1#p1"],
                    },
                  ],
                },
                {
                  key: "needs_confirmation",
                  title: "Needs confirmation",
                  fields: [
                    {
                      field: "shaft_diameter_mm",
                      value: 42,
                      engineering_value: { unit: "mm" },
                      status: "needs_confirmation",
                      provenance: "user_stated",
                      confidence: "medium",
                      confirmation_required: true,
                      evidence_refs: ["doc-1#p2"],
                    },
                  ],
                },
              ],
              technical_field_statuses: [
                {
                  field: "shaft_diameter_mm",
                  status: "needs_confirmation",
                  provenance: "user_stated",
                  confidence: "medium",
                  confirmation_required: true,
                  evidence_refs: ["doc-1#p2"],
                },
              ],
            },
            decision_understanding: {
              key_risks: ["Medium noch unvollstaendig"],
              manufacturer_review_needs: ["Dichtungslippe pruefen"],
            },
          },
        }),
      }),
    );

    render(<RfqPane data={cockpitData()} caseId="case-1" />);

    expect(await screen.findByRole("heading", { name: "Anfragevorschau" })).toBeInTheDocument();
    expect(screen.getByText("Stand 7")).toBeInTheDocument();
    expect(screen.getByText("jetzt 8")).toBeInTheDocument();
    expect(screen.getByText(/Diese Anfragevorschau ist veraltet/i)).toBeInTheDocument();
    expect(screen.getByText("Wellendurchmesser bestaetigen")).toBeInTheDocument();
    expect(screen.getByText("Temperaturspitzen offen")).toBeInTheDocument();
    expect(screen.getByText("Bitte Werkstofffenster pruefen")).toBeInTheDocument();
    expect(screen.getByText("Documented values")).toBeInTheDocument();
    expect(screen.getByText("Needs confirmation")).toBeInTheDocument();
    expect(screen.getByText("medium_name")).toBeInTheDocument();
    expect(screen.getByText(/Wert: Salzwasser/i)).toBeInTheDocument();
    expect(screen.getByText("shaft_diameter_mm")).toBeInTheDocument();
    expect(screen.getByText(/Wert: 42 mm/i)).toBeInTheDocument();
    expect(screen.getByText(/Beleg: doc-1#p2/i)).toBeInTheDocument();
    expect(screen.getByText("Nutzerbestätigung erforderlich")).toBeInTheDocument();
    expect(screen.getByLabelText(/keine Auslegungsfreigabe/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/offenen Punkte/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/manuelle, von mir kontrollierte Weitergabe/i)).toBeInTheDocument();
    expect(screen.queryByText("EagleBurgmann")).not.toBeInTheDocument();
    expect(screen.queryByText("John Crane")).not.toBeInTheDocument();
    expect(screen.queryByText("Flowserve")).not.toBeInTheDocument();
    expect(screen.queryByText(["An Hersteller", "senden"].join(" "))).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Nutzerbestätigung speichern/i })).toBeDisabled();
  });

  it("creates preview from the BFF and requires all consent acknowledgements before consent", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: "rfq_preview_not_found" } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          preview_id: "preview-2",
          case_id: "case-1",
          case_revision: 4,
          current_case_revision: 4,
          stale: false,
          consent_status: "not_requested",
          dispatch_enabled: false,
          created_at: null,
          payload: {
            rfq_preview: {
              sections: [
                { index: 1, title: "Kurzbeschreibung der Anwendung", content: { medium_name: "Oel" }, status: "available" },
                { index: 10, title: "Offene Punkte / unbestaetigte Annahmen", content: ["Druckspitzen offen"], status: "open" },
              ],
              technical_field_statuses: [],
            },
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          preview_id: "preview-2",
          case_id: "case-1",
          case_revision: 4,
          current_case_revision: 4,
          stale: false,
          consent_status: "granted",
          dispatch_enabled: false,
          created_at: null,
          payload: {
            rfq_preview: {
              sections: [
                { index: 1, title: "Kurzbeschreibung der Anwendung", content: { medium_name: "Oel" }, status: "available" },
                { index: 10, title: "Offene Punkte / unbestaetigte Annahmen", content: ["Druckspitzen offen"], status: "open" },
              ],
              technical_field_statuses: [],
            },
          },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<RfqPane data={cockpitData()} caseId="case-1" />);

    await user.click(await screen.findByRole("button", { name: /Anfragevorschau vorbereiten/i }));
    expect(await screen.findByText("Stand 4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Nutzerbestätigung speichern/i })).toBeDisabled();

    await user.click(screen.getByLabelText(/keine Auslegungsfreigabe/i));
    await user.click(screen.getByLabelText(/offenen Punkte/i));
    expect(screen.getByRole("button", { name: /Nutzerbestätigung speichern/i })).toBeDisabled();

    await user.click(screen.getByLabelText(/manuelle, von mir kontrollierte Weitergabe/i));
    await user.click(screen.getByRole("button", { name: /Nutzerbestätigung speichern/i }));

    expect(await screen.findByText("Anfragevorschau exportbereit")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/bff/rfq/case-1/preview/preview-2/consent",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"intended_recipients":["manual-export-by-user"]'),
      }),
    );
    const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
    expect(lastCall?.[1]?.body).toContain(
      '"user_acknowledged_export_intent":true',
    );
  });

  it("renders RFQ readiness projection with Anfragebasis and Herstellerprüfung framing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: "rfq_preview_not_found" } }),
      }),
    );
    const workspace = workspaceWithReadiness(readinessProjection());

    render(<RfqPane data={cockpitData()} caseId="case-1" workspace={workspace} />);

    expect(await screen.findByText("Anfragebasis für Herstellerprüfung")).toBeInTheDocument();
    expect(screen.getByText("Anfragebasis offen")).toBeInTheDocument();
    expect(screen.getByText("shaft_diameter_mm")).toBeInTheDocument();
    expect(screen.getByText("Druckspitzen offen")).toBeInTheDocument();
    expect(screen.getByText("Medium noch nicht bestaetigt")).toBeInTheDocument();
    expect(screen.getByText(/Vorschau bedeutet Anfragebasis für die Herstellerprüfung/i)).toBeInTheDocument();
    expect(screen.getByText(/kein Herstellerkontakt/i)).toBeInTheDocument();
    expect(screen.queryByText(/final approved|garantiert geeignet|freigegeben/i)).not.toBeInTheDocument();
    expect(screen.queryByText(["An Hersteller", "senden"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(/Hersteller kontaktieren/i)).not.toBeInTheDocument();
  });

  it("sends only expected_case_revision when the preview action is triggered from readiness", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: "rfq_preview_not_found" } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          preview_id: "preview-3",
          case_id: "case-1",
          case_revision: 6,
          current_case_revision: 6,
          stale: false,
          consent_status: "not_requested",
          dispatch_enabled: false,
          dispatch_allowed: false,
          external_contact_allowed: false,
          created_at: null,
          payload: {
            rfq_preview: {
              sections: [],
              technical_field_statuses: [],
            },
          },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const workspace = workspaceWithReadiness(readinessProjection(), 6);

    render(<RfqPane data={cockpitData()} caseId="case-1" workspace={workspace} />);

    const button = await screen.findByRole("button", { name: /Anfragevorschau vorbereiten/i });
    expect(button).toBeEnabled();
    expect(screen.getByText("Vorschau verfügbar")).toBeInTheDocument();
    await user.click(button);

    expect(await screen.findByText("Stand 6")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/bff/rfq/case-1/preview",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    const createBody = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(createBody).toEqual({ expected_case_revision: 6 });
    expect(createBody).not.toHaveProperty("dispatch_allowed");
    expect(createBody).not.toHaveProperty("external_contact_allowed");
    expect(createBody).not.toHaveProperty("export_allowed");
    expect(createBody).not.toHaveProperty("contact_manufacturer");
  });

  it("disables preview creation when the readiness projection blocks the action", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: "rfq_preview_not_found" } }),
      }),
    );
    const workspace = workspaceWithReadiness(
      readinessProjection({
        preview_possible: false,
        preview_action_available: false,
        blocking_reasons: ["Fall noch nicht als Case-Revision gespeichert"],
      }),
    );

    render(<RfqPane data={cockpitData()} caseId="case-1" workspace={workspace} />);

    expect(await screen.findByText("Vorschau noch blockiert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Anfragevorschau vorbereiten/i })).toBeDisabled();
    expect(screen.queryByText(["An Hersteller", "senden"].join(" "))).not.toBeInTheDocument();
    expect(screen.queryByText(/Hersteller kontaktieren/i)).not.toBeInTheDocument();
  });

  it("shows a product-safe message when preview creation has no persisted case revision", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: "rfq_preview_not_found" } }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: { message: "rfq_preview_create_failed:404" } }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<RfqPane data={cockpitData()} caseId="case-1" />);

    const button = await screen.findByRole("button", { name: /Anfragevorschau vorbereiten/i });
    expect(button).toBeEnabled();
    await user.click(button);

    expect(
      await screen.findByText(
        "Die Anfragevorschau kann erst erstellt werden, wenn der Fall gespeichert ist. Bitte übernimm zuerst die vorgeschlagenen Angaben.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("rfq_preview_create_failed:404")).not.toBeInTheDocument();
  });
});
