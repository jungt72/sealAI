import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
        core_intake: {
          id: "core_intake",
          title: "A. Grunddaten",
          properties: [],
          completion: { mandatoryPresent: 0, mandatoryTotal: 0, percent: 0 },
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
  it("does not render mock manufacturers as backend-approved matches", () => {
    render(<RfqPane data={cockpitData()} caseId="case-1" />);

    expect(screen.getByText("Backend-Matching ausstehend")).toBeInTheDocument();
    expect(screen.getByText("Noch keine backend-bestätigte Herstellerliste")).toBeInTheDocument();
    expect(screen.queryByText("EagleBurgmann")).not.toBeInTheDocument();
    expect(screen.queryByText("John Crane")).not.toBeInTheDocument();
    expect(screen.queryByText("Flowserve")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /An Hersteller senden/i })).toBeDisabled();
  });
});
