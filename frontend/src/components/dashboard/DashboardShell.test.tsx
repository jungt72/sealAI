import { render, screen, waitFor } from "@testing-library/react";
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

  it("renders the persistent left navigation and case history shell", async () => {
    render(
      <DashboardShell>
        <main>Arbeitsbereich</main>
      </DashboardShell>,
    );

    expect(screen.getAllByRole("link", { name: "Neue Analyse" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Goal" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Wissensbasis" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dokumente" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einstellungen" })).toBeInTheDocument();
    expect(screen.getByText("Verlauf")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("link", { name: /RWDR Wasser-Glykol/ })).toBeInTheDocument());
  });
});
