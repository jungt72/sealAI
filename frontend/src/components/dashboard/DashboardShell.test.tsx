import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import DashboardShell from "./DashboardShell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard/new",
}));

vi.mock("next-auth/react", () => ({
  signOut: vi.fn(),
  useSession: () => ({ data: null }),
}));

describe("DashboardShell", () => {
  it("renders the SeaLAI image logo in the shell", () => {
    render(
      <DashboardShell>
        <main>Arbeitsbereich</main>
      </DashboardShell>,
    );

    const logos = screen.getAllByAltText("SeaLAI") as HTMLImageElement[];
    expect(logos.length).toBeGreaterThanOrEqual(1);
    expect(logos[0].getAttribute("src")).toContain("sealai-symbol.png");
    expect(screen.getByText("SEALING")).toBeInTheDocument();
    expect(screen.getByText("INTELLIGENCE")).toBeInTheDocument();
    expect(screen.queryByText("Knowledge Modus")).not.toBeInTheDocument();
  });

  it("expands the left navigation so labels and content become visible", async () => {
    const user = userEvent.setup();

    render(
      <DashboardShell>
        <main>Arbeitsbereich</main>
      </DashboardShell>,
    );

    expect(screen.queryByText("Wissen")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Navigation erweitern" }));

    expect(screen.getByText("Wissen")).toBeInTheDocument();
    expect(screen.getByText("Dokumente")).toBeInTheDocument();
    expect(screen.getByText("Einstellungen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Navigation einklappen" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
