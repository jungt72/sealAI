import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChatPane from "./ChatPane";

const agentStreamMockState = vi.hoisted(() => ({
  activeCaseId: "case-parameter",
  messages: [] as Array<{ role: "user" | "assistant"; content: string }>,
  streamingText: "",
  streamWorkspace: null as null | Record<string, unknown>,
  isStreaming: false,
  error: null as string | null,
  sendMessage: vi.fn(),
  clearError: vi.fn(),
}));

const decideCaseDeltaMock = vi.hoisted(() => vi.fn());

vi.mock("@/components/dashboard/ChatComposer", () => ({
  default: () => <div data-testid="chat-composer" />,
}));

vi.mock("@/hooks/useAgentStream", () => ({
  useAgentStream: () => agentStreamMockState,
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
  decideCaseDelta: decideCaseDeltaMock,
}));

vi.mock("@/lib/ragApi", () => ({
  uploadRagDocument: vi.fn(),
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
    decideCaseDeltaMock.mockReset();
    decideCaseDeltaMock.mockResolvedValue({
      session_id: "case-parameter",
      action: "accept",
      source_event_id: "event-1",
      applied_fields: ["medium"],
      rejected_fields: [],
      governance: {},
    });
  });

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

  it("auto-accepts safe user-stated chat deltas as working state", async () => {
    const onTurnComplete = vi.fn();
    agentStreamMockState.messages = [
      { role: "user", content: "Flachdichtung, Wasser, 80 Grad." },
      { role: "assistant", content: "Das ist ein guter Arbeitsstand." },
    ];
    agentStreamMockState.streamWorkspace = {
      proposedCaseDelta: {
        fields: [
          {
            field_name: "medium",
            proposed_value: "Wasser",
            confidence: "estimated",
            confirmation_required: true,
            status: "proposed",
          },
          {
            field_name: "temperature_c",
            proposed_value: 80,
            unit: "°C",
            provenance: "user_stated",
            confidence: "estimated",
            confirmation_required: false,
            status: "proposed",
          },
          {
            field_name: "installation",
            proposed_value: "flange",
            provenance: "inferred",
            confidence: "inferred",
            confirmation_required: true,
            status: "proposed",
          },
          {
            field_name: "material",
            proposed_value: "Flachdichtung",
            provenance: "inferred",
            confidence: "estimated",
            confirmation_required: true,
            status: "proposed",
          },
        ],
      },
    };

    render(<ChatPane caseId="case-parameter" onTurnComplete={onTurnComplete} />);

    await waitFor(() => {
      expect(decideCaseDeltaMock).toHaveBeenCalledWith(
        "case-parameter",
        "accept",
        ["medium", "temperature_c", "installation"],
      );
    });
    await waitFor(() => expect(onTurnComplete).toHaveBeenCalledWith("case-parameter"));
    expect(screen.queryByText("Vorgeschlagene Case-Aenderung")).not.toBeInTheDocument();
  });

  it("keeps confirmation-required deltas in the manual review path", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "Viton bei Dampf." },
      { role: "assistant", content: "Das ist ein guter Arbeitsstand." },
    ];
    agentStreamMockState.streamWorkspace = {
      proposedCaseDelta: {
        source: "llm",
        fields: [
          {
            field_name: "material",
            proposed_value: "FKM",
            provenance: "user_stated",
            confidence: "requires_confirmation",
            confirmation_required: true,
            status: "proposed",
          },
        ],
      },
    };

    render(<ChatPane caseId="case-parameter" />);

    expect(decideCaseDeltaMock).not.toHaveBeenCalled();
    expect(screen.getByText("Vorgeschlagene Case-Aenderung")).toBeInTheDocument();
    expect(screen.getByText("material")).toBeInTheDocument();
  });

  it("keeps document deltas in the manual review path", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "Ich habe ein Datenblatt hochgeladen." },
      { role: "assistant", content: "Dokument analysiert." },
    ];
    agentStreamMockState.streamWorkspace = {
      proposedCaseDelta: {
        source: "document",
        fields: [
          {
            field_name: "medium",
            proposed_value: "Wasser",
            provenance: "documented",
            confidence: "estimated",
            confirmation_required: false,
            status: "proposed",
          },
        ],
      },
    };

    render(<ChatPane caseId="case-parameter" />);

    expect(decideCaseDeltaMock).not.toHaveBeenCalled();
    expect(screen.getByText("Vorgeschlagene Case-Aenderung")).toBeInTheDocument();
  });

  it("keeps documented-provenance deltas in the manual review path even when source is missing", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "Datenblatt liegt vor." },
      { role: "assistant", content: "Dokument analysiert." },
    ];
    agentStreamMockState.streamWorkspace = {
      proposedCaseDelta: {
        fields: [
          {
            field_name: "medium",
            proposed_value: "Wasser",
            provenance: "documented",
            confidence: "estimated",
            confirmation_required: false,
            status: "proposed",
          },
        ],
      },
    };

    render(<ChatPane caseId="case-parameter" />);

    expect(decideCaseDeltaMock).not.toHaveBeenCalled();
    expect(screen.getByText("Vorgeschlagene Case-Aenderung")).toBeInTheDocument();
  });
});
