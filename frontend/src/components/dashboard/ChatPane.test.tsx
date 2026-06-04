import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPane from "./ChatPane";

const agentStreamMockState = vi.hoisted(() => ({
  activeCaseId: "case-parameter",
  messages: [] as Array<{
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
  }>,
  streamingText: "",
  streamingStatusText: "",
  streamWorkspace: null as null | Record<string, unknown>,
  isStreaming: false,
  error: null as string | null,
  sendMessage: vi.fn(),
  appendAssistantMessage: vi.fn(),
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

let viewportScrollHeight = 1200;

vi.mock("@/components/dashboard/ChatComposer", () => ({
  default: ({ externalValue, onSend, isLoading }: { externalValue?: string | null; onSend: (message: string) => void; isLoading: boolean }) => (
    <button type="button" data-loading={isLoading} data-value={externalValue ?? ""} onClick={() => onSend("Composer text")}>
      ChatComposer
    </button>
  ),
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: {
      user: {
        name: "Thorsten Jung",
        email: "thorsten@example.com",
      },
      idToken: null,
    },
    status: "authenticated",
  }),
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    agentStreamMockState.activeCaseId = "case-parameter";
    agentStreamMockState.messages = [];
    agentStreamMockState.streamingText = "";
    agentStreamMockState.streamingStatusText = "";
    agentStreamMockState.streamWorkspace = null;
    agentStreamMockState.isStreaming = false;
    agentStreamMockState.error = null;
    viewportScrollHeight = 1200;
    agentStreamMockState.sendMessage.mockReset();
    agentStreamMockState.appendAssistantMessage.mockReset();
    agentStreamMockState.clearError.mockReset();
    workspaceStoreMock.setStreamWorkspace.mockReset();
    workspaceStoreMock.setActiveResponseClass.mockReset();
    chatStoreMock.registerCallbacks.mockReset();
    chatStoreMock.setActiveCaseId.mockReset();
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      writable: true,
      value: function scrollTo() {},
    });
    vi.spyOn(HTMLElement.prototype, "scrollTo").mockImplementation(function scrollTo(
      this: HTMLElement,
      options?: ScrollToOptions | number,
      y?: number,
    ) {
      const nextTop = typeof options === "number" ? y ?? 0 : options?.top ?? this.scrollTop;
      Object.defineProperty(this, "scrollTop", {
        configurable: true,
        writable: true,
        value: nextTop,
      });
    });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function getBoundingClientRect(
      this: HTMLElement,
    ) {
      const element = this;
      const top = element.dataset.testid === "chat-scroll-region" ? 100 : element.dataset.latestUser ? 260 : 0;
      return {
        x: 0,
        y: top,
        top,
        left: 0,
        right: 800,
        bottom: top + 48,
        width: 800,
        height: 48,
        toJSON: () => ({}),
      };
    });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get() {
        return (this as HTMLElement).dataset.testid === "chat-scroll-region" ? 500 : 48;
      },
    });
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
      configurable: true,
      get() {
        const element = this as HTMLElement;
        if (element.dataset.testid !== "chat-scroll-region") {
          return 48;
        }
        const spacer = element.querySelector<HTMLElement>('[data-testid="submit-anchor-spacer"]');
        const spacerHeight = spacer ? Number.parseInt(spacer.style.height || "0", 10) || 0 : 0;
        return viewportScrollHeight + spacerHeight;
      },
    });
    window.history.replaceState(null, "", "/dashboard/case-parameter");
    window.localStorage.clear();
  });

  it("places message identity icons above the related text", () => {
    agentStreamMockState.messages = [
      { role: "assistant", content: "Hallo Antwort", timestamp: "1" },
      { role: "user", content: "Hallo Frage", timestamp: "2" },
    ];

    render(<ChatPane caseId="case-parameter" />);

    const assistantAvatar = screen.getByTestId("message-avatar-assistant");
    const userAvatar = screen.getByTestId("message-avatar-user");
    const assistantText = screen.getByText("Hallo Antwort");
    const userText = screen.getByText("Hallo Frage");

    expect(assistantAvatar.compareDocumentPosition(assistantText) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(userText.compareDocumentPosition(userAvatar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("places the composer in a centered first-run state without prompt chips", async () => {
    const user = userEvent.setup();
    agentStreamMockState.activeCaseId = "";

    render(<ChatPane />);

    expect(screen.queryByText("Hallo Thorsten")).not.toBeInTheDocument();
    expect(screen.queryByText("Schön, dass du wieder hier bist.")).not.toBeInTheDocument();
    expect(screen.getByText("Womit sollen wir anfangen?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ChatComposer" })).toBeInTheDocument();
    expect(screen.queryByText(/Governed RFQ Qualification/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/belastbare Anfragebasis/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lösung erarbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Material vergleichen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Materialdetails" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "ChatComposer" }));

    expect(agentStreamMockState.sendMessage).toHaveBeenCalledWith("Composer text");
  });

  it("registers chat callbacks and keeps the active case id in shared state", () => {
    render(<ChatPane caseId="case-parameter" />);

    expect(chatStoreMock.registerCallbacks).toHaveBeenCalledWith({
      appendAssistantMessage: expect.any(Function),
      sendMessage: expect.any(Function),
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

  it("keeps the message list scrollable while the composer stays docked", () => {
    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByTestId("chat-scroll-region")).toHaveClass(
      "chat-scroll-viewport",
      "min-h-0",
      "flex-1",
      "overflow-y-auto",
    );
    expect(screen.getByTestId("chat-scroll-region")).toHaveAttribute("role", "log");
    expect(screen.getByTestId("chat-scroll-region")).toHaveAttribute("aria-busy", "false");
    expect(screen.getByTestId("chat-composer-dock")).toHaveClass("shrink-0");
  });

  it("anchors the latest user turn from the composer near the viewport top and freezes streaming growth", async () => {
    const user = userEvent.setup();
    agentStreamMockState.activeCaseId = "case-parameter";
    agentStreamMockState.messages = [{ role: "assistant", content: "Vorherige Antwort", timestamp: "1" }];

    const { rerender } = render(<ChatPane caseId="case-parameter" />);
    await user.click(screen.getByRole("button", { name: "ChatComposer" }));
    expect(agentStreamMockState.sendMessage).toHaveBeenCalledWith("Composer text");

    agentStreamMockState.messages = [
      { role: "assistant", content: "Vorherige Antwort", timestamp: "1" },
      { role: "user", content: "Composer text", timestamp: "2" },
    ];
    agentStreamMockState.isStreaming = true;
    agentStreamMockState.streamingText = "Der erste Stream-Chunk";
    rerender(<ChatPane caseId="case-parameter" />);

    const viewport = screen.getByTestId("chat-scroll-region") as HTMLElement;

    await waitFor(() => {
      expect(viewport.scrollTop).toBe(1250);
    });
    const anchoredTop = viewport.scrollTop;
    expect(screen.getByTestId("submit-anchor-spacer")).toHaveStyle({ height: "550px" });

    viewportScrollHeight = 2400;
    agentStreamMockState.streamingText = "Der erste Stream-Chunk mit deutlich mehr Text";
    rerender(<ChatPane caseId="case-parameter" />);

    expect(viewport.scrollTop).toBe(anchoredTop);
    expect(screen.getByTestId("submit-anchor-spacer")).toHaveStyle({ height: "0px" });
    expect(screen.getByRole("button", { name: "Zum aktuellen Ende" })).toBeInTheDocument();
  });

  it("resumes live-follow only after the user explicitly jumps to the current end", async () => {
    const user = userEvent.setup();
    agentStreamMockState.activeCaseId = "case-parameter";

    const { rerender } = render(<ChatPane caseId="case-parameter" />);
    const callbacks = chatStoreMock.registerCallbacks.mock.calls.at(-1)?.[0] as { sendMessage: (message: string) => void };
    callbacks.sendMessage("Bitte vergleiche PTFE und NBR");

    agentStreamMockState.messages = [
      { role: "user", content: "Bitte vergleiche PTFE und NBR", timestamp: "1" },
    ];
    agentStreamMockState.isStreaming = true;
    agentStreamMockState.streamingText = "Antwort läuft";
    viewportScrollHeight = 2400;
    rerender(<ChatPane caseId="case-parameter" />);

    const viewport = screen.getByTestId("chat-scroll-region") as HTMLElement;

    expect(screen.getByRole("button", { name: "Zum aktuellen Ende" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Zum aktuellen Ende" }));

    expect(viewport.scrollTop).toBe(2400);
  });

  it("renders a restrained streaming placeholder before text chunks arrive", () => {
    agentStreamMockState.isStreaming = true;
    agentStreamMockState.streamingStatusText = "SealingAI bewertet technische Risiken...";

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByTestId("thinking-indicator")).toBeInTheDocument();
    expect(screen.getByText("SealingAI bewertet technische Risiken...")).toBeInTheDocument();
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
