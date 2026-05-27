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
    window.localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "internal-db-id",
              case_number: "case-42",
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

    expect(screen.getByTestId("sealai-header-wordmark")).toHaveAccessibleName("SEALING Intelligence");
    expect(screen.getByTestId("sealai-sidebar-corner-logo")).toBeInTheDocument();
    expect(screen.getByTestId("sealai-circular-s-logo")).toBeInTheDocument();
    expect(screen.getByText("SEALING")).toBeInTheDocument();
    expect(screen.getByText("INTELLIGENCE")).toBeInTheDocument();
    expect(screen.queryByText(/Arbeitsraum:/)).not.toBeInTheDocument();
    expect(screen.queryByText("Governed")).not.toBeInTheDocument();
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

    expect(screen.getByRole("link", { name: "Neuer Chat" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Meine Inhalte" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "SEO" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analytics" })).toHaveAttribute("href", "/dashboard/analytics");
    expect(screen.getByRole("link", { name: "Analytics" })).not.toHaveAttribute("target");
    expect(screen.getByRole("link", { name: "Goal" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "SealingPedia" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dokumente" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einstellungen" })).toBeInTheDocument();
    expect(screen.queryByText("Chats")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Seitenleiste ausklappen" }));

    expect(screen.getByText("Chats")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("link", { name: /RWDR Wasser-Glykol/ })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /RWDR Wasser-Glykol/ })).toHaveAttribute(
      "href",
      "/dashboard/case-42",
    );
  });

  it("collapses and restores the left history column", async () => {
    const user = userEvent.setup();

    render(
      <DashboardShell>
        <main>Arbeitsbereich</main>
      </DashboardShell>,
    );

    await user.click(screen.getByRole("button", { name: "Seitenleiste ausklappen" }));
    await waitFor(() => expect(screen.getByRole("link", { name: /RWDR Wasser-Glykol/ })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Seitenleiste einklappen" }));

    expect(screen.queryByText("Chats")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /RWDR Wasser-Glykol/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Seitenleiste ausklappen" }));

    expect(screen.getByText("Chats")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("link", { name: /RWDR Wasser-Glykol/ })).toBeInTheDocument());
  });
});
