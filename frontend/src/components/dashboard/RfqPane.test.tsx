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
