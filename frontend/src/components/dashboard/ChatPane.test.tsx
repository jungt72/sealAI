import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChatPane from "./ChatPane";

const agentStreamMockState = vi.hoisted(() => ({
  activeCaseId: "case-parameter",
  messages: [] as Array<{
    role: "user" | "assistant";
    content: string;
    answerSource?: "answer_markdown" | "reply" | "text_chunk";
  }>,
  streamingText: "",
  streamingAnswerSource: null as null | "answer_markdown" | "reply" | "text_chunk",
  streamWorkspace: null as null | Record<string, unknown>,
  isStreaming: false,
  error: null as string | null,
  sendMessage: vi.fn(),
  clearError: vi.fn(),
}));

const decideCaseDeltaMock = vi.hoisted(() => vi.fn());
const workspaceMockState = vi.hoisted(() => ({
  workspace: null as null | Record<string, unknown>,
}));

vi.mock("@/components/dashboard/ChatComposer", () => ({
  default: () => <div data-testid="chat-composer" />,
}));

vi.mock("@/hooks/useAgentStream", () => ({
  useAgentStream: () => agentStreamMockState,
}));

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      workspace: workspaceMockState.workspace,
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
    agentStreamMockState.streamingAnswerSource = null;
    agentStreamMockState.streamWorkspace = null;
    agentStreamMockState.isStreaming = false;
    agentStreamMockState.error = null;
    workspaceMockState.workspace = null;
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

  it("places the first-run suggestions in the centered greeting state", async () => {
    const user = userEvent.setup();

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("Hallo Thorsten,")).toBeInTheDocument();
    expect(screen.getByTestId("chat-composer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "PTFE-RWDR für rotierende Welle" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Gleitringdichtung für Pumpe" }));

    expect(agentStreamMockState.sendMessage).toHaveBeenCalledWith("Gleitringdichtung für Pumpe");
  });

  it("hides the first-run suggestion bubbles after the conversation starts", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "PTFE-RWDR für rotierende Welle" },
      { role: "assistant", content: "Gut, dann klären wir zuerst Medium und Betriebsdaten." },
    ];

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.queryByRole("button", { name: "PTFE-RWDR für rotierende Welle" })).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-composer")).toBeInTheDocument();
  });

  it("renders assistant replies without a bordered bubble surface", () => {
    agentStreamMockState.messages = [
      { role: "assistant", content: "Gern, dann grenzen wir den Fall sauber ein." },
    ];

    render(<ChatPane caseId="case-parameter" />);

    const assistantText = screen.getByText("Gern, dann grenzen wir den Fall sauber ein.");
    const assistantSurface = assistantText.closest(".max-w-\\[min\\(720px\\,84\\%\\)\\]");
    expect(assistantSurface).not.toHaveClass("border");
    expect(assistantSurface).not.toHaveClass("bg-white");
    expect(assistantSurface).not.toHaveClass("shadow-sm");
  });

  it("turns internal working-state markdown into human chat language", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "Flachdichtung, Wasser, 80 Grad und 6 bar." },
      {
        role: "assistant",
        content:
          "**Arbeitsstand:** Wasser, 80 °C und 6 bar.\n\n" +
          "- Dichtungsart: Flachdichtung\n" +
          "- Einbausituation: noch offen\n\n" +
          "**Naechste sinnvolle Frage:** Sitzt die Dichtung zwischen zwei genormten Flanschen?",
      },
    ];

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("Alles klar, das reicht für den nächsten Schritt.")).toBeInTheDocument();
    expect(screen.getByText("Sitzt die Dichtung zwischen zwei genormten Flanschen?")).toBeInTheDocument();
    expect(screen.queryByText(/Wasser, 80 °C und 6 bar/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Dichtungsart: Flachdichtung/)).not.toBeInTheDocument();
    expect(screen.queryByText("Arbeitsstand:")).not.toBeInTheDocument();
    expect(screen.queryByText("Naechste sinnvolle Frage:")).not.toBeInTheDocument();
  });

  it("replaces the generic clarification fallback with the backend next-best-question projection", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "Flachdichtung fuer DN50 PN16 Flansch, Wasser bei 80 Grad und 6 bar" },
      {
        role: "assistant",
        content:
          "**Arbeitsstand:** Das ist ein guter erster Stand.\n\n" +
          "**Naechste sinnvolle Frage:** Wo sitzt die Dichtung genau?",
      },
    ];
    workspaceMockState.workspace = {
      decisionUnderstanding: {
        understoodNow: ["Medium: Wasser", "Temperatur max.: 80 °C", "Druck: 6 bar"],
        technicalMeaning: ["Bei Flachdichtungen bestimmt der Flanschstandard die Geometrie."],
        nextBestQuestion: "Welche Flansch- oder Normgeometrie liegt vor?",
        nextBestQuestions: [
          {
            question: "Welche Flansch- oder Normgeometrie liegt vor?",
            reason: "Bei Flachdichtungen bestimmt der Flanschstandard die Geometrie.",
          },
        ],
      },
      communication: {},
    };

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("Alles klar, das reicht für den nächsten Schritt.")).toBeInTheDocument();
    expect(screen.getByText("Welche Flansch- oder Normgeometrie liegt vor?")).toBeInTheDocument();
    expect(screen.queryByText(/Medium: Wasser/)).not.toBeInTheDocument();
    expect(screen.queryByText("Wo sitzt die Dichtung genau?")).not.toBeInTheDocument();
    expect(screen.queryByText("Arbeitsstand:")).not.toBeInTheDocument();
  });

  it("renders explicit answer_markdown chat text without cockpit/workspace rewriting", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "Hallo" },
      {
        role: "assistant",
        content: "real assistant answer",
        answerSource: "answer_markdown",
      },
    ];
    workspaceMockState.workspace = {
      decisionUnderstanding: {
        understoodNow: ["Noch kein technischer Fall"],
        technicalMeaning: ["Starte, sobald ein Dichtungsfall beschrieben ist"],
        nextBestQuestion: "Noch nicht möglich",
        nextBestQuestions: [
          {
            question: "Noch nicht möglich",
            reason: "Starte, sobald ein Dichtungsfall beschrieben ist",
          },
        ],
      },
      communication: {
        primaryQuestion: "Noch kein technischer Fall",
        supportingReason: "Noch nicht möglich",
      },
    };

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("real assistant answer")).toBeInTheDocument();
    expect(screen.queryByText(/Noch kein technischer Fall/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Noch nicht möglich/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Starte, sobald/)).not.toBeInTheDocument();
  });

  it("does not expose internal open-field reasoning as chat copy", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "danke, ich möchte meine dichtungssituation besprechen" },
      {
        role: "assistant",
        content:
          "**Arbeitsstand:** Ich habe deine Angaben als aktuellen Arbeitsstand übernommen.\n\n" +
          "Dichtungstyp-Richtung: Dichtungstyp offen\n\n" +
          "**Warum das wichtig ist:** Der Dichtungstyp grenzt Pflichtangaben, Risiken und den Herstellerpruefpfad zuerst ein.\n\n" +
          "**Naechste sinnvolle Frage:** Um welchen Dichtungstyp geht es, zum Beispiel O-Ring, Wellendichtring, Flachdichtung, Hydraulikdichtung oder Gleitringdichtung?",
      },
    ];

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("Gern. Dann lass uns die Dichtungssituation Schritt für Schritt eingrenzen.")).toBeInTheDocument();
    expect(screen.getByText(/Um welchen Dichtungstyp geht es/)).toBeInTheDocument();
    expect(screen.queryByText("Dichtungstyp-Richtung: Dichtungstyp offen")).not.toBeInTheDocument();
    expect(screen.queryByText("Der Dichtungstyp grenzt Pflichtangaben, Risiken und den Herstellerpruefpfad zuerst ein.")).not.toBeInTheDocument();
  });

  it("does not repeat generic working-state phrases as if they were user facts", () => {
    agentStreamMockState.messages = [
      { role: "user", content: "danke, ich möchte meine dichtungssituation besprechen" },
      {
        role: "assistant",
        content:
          "**Arbeitsstand:** Das ist ein guter erster Stand.\n\n" +
          "**Naechste sinnvolle Frage:** Wo sitzt die Dichtung genau?",
      },
    ];

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("Gern. Dann lass uns die Dichtungssituation Schritt für Schritt eingrenzen.")).toBeInTheDocument();
    expect(screen.getByText(/Worum geht es ungefähr/)).toBeInTheDocument();
    expect(screen.queryByText(/Okay, ich habe Das ist ein guter erster Stand/)).not.toBeInTheDocument();
    expect(screen.queryByText("Wo sitzt die Dichtung genau?")).not.toBeInTheDocument();
  });

  it("does not flash structured working-state drafts while streaming", () => {
    agentStreamMockState.isStreaming = true;
    agentStreamMockState.streamingText =
      "**Arbeitsstand:** Ich habe deine Angaben als aktuellen Arbeitsstand übernommen.\n\n" +
      "**Naechste sinnvolle Frage:** Um welchen Dichtungstyp geht es?";

    render(<ChatPane caseId="case-parameter" />);

    expect(screen.getByText("SeaLAI bereitet die Antwort vor...")).toBeInTheDocument();
    expect(screen.queryByText("Arbeitsstand:")).not.toBeInTheDocument();
    expect(screen.queryByText("Naechste sinnvolle Frage:")).not.toBeInTheDocument();
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
