import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

import { HeroPrecheckCard } from "./HeroPrecheckCard";

describe("HeroPrecheckCard", () => {
  it("computes circumferential speed for a complete RWDR case and shows the full-analysis CTA", () => {
    render(<HeroPrecheckCard />);

    fireEvent.change(screen.getByLabelText("Dichtungstyp"), { target: { value: "rwdr" } });
    fireEvent.change(screen.getByLabelText("Situation"), { target: { value: "leakage" } });
    fireEvent.change(screen.getByLabelText("Medium"), { target: { value: "Hydrauliköl" } });
    fireEvent.change(screen.getByLabelText("Wellendurchmesser"), { target: { value: "45 mm" } });
    fireEvent.change(screen.getByLabelText("Drehzahl"), { target: { value: "1.500 U/min" } });

    fireEvent.click(screen.getByRole("button", { name: /Vorcheck starten/i }));

    expect(screen.getByText("3,53")).toBeInTheDocument();
    expect(screen.getByText(/Umfangsgeschwindigkeit/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kostenlos vollständig analysieren/i })).toBeInTheDocument();
  });

  it("shows at most 3 open points in the compact result", () => {
    render(<HeroPrecheckCard />);
    fireEvent.change(screen.getByLabelText("Dichtungstyp"), { target: { value: "rwdr" } });
    fireEvent.change(screen.getByLabelText("Medium"), { target: { value: "Hydrauliköl" } });
    fireEvent.click(screen.getByRole("button", { name: /Vorcheck starten/i }));

    const openList = screen.getByText("Noch offen").parentElement?.querySelector("ul");
    expect(openList).not.toBeNull();
    expect(openList!.querySelectorAll("li").length).toBeLessThanOrEqual(3);
  });

  it("makes no recommendation and shows no result before submit", () => {
    render(<HeroPrecheckCard />);
    expect(screen.queryByText(/Kostenlos vollständig analysieren/i)).not.toBeInTheDocument();
  });
});
