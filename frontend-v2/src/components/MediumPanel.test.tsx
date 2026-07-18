import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { MediumIntelligence } from "../contracts";
import { MediumPanel } from "./MediumPanel";

afterEach(cleanup);

const base: MediumIntelligence = {
  medium: "Salzsäure 30%",
  kategorie: "Sonstiges",
  eigenschaften: ["stark sauer/oxidierend"],
  herausforderungen: ["Versprödung vieler Elastomere"],
  werkstoff_tendenz: ["eher FFKM/PTFE"],
  unsicher: false,
  vorlaeufig: true,
};

describe("MediumPanel", () => {
  it("renders the medium, its sections and the mandatory vorläufig badge", () => {
    render(<MediumPanel data={base} />);
    expect(screen.getByTestId("medium-panel")).toBeInTheDocument();
    expect(screen.getByText(/Salzsäure 30%/)).toBeInTheDocument();
    expect(screen.getByText(/\(Sonstiges\)/)).toBeInTheDocument();
    expect(screen.getByText("vorläufig")).toBeInTheDocument();
    expect(screen.getByText("stark sauer/oxidierend")).toBeInTheDocument();
    expect(screen.getByText("Versprödung vieler Elastomere")).toBeInTheDocument();
    expect(screen.queryByText("eher FFKM/PTFE")).not.toBeInTheDocument();
    expect(screen.queryByText("Werkstoff-Tendenz")).not.toBeInTheDocument();
  });

  it("omits empty sections", () => {
    render(<MediumPanel data={{ ...base, werkstoff_tendenz: [] }} />);
    expect(screen.queryByText("Werkstoff-Tendenz")).not.toBeInTheDocument();
  });

  it("shows the extra unsicher caveat only when flagged", () => {
    const { rerender } = render(<MediumPanel data={base} />);
    expect(screen.queryByText(/besonders unsicher/)).not.toBeInTheDocument();
    rerender(<MediumPanel data={{ ...base, unsicher: true }} />);
    expect(screen.getByText(/besonders unsicher/)).toBeInTheDocument();
  });
});
