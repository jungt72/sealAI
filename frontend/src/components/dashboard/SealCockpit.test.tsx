import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";

import { DesignIntakePanel } from "./SealCockpit";

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
