import { render, screen, waitFor } from "@testing-library/react";
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
    pending_question: {
      target_field: "shaft_diameter_mm",
      question_text: "Welche Wellendurchmesser-Dokumentation liegt vor?",
      required_for_rfq: true,
    },
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
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
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
              technical_rwdr_rfq_brief: {
                artifact_title: "Technical RWDR RFQ Brief",
                artifact_type: "technical_rwdr_rfq_brief",
                status: "NEEDS_CLARIFICATION",
                no_final_technical_release: true,
                dispatch_enabled: false,
                manufacturer_matching_enabled: false,
                evaluation: {
                  complete_enough_for_manufacturer_evaluation: false,
                  open_points: ["Missing or unconfirmed: shaft_diameter"],
                  out_of_scope_reasons: [],
                },
                confirmed_case_fields: [
                  {
                    field: "medium_name",
                    value: "Salzwasser",
                    status: "documented",
                    provenance: "documented",
                    source_type: "uploaded_evidence",
                    validation_status: "documented",
                    allowed_in_brief: true,
                  },
                ],
                calculation_fields: [
                  {
                    field: "calculated_speed_m_s",
                    value: 3.19,
                    unit: "m/s",
                    status: "calculated",
                    source_type: "deterministic_calculation",
                    validation_status: "calculated",
                    allowed_in_brief: true,
                  },
                ],
                open_fields: [
                  {
                    field: "shaft_diameter_mm",
                    value: 42,
                    unit: "mm",
                    status: "needs_confirmation",
                    source_type: "user_stated",
                    validation_status: "candidate",
                    allowed_in_brief: false,
                    blocked_reason: "explicit_user_confirmation_required",
                  },
                ],
              },
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
    expect(await screen.findByText("Stand 7")).toBeInTheDocument();
    expect(screen.getByText("jetzt 8")).toBeInTheDocument();
    expect(screen.getByText(/Diese Anfragevorschau ist veraltet/i)).toBeInTheDocument();
    expect(screen.getByText("Technical RWDR RFQ Brief")).toBeInTheDocument();
    expect(screen.getByText("Klärung erforderlich")).toBeInTheDocument();
    expect(screen.getByText("kein Hersteller-Ranking")).toBeInTheDocument();
    expect(screen.getByText("Hersteller-Routing")).toBeInTheDocument();
    expect(screen.getByText("deaktiviert")).toBeInTheDocument();
    expect(screen.getByText(/medium_name: Salzwasser/i)).toBeInTheDocument();
    expect(screen.getByText(/calculated_speed_m_s: 3.19 m\/s/i)).toBeInTheDocument();
    expect(screen.getByText(/explicit_user_confirmation_required/i)).toBeInTheDocument();
    expect(screen.getByText("Wellendurchmesser bestaetigen")).toBeInTheDocument();
    expect(screen.getByText("Temperaturspitzen offen")).toBeInTheDocument();
    expect(screen.getAllByText("Bitte Werkstofffenster pruefen")[0]).toBeInTheDocument();
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
    expect(await screen.findByText("Fertige Anfrage als PDF bereit")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Anfrage als PDF herunterladen/i })).toHaveAttribute(
      "href",
      "/api/bff/rfq/case-1/preview/preview-2/export",
    );
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
    const workspace = {
      ...workspaceWithReadiness(readinessProjection()),
      manufacturerQuestions: {
        mandatory: [
          "Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
        ],
        openQuestions: [
          {
            id: "challenge.nbr",
            question: "Bitte Gegenindikator pruefen: NBR wirkt im bekannten Chemiefenster als Gegenindikator.",
            reason: "Als Herstellerpruefpunkt sichtbar machen.",
            priority: "critical",
            category: "contradiction",
          },
        ],
        totalOpen: 2,
      },
    } as WorkspaceView;

    render(<RfqPane data={cockpitData()} caseId="case-1" workspace={workspace} />);

    expect(await screen.findByText("Anfragebasis für Herstellerprüfung")).toBeInTheDocument();
    expect(screen.getByText("Anfragebasis offen")).toBeInTheDocument();
    expect(screen.getByText("Automatisch vorbereitete Herstellerfragen")).toBeInTheDocument();
    expect(screen.getByText(/Welcher Druck oder welche Druckdifferenz/)).toBeInTheDocument();
    expect(screen.getByText(/NBR wirkt im bekannten Chemiefenster/)).toBeInTheDocument();
    expect(screen.getByText("shaft_diameter_mm")).toBeInTheDocument();
    expect(screen.getByText(/Nächste Frage: Welche Wellendurchmesser-Dokumentation liegt vor/i)).toBeInTheDocument();
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

  it("lets users confirm extracted RWDR liability fields with source spans", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          case_id: "rwdr-case-1",
          raw_inquiry: "Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min.",
          evidence_fields: [
            {
              field: "shaft_diameter_d1_mm",
              value: 45,
              unit: "mm",
              origin: "llm_extracted",
              source_type: "user_text",
              source_span: "45x62x8",
              confirmation_status: "unconfirmed",
              liability_bearing: true,
            },
          ],
          technical_rwdr_rfq_brief: {
            artifact_title: "Technical RWDR RFQ Brief",
            status: "NEEDS_CLARIFICATION",
            manufacturer_matching_enabled: false,
            no_final_technical_release: true,
            confirmed_case_fields: [],
            calculation_fields: [],
            open_fields: [{ field: "shaft_diameter_d1_mm", value: 45, unit: "mm", blocked_reason: "llm_extracted_field_not_user_confirmed" }],
            sections: [
              { id: "missing_critical_fields", items: ["housing_bore_D_mm"] },
              { id: "manufacturer_questions", items: ["Bitte geben Sie die Gehäusebohrung D in mm an."] },
              { id: "recommended_measurement_and_verification_data", items: [{ field: "housing_bore_D_mm", method: "3-point bore gauge / Innenmessgerät" }] },
            ],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          snapshots: [
            { revision_number: 1, event_type: "case_created_after_analyze", created_at: "2026-05-27T00:00:00Z" },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          case_id: "rwdr-case-1",
          raw_inquiry: "Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min.",
          evidence_fields: [
            {
              field: "shaft_diameter_d1_mm",
              value: 45,
              unit: "mm",
              origin: "llm_extracted",
              source_type: "user_text",
              source_span: "45x62x8",
              confirmation_status: "confirmed",
              liability_bearing: true,
            },
          ],
          technical_rwdr_rfq_brief: {
            artifact_title: "Technical RWDR RFQ Brief",
            status: "NEEDS_CLARIFICATION",
            manufacturer_matching_enabled: false,
            no_final_technical_release: true,
            confirmed_case_fields: [{ field: "shaft_diameter_d1_mm", value: 45, unit: "mm", source_span: "45x62x8" }],
            calculation_fields: [],
            open_fields: [],
            sections: [{ id: "confirmed_data", items: [{ field: "shaft_diameter_d1_mm", value: 45 }] }],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          snapshots: [
            { revision_number: 1, event_type: "case_created_after_analyze", created_at: "2026-05-27T00:00:00Z" },
            { revision_number: 2, event_type: "confirmation_decision_applied", created_at: "2026-05-27T00:01:00Z" },
          ],
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<RfqPane data={null} />);

    await user.type(screen.getByLabelText(/RWDR-Anfrage einfügen/i), "Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min.");
    await user.click(screen.getByRole("button", { name: /Angaben strukturieren/i }));

    expect(await screen.findByText("Wellendurchmesser d1")).toBeInTheDocument();
    expect(screen.getByText(/Gefundener Wert/i)).toBeInTheDocument();
    expect(screen.getByText('"45x62x8"')).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bestätigen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Nicht angegeben \/ unbekannt/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Verwerfen" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Bestätigen" }));

    const confirmationCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).includes("/confirmations"),
    );
    const confirmBody = JSON.parse(String(confirmationCall?.[1]?.body));
    expect(confirmationCall?.[0]).toBe("/api/bff/rfq/rwdr/cases/rwdr-case-1/confirmations");
    expect(confirmBody.decisions[0]).toMatchObject({
      field: "shaft_diameter_d1_mm",
      action: "confirm",
      source_span: "45x62x8",
    });
  });

  it("does not treat missing source span as trusted extracted evidence and supports edit unknown and reject", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          case_id: "rwdr-case-2",
          raw_inquiry: "RWDR Öl",
          evidence_fields: [
            {
              field: "temperature_max_c",
              value: 80,
              unit: "degC",
              origin: "llm_extracted",
              source_type: "user_text",
              confirmation_status: "unconfirmed",
              liability_bearing: true,
            },
          ],
          technical_rwdr_rfq_brief: {
            artifact_title: "Technical RWDR RFQ Brief",
            status: "NEEDS_CLARIFICATION",
            manufacturer_matching_enabled: false,
            no_final_technical_release: true,
            confirmed_case_fields: [],
            calculation_fields: [],
            open_fields: [{ field: "temperature_max_c", value: 80 }],
            sections: [{ id: "missing_critical_fields", items: ["temperature_max_c"] }],
          },
        }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          case_id: "rwdr-case-2",
          raw_inquiry: "RWDR Öl",
          evidence_fields: [
            {
              field: "temperature_max_c",
              value: 80,
              unit: "degC",
              origin: "llm_extracted",
              source_type: "user_text",
              confirmation_status: "unconfirmed",
              liability_bearing: true,
            },
          ],
          technical_rwdr_rfq_brief: {
            artifact_title: "Technical RWDR RFQ Brief",
            status: "NEEDS_CLARIFICATION",
            manufacturer_matching_enabled: false,
            no_final_technical_release: true,
            confirmed_case_fields: [],
            calculation_fields: [],
            open_fields: [],
            sections: [{ id: "missing_critical_fields", items: ["temperature_max_c"] }],
          },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<RfqPane data={null} />);

    await user.type(screen.getByLabelText(/RWDR-Anfrage einfügen/i), "RWDR Öl");
    await user.click(screen.getByRole("button", { name: /Angaben strukturieren/i }));

    expect(await screen.findByText(/Keine exakte Quellenstelle verfügbar/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.clear(screen.getByLabelText(/Maximale Temperatur bearbeiten/i));
    await user.type(screen.getByLabelText(/Maximale Temperatur bearbeiten/i), "85");
    await user.click(screen.getByRole("button", { name: /Bearbeitung übernehmen/i }));
    const confirmationCalls = () =>
      fetchMock.mock.calls.filter((call) => String(call[0]).includes("/confirmations"));
    expect(confirmationCalls()[0]?.[0]).toBe("/api/bff/rfq/rwdr/cases/rwdr-case-2/confirmations");
    expect(JSON.parse(String(confirmationCalls()[0]?.[1]?.body)).decisions[0]).toMatchObject({
      field: "temperature_max_c",
      action: "edit",
      value: "85",
    });

    await user.click(screen.getByRole("button", { name: /Nicht angegeben \/ unbekannt/i }));
    expect(JSON.parse(String(confirmationCalls()[1]?.[1]?.body)).decisions[0]).toMatchObject({
      field: "temperature_max_c",
      action: "explicitly_unknown",
    });

    await user.click(screen.getByRole("button", { name: "Verwerfen" }));
    expect(JSON.parse(String(confirmationCalls()[2]?.[1]?.body)).decisions[0]).toMatchObject({
      field: "temperature_max_c",
      action: "reject",
    });
    expect(screen.queryByText(/Partner-Fit|Warum passend|passende Partnerprofile/i)).not.toBeInTheDocument();
  });

  it("generates and exposes the backend-persisted RWDR brief export by case id", async () => {
    vi.stubGlobal("navigator", {
      ...window.navigator,
      clipboard: { writeText: vi.fn() },
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          case_id: "rwdr-case-3",
          raw_inquiry: "RWDR Druck unbekannt",
          evidence_fields: [
            {
              field: "pressure_differential",
              value: null,
              origin: "llm_extracted",
              source_type: "user_text",
              confirmation_status: "explicitly_unknown",
              liability_bearing: true,
            },
          ],
          technical_rwdr_rfq_brief: {
            artifact_title: "Technical RWDR RFQ Brief",
            status: "NEEDS_CLARIFICATION",
            manufacturer_matching_enabled: false,
            no_final_technical_release: true,
            confirmed_case_fields: [],
            calculation_fields: [],
            open_fields: [],
            sections: [
              { id: "status", title: "Status", items: ["NEEDS_CLARIFICATION"] },
              { id: "disclaimer", title: "Disclaimer", items: ["keine finale technische Eignungsfreigabe"] },
            ],
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          artifact_title: "Technical RWDR RFQ Brief",
          status: "NEEDS_CLARIFICATION",
          manufacturer_matching_enabled: false,
          no_final_technical_release: true,
          confirmed_case_fields: [],
          calculation_fields: [],
          open_fields: [{ field: "pressure_differential", value: null }],
          sections: [
            { id: "status", title: "Status", items: ["NEEDS_CLARIFICATION"] },
            { id: "missing_critical_fields", title: "Kritisch fehlende Angaben", items: ["pressure_differential"] },
            { id: "disclaimer", title: "Disclaimer", items: ["keine finale technische Eignungsfreigabe"] },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          case_id: "rwdr-case-3",
          export_format: "markdown",
          content: "# Technical RWDR RFQ Brief\n\nPersistierte Exportfassung",
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<RfqPane data={null} />);

    await user.type(screen.getByLabelText(/RWDR-Anfrage einfügen/i), "RWDR Druck unbekannt");
    await user.click(screen.getByRole("button", { name: /Angaben strukturieren/i }));
    expect(await screen.findByText(/RWDR Case: rwdr-cas/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Technical RWDR RFQ Brief erstellen" }));

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(urls).toContain("/api/bff/rfq/rwdr/cases/rwdr-case-3/brief");
      expect(urls).toContain("/api/bff/rfq/rwdr/cases/rwdr-case-3/export");
    });
    expect(await screen.findByRole("button", { name: "Brief als Text kopieren" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Brief als PDF herunterladen" })).toHaveAttribute(
      "href",
      "/api/bff/rfq/rwdr/cases/rwdr-case-3/export.pdf",
    );
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toContain("/api/bff/rfq/rwdr/cases/rwdr-case-3/export");
  });

  it("restores RWDR case state from URL case id without trusting local evidence fields", async () => {
    window.history.replaceState({}, "", "/dashboard?rwdr_case_id=rwdr-restore-1");
    window.localStorage.setItem("sealai_rwdr_case_id", "rwdr-other");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          case_id: "rwdr-restore-1",
          raw_inquiry_text: "RWDR 45x62x8 Öl",
          evidence_fields: [
            {
              field: "shaft_diameter_d1_mm",
              value: 45,
              unit: "mm",
              origin: "llm_extracted",
              source_span: "45x62x8",
              confirmation_status: "confirmed",
              liability_bearing: true,
            },
          ],
          technical_rwdr_rfq_brief: {
            artifact_title: "Technical RWDR RFQ Brief",
            status: "NEEDS_CLARIFICATION",
            manufacturer_matching_enabled: false,
            no_final_technical_release: true,
            confirmed_case_fields: [{ field: "shaft_diameter_d1_mm", value: 45, unit: "mm" }],
            calculation_fields: [],
            open_fields: [],
            sections: [{ id: "confirmed_data", title: "Bestätigte Angaben", items: [{ field: "shaft_diameter_d1_mm", value: 45 }] }],
          },
          export_markdown: "# Technical RWDR RFQ Brief",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          case_id: "rwdr-restore-1",
          snapshots: [
            { revision_number: 1, event_type: "case_created_after_analyze" },
            { revision_number: 2, event_type: "confirmation_decision_applied" },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          case_id: "rwdr-restore-1",
          from_revision: 1,
          to_revision: 2,
          from_event_type: "case_created_after_analyze",
          to_event_type: "confirmation_decision_applied",
          summary: {
            changed_fields_count: 1,
            added_missing_fields_count: 0,
            removed_missing_fields_count: 1,
            status_changed: false,
            brief_changed: false,
            export_changed: true,
          },
          status_diff: {},
          evidence_field_diffs: [
            {
              field: "shaft_diameter_d1_mm",
              change_type: "confirmation_status_changed",
              from: { value: 45, confirmation_status: "unconfirmed" },
              to: { value: 45, confirmation_status: "confirmed" },
              source_span_changed: false,
            },
          ],
          missing_critical_fields_diff: {
            added: [],
            removed: ["shaft_diameter_d1_mm"],
            unchanged: ["temperature_max_c"],
          },
          computed_values_diff: {
            added: [{ field: "circumferential_speed_mps", value: 3.53 }],
            changed: [],
            removed: [],
          },
          review_flags_diff: { added: ["pressure_design_review_required"], changed: [], removed: [] },
          manufacturer_questions_diff: { added: ["Welche maximale Druckdifferenz liegt an?"], changed: [], removed: [] },
          measurement_recommendations_diff: { added: [], changed: [], removed: [] },
          export_diff: {
            markdown_export_changed: false,
            pdf_export_changed: true,
            export_metadata_changed: true,
          },
          audit_metadata: { audit_metadata_excluded_from_deterministic_diff: true },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<RfqPane data={null} />);

    expect(await screen.findByText(/RWDR Case: rwdr-re/i)).toBeInTheDocument();
    expect(await screen.findByText(/aus Backend wiederhergestellt/i)).toBeInTheDocument();
    expect(screen.getByText("Rev. 2: confirmation_decision_applied")).toBeInTheDocument();
    expect(screen.getByText(/Origin: llm_extracted · Status: confirmed/i)).toBeInTheDocument();
    expect(window.localStorage.getItem("sealai_rwdr_case_id")).toBe("rwdr-restore-1");
    expect(window.localStorage.getItem("rwdr_evidence_fields")).toBeNull();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/rfq/rwdr/cases/rwdr-restore-1");

    await user.click(screen.getByRole("button", { name: "Revisionen vergleichen" }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.map((call) => String(call[0]))).toContain(
        "/api/bff/rfq/rwdr/cases/rwdr-restore-1/diff/1/2",
      );
    });
    expect(await screen.findByText(/Bestätigungsstatus geändert/i)).toBeInTheDocument();
    expect(screen.getByText(/Entfallen: Wellendurchmesser d1/i)).toBeInTheDocument();
    expect(screen.getByText(/circumferential_speed_mps/i)).toBeInTheDocument();
    expect(screen.getByText(/PDF-Export geändert/i)).toBeInTheDocument();
    expect(screen.queryByText(/Partner-Fit|Warum passend|passende Partnerprofile/i)).not.toBeInTheDocument();
  });
});
