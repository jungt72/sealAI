import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import PocketCockpit from "@/components/dashboard/PocketCockpit";
import type { ActionChip, PocketCockpitPatch } from "@/lib/contracts/agent";

const PATCH: PocketCockpitPatch = {
  recognized: [
    { label: "Dichtungstyp", value: "RWDR", status: "confirmed" },
    { label: "Medium", value: "Öl", status: "confirmed" },
  ],
  critical: [{ label: "Wellenlauffläche prüfen", severity: "high" }],
  next_step: { question: "Dreht sich die Welle?", field: "shaft_rotates" },
  rfq_status: "DRAFT",
  details_available: true,
  collapsed_by_default: true,
};

const CHIPS: ActionChip[] = [
  { label: "Ja", value: "yes", field: "shaft_rotates" },
  { label: "Foto senden", action: "upload_photo" },
];

describe("PocketCockpit", () => {
  it("renders the four compressed sections", () => {
    render(<PocketCockpit patch={PATCH} />);
    expect(screen.getByTestId("pocket-recognized")).toHaveTextContent("Dichtungstyp");
    expect(screen.getByTestId("pocket-recognized")).toHaveTextContent("RWDR");
    expect(screen.getByTestId("pocket-critical")).toHaveTextContent("Wellenlauffläche prüfen");
    expect(screen.getByTestId("pocket-next-step")).toHaveTextContent("Dreht sich die Welle?");
    expect(screen.getByTestId("pocket-rfq-status")).toHaveTextContent("DRAFT");
  });

  it("renders action chips and emits selection events without mutating", async () => {
    const user = userEvent.setup();
    const onActionChip = vi.fn();
    render(<PocketCockpit patch={PATCH} actionChips={CHIPS} onActionChip={onActionChip} />);

    const chips = screen.getAllByTestId("pocket-action-chip");
    expect(chips).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: /Ja/ }));
    expect(onActionChip).toHaveBeenCalledTimes(1);
    expect(onActionChip).toHaveBeenCalledWith(CHIPS[0]);
  });

  it("renders backend-provided V1.6 action chips as non-mutating suggestions", () => {
    // Mirrors what CaseScreen passes after resolvePocketCockpitView prefers the
    // backend pocket_cockpit_patch / action_chips (Patch 6). Rendering alone must
    // not trigger any chip selection — click handling is intentionally out of
    // scope for this patch.
    const onActionChip = vi.fn();
    const backendChips: ActionChip[] = [
      { label: "Ja", value: "yes", field: "shaft_rotates" },
      { label: "Nein", value: "no", field: "shaft_rotates" },
      { label: "Weiß ich nicht", value: "unknown", field: "shaft_rotates" },
    ];
    render(<PocketCockpit patch={PATCH} actionChips={backendChips} onActionChip={onActionChip} />);

    const chips = screen.getAllByTestId("pocket-action-chip");
    expect(chips).toHaveLength(3);
    expect(screen.getByTestId("pocket-action-chips")).toHaveTextContent("Weiß ich nicht");
    // No mutation happens just by rendering the suggestions.
    expect(onActionChip).not.toHaveBeenCalled();
  });

  it("shows an immediate progress state instead of an empty spinner while loading", () => {
    render(<PocketCockpit patch={null} isLoading />);
    const progress = screen.getByTestId("pocket-progress");
    expect(progress).toBeInTheDocument();
    expect(progress.textContent?.trim().length ?? 0).toBeGreaterThan(0);
  });

  it("uses the provided progress text when loading with no content", () => {
    render(<PocketCockpit patch={null} isLoading progressText="Ich prüfe das als Leckagefall …" />);
    expect(screen.getByTestId("pocket-progress")).toHaveTextContent("Ich prüfe das als Leckagefall …");
  });

  it("renders nothing when there is neither a patch nor loading state", () => {
    const { container } = render(<PocketCockpit patch={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
