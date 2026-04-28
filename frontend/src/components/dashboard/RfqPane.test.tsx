import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import RfqPane from "./RfqPane";
import type { CockpitData } from "@/hooks/useCockpitData";

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

    expect(await screen.findByText("RFQ-Preview")).toBeInTheDocument();
    expect(screen.getByText("frozen revision 7")).toBeInTheDocument();
    expect(screen.getByText("current revision 8")).toBeInTheDocument();
    expect(screen.getByText(/Diese RFQ-Preview ist stale/i)).toBeInTheDocument();
    expect(screen.getByText("Wellendurchmesser bestaetigen")).toBeInTheDocument();
    expect(screen.getByText("Temperaturspitzen offen")).toBeInTheDocument();
    expect(screen.getByText("Bitte Werkstofffenster pruefen")).toBeInTheDocument();
    expect(screen.getByText("shaft_diameter_mm")).toBeInTheDocument();
    expect(screen.getByText(/Evidence: doc-1#p2/i)).toBeInTheDocument();
    expect(screen.getByText("Nutzerbestätigung erforderlich")).toBeInTheDocument();
    expect(screen.getByLabelText(/keine finale technische Freigabe/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/offenen Punkte/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/explizitem Einverständnis/i)).toBeInTheDocument();
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

    await user.click(await screen.findByRole("button", { name: /RFQ-Preview vorbereiten/i }));
    expect(await screen.findByText("frozen revision 4")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Nutzerbestätigung speichern/i })).toBeDisabled();

    await user.click(screen.getByLabelText(/keine finale technische Freigabe/i));
    await user.click(screen.getByLabelText(/offenen Punkte/i));
    expect(screen.getByRole("button", { name: /Nutzerbestätigung speichern/i })).toBeDisabled();

    await user.click(screen.getByLabelText(/explizitem Einverständnis/i));
    await user.click(screen.getByRole("button", { name: /Nutzerbestätigung speichern/i }));

    expect(await screen.findByText("RFQ-Preview exportbereit")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/bff/rfq/case-1/preview/preview-2/consent",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
