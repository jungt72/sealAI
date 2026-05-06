import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChatPane from "./ChatPane";

const agentStreamMockState = vi.hoisted(() => ({
  activeCaseId: "case-parameter",
  messages: [] as Array<{
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
  }>,
  streamingText: "",
  streamWorkspace: null as null | Record<string, unknown>,
  isStreaming: false,
  error: null as string | null,
  sendMessage: vi.fn(),
  clearError: vi.fn(),
}));

const workspaceStoreMock = vi.hoisted(() => ({
  setStreamWorkspace: vi.fn(),
  setActiveResponseClass: vi.fn(),
}));

const chatStoreMock = vi.hoisted(() => ({
  registerCallbacks: vi.fn(),
  setActiveCaseId: vi.fn(),
}));

vi.mock("@/components/dashboard/ChatComposer", () => ({
  default: ({ externalValue, onSend, isLoading }: { externalValue?: string | null; onSend: (message: string) => void; isLoading: boolean }) => (
    <button type="button" data-loading={isLoading} data-value={externalValue ?? ""} onClick={() => onSend("Composer text")}>
      ChatComposer
    </button>
  ),
}));

vi.mock("@/hooks/useAgentStream", () => ({
  useAgentStream: () => agentStreamMockState,
}));

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      setStreamWorkspace: workspaceStoreMock.setStreamWorkspace,
      setActiveResponseClass: workspaceStoreMock.setActiveResponseClass,
    }),
}));

vi.mock("@/lib/store/chatStore", () => ({
  useChatStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      registerCallbacks: chatStoreMock.registerCallbacks,
      setActiveCaseId: chatStoreMock.setActiveCaseId,
    }),
}));

describe("ChatPane", () => {
  beforeEach(() => {
    agentStreamMockState.activeCaseId = "case-parameter";
    agentStreamMockState.messages = [];
    agentStreamMockState.streamingText = "";
    agentStreamMockState.streamWorkspace = null;
    agentStreamMockState.isStreaming = false;
    agentStreamMockState.error = null;
    agentStreamMockState.sendMessage.mockReset();
    agentStreamMockState.clearError.mockReset();
    workspaceStoreMock.setStreamWorkspace.mockReset();
    workspaceStoreMock.setActiveResponseClass.mockReset();
    chatStoreMock.registerCallbacks.mockReset();
    chatStoreMock.setActiveCaseId.mockReset();
    window.history.replaceState(null, "", "/dashboard/case-parameter");
    window.localStorage.clear();
  });

  it("places the composer in a centered first-run state without prompt bubbles", async () => {
    const user = userEvent.setup();
    agentStreamMockState.activeCaseId = "";

    render(<ChatPane />);

    expect(screen.getByRole("button", { name: "ChatComposer" })).toBeInTheDocument();
    expect(screen.queryByText(/Governed RFQ Qualification/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/belastbare Anfragebasis/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Welche Angaben fehlen noch für eine belastbare Anfragebasis?" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dichtungsfall mit Medium, Temperatur, Druck und Drehzahl analysieren." })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "ChatComposer" }));

    expect(agentStreamMockState.sendMessage).toHaveBeenCalledWith("Composer text");
  });

  it("registers chat callbacks and keeps the active case id in shared state", () => {
    render(<ChatPane caseId="case-parameter" />);

    expect(chatStoreMock.registerCallbacks).toHaveBeenCalledWith({
      sendMessage: agentStreamMockState.sendMessage,
      startNewChat: expect.any(Function),
    });
    expect(chatStoreMock.setActiveCaseId).toHaveBeenCalledWith("case-parameter");
    expect(window.localStorage.getItem("sealai:lastCaseId")).toBe("case-parameter");
  });

  it("hides start suggestions after the conversation starts and renders messages", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "Dichtungsfall mit Wasser, 80 Grad und 6 bar." },
      { role: "assistant", content: "Welche Flansch- oder Normgeometrie liegt vor?" },
    ];

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("Dichtungsfall mit Wasser, 80 Grad und 6 bar.")).toBeInTheDocument();
    expect(screen.getByText("Welche Flansch- oder Normgeometrie liegt vor?")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dichtungsfall mit Medium, Temperatur, Druck und Drehzahl analysieren." })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Medienliste prüfen" })).not.toBeInTheDocument();
  });

  it("renders a restrained streaming placeholder before text chunks arrive", () => {
    agentStreamMockState.isStreaming = true;

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("sealingAI verbindet den LLM-Stream...")).toBeInTheDocument();
  });

  it("forwards composer messages to the agent stream", async () => {
    const user = userEvent.setup();
    agentStreamMockState.activeCaseId = "";

    render(<ChatPane initialGoal="Goal text" />);

    await user.click(screen.getByRole("button", { name: "ChatComposer" }));

    expect(agentStreamMockState.sendMessage).toHaveBeenCalledWith("Composer text");
    expect(screen.getByRole("button", { name: "ChatComposer" })).toHaveAttribute("data-value", "Goal text");
  });

  it("surfaces stream errors with a dismiss action", async () => {
    const user = userEvent.setup();
    agentStreamMockState.error = "Backend nicht erreichbar";

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("Backend nicht erreichbar")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Schließen" }));
    expect(agentStreamMockState.clearError).toHaveBeenCalledTimes(1);
  });
});
