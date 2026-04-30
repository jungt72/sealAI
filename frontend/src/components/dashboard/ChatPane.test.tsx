import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ChatPane from "./ChatPane";

vi.mock("@/components/dashboard/ChatComposer", () => ({
  default: () => <div data-testid="chat-composer" />,
}));

vi.mock("@/hooks/useAgentStream", () => ({
  useAgentStream: () => ({
    activeCaseId: "case-parameter",
    messages: [],
    streamingText: "",
    streamWorkspace: null,
    isStreaming: false,
    error: null,
    sendMessage: vi.fn(),
    clearError: vi.fn(),
  }),
}));

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      registerCallbacks: vi.fn(),
      setStreamWorkspace: vi.fn(),
      setActiveResponseClass: vi.fn(),
    }),
}));

vi.mock("@/lib/bff/caseDelta", () => ({
  decideCaseDelta: vi.fn(),
}));

vi.mock("@/lib/ragApi", () => ({
  uploadRagDocument: vi.fn(),
}));

describe("ChatPane", () => {
  it("renders parameter confirmations as chat messages even before prior chat history exists", () => {
    render(
      <ChatPane
        caseId="case-parameter"
        parameterConfirmation="Parameter als Nutzerangaben übernommen: Drehzahl: 1450 rpm."
      />,
    );

    expect(screen.getByText("Parameter als Nutzerangaben übernommen: Drehzahl: 1450 rpm.")).toBeInTheDocument();
    expect(screen.queryByText("Hallo Thorsten,")).not.toBeInTheDocument();
  });
});
