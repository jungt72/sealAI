import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardShell from "./DashboardShell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard/new",
}));

vi.mock("next-auth/react", () => ({
  signOut: vi.fn(),
  useSession: () => ({ data: null }),
}));

describe("DashboardShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          items: [
            {
              case_id: "case-42",
              title: "RWDR Wasser-Glykol",
              status: "Analyse",
              updated_at: "2026-05-06T08:00:00.000Z",
            },
          ],
        }),
      }),
    );
  });

  it("renders the sealingAI header and active workspace", () => {
    render(
      <DashboardShell>
        <main>Arbeitsbereich</main>
      </DashboardShell>,
    );

    expect(screen.getByText("SEALING")).toBeInTheDocument();
    expect(screen.getByText("INTELLIGENCE")).toBeInTheDocument();
    expect(screen.getByText(/Arbeitsraum:/)).toBeInTheDocument();
    expect(screen.getByText("Anfragebasis")).toBeInTheDocument();
    expect(screen.queryByText(/Suche-ID:/)).not.toBeInTheDocument();
    expect(screen.queryByText("Knowledge Modus")).not.toBeInTheDocument();
  });

  it("renders the persistent left navigation and opens case history as a drawer", async () => {
    const user = userEvent.setup();

    render(
      <DashboardShell>
        <main>Arbeitsbereich</main>
      </DashboardShell>,
    );

    expect(screen.getAllByRole("link", { name: "Neue Analyse" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "SEO" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Goal" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "SealingPedia Upload" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dokumente" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einstellungen" })).toBeInTheDocument();
    expect(screen.queryByText("Verlauf")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Historie einblenden" }));

    expect(screen.getByText("Verlauf")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("link", { name: /RWDR Wasser-Glykol/ })).toBeInTheDocument());
  });

  it("collapses and restores the left history column", async () => {
    const user = userEvent.setup();

    render(
      <DashboardShell>
        <main>Arbeitsbereich</main>
      </DashboardShell>,
    );

    await user.click(screen.getByRole("button", { name: "Historie einblenden" }));
    await waitFor(() => expect(screen.getByRole("link", { name: /RWDR Wasser-Glykol/ })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Historie ausblenden" }));

    expect(screen.queryByText("Verlauf")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /RWDR Wasser-Glykol/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Historie einblenden" }));

    expect(screen.getByText("Verlauf")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("link", { name: /RWDR Wasser-Glykol/ })).toBeInTheDocument());
  });
});
