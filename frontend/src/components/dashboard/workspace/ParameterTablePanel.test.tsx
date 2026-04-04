import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ParameterTablePanel from "@/components/dashboard/workspace/ParameterTablePanel";

const {
  sendMessage,
  patchAgentOverrides,
  refreshWorkspace,
  setStreamAssertions,
} = vi.hoisted(() => ({
  sendMessage: vi.fn(),
  patchAgentOverrides: vi.fn(),
  refreshWorkspace: vi.fn(),
  setStreamAssertions: vi.fn(),
}));

const workspaceStoreState = {
  streamAssertions: null as Record<string, { value: string; confidence: string }> | null,
  streamWorkspace: null,
  setStreamAssertions,
  refreshWorkspace,
  workspace: {
    communication: {
      confirmedFactsSummary: [] as string[],
    },
    mediumContext: {
      mediumLabel: null as string | null,
    },
    mediumClassification: {
      canonicalLabel: null as string | null,
    },
    summary: {
      turnCount: 3,
    },
  },
};

vi.mock("@/lib/bff/parameterOverride", () => ({
  patchAgentOverrides,
}));

vi.mock("@/lib/store/caseStore", () => ({
  useCaseStore: (selector: (state: { caseId: string | null }) => unknown) =>
    selector({ caseId: "case-123" }),
}));

vi.mock("@/lib/store/chatStore", () => ({
  useChatStore: (selector: (state: { sendMessage: typeof sendMessage }) => unknown) =>
    selector({ sendMessage }),
}));

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: typeof workspaceStoreState) => unknown) =>
    selector(workspaceStoreState),
}));

describe("ParameterTablePanel", () => {
  const getMediumInput = (): HTMLInputElement => {
    const label = screen.getByText("Medium");
    const container = label.parentElement?.parentElement;
    const input = container?.querySelector("input");
    if (!(input instanceof HTMLInputElement)) {
      throw new Error("Medium input not found");
    }
    return input;
  };

  beforeEach(() => {
    sendMessage.mockReset();
    patchAgentOverrides.mockReset();
    refreshWorkspace.mockReset();
    setStreamAssertions.mockReset();
    workspaceStoreState.streamAssertions = null;
    workspaceStoreState.streamWorkspace = null;
    workspaceStoreState.workspace.communication.confirmedFactsSummary = [];
    workspaceStoreState.workspace.mediumContext.mediumLabel = null;
    workspaceStoreState.workspace.mediumClassification.canonicalLabel = null;
  });

  it("sends workspace edits through the override path instead of chat fallback", async () => {
    patchAgentOverrides.mockResolvedValue({
      session_id: "case-123",
      applied_fields: ["medium"],
      governance: {
        gov_class: "B",
        rfq_admissible: false,
        blocking_unknowns: [],
        conflict_flags: [],
        validity_limits: [],
        open_validation_points: [],
      },
    });

    render(<ParameterTablePanel />);

    const mediumInput = getMediumInput();
    fireEvent.change(mediumInput, { target: { value: "Wasser" } });
    fireEvent.blur(mediumInput);

    await waitFor(() =>
      expect(patchAgentOverrides).toHaveBeenCalledWith("case-123", {
        overrides: [{ field_name: "medium", value: "Wasser", unit: undefined }],
        turn_index: 3,
      }),
    );
    expect(sendMessage).not.toHaveBeenCalled();
    expect(setStreamAssertions).toHaveBeenCalledWith({
      medium: { value: "Wasser", confidence: "user_override" },
    });
    expect(refreshWorkspace).toHaveBeenCalledTimes(1);
  });

  it("shows a visible error when the structured override request fails", async () => {
    patchAgentOverrides.mockRejectedValue(new Error("override failed"));

    render(<ParameterTablePanel />);

    const mediumInput = getMediumInput();
    fireEvent.change(mediumInput, { target: { value: "Wasser" } });
    fireEvent.blur(mediumInput);

    expect(await screen.findByText("override failed")).toBeInTheDocument();
    expect(sendMessage).not.toHaveBeenCalled();
    expect(setStreamAssertions).not.toHaveBeenCalled();
    expect(refreshWorkspace).not.toHaveBeenCalled();
  });

  it("falls back to canonical workspace facts when no stream medium is present", () => {
    workspaceStoreState.workspace.communication.confirmedFactsSummary = ["Medium: Salzwasser"];

    render(<ParameterTablePanel />);

    expect(getMediumInput().value).toBe("Salzwasser");
  });

  it("uses medium context as canonical fallback when confirmed facts are absent", () => {
    workspaceStoreState.workspace.mediumContext.mediumLabel = "Meerwasser";

    render(<ParameterTablePanel />);

    expect(getMediumInput().value).toBe("Meerwasser");
  });

  it("uses medium classification as canonical fallback before medium context", () => {
    workspaceStoreState.workspace.mediumClassification.canonicalLabel = "Salzwasser";
    workspaceStoreState.workspace.mediumContext.mediumLabel = "Meerwasser";

    render(<ParameterTablePanel />);

    expect(getMediumInput().value).toBe("Salzwasser");
  });
});
