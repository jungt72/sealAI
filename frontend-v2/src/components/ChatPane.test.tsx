import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatResponse, ConversationMemory } from "../contracts";
import { ChatPane } from "./ChatPane";
import { Shell } from "./Shell";

afterEach(cleanup);

const EMPTY: ConversationMemory = { case_state: [], history: [] };
const WITH_FACTS: ConversationMemory = {
  case_state: [
    { feld: "wellendurchmesser", wert: "50 mm", provenance: "user-form" },
    { feld: "medium", wert: "Hydrauliköl", provenance: "distilled-from-conversation" },
  ],
  history: [],
};

function renderPane(over: Partial<Parameters<typeof ChatPane>[0]> = {}) {
  const props: Parameters<typeof ChatPane>[0] = {
    onSend: vi.fn(async (): Promise<ChatResponse> => ({
      answer: "ok",
      model: "m",
      grounded: true,
      intent: null,
      citations: [],
    })),
    error: null,
    memory: EMPTY,
    onEditFact: vi.fn(),
    onForgetFact: vi.fn(),
    onForgetAll: vi.fn(),
    onSubmitParam: vi.fn(),
    onMakeBriefing: vi.fn(),
    canBriefing: false,
    briefing: null,
    ...over,
  };
  return { ...render(<ChatPane {...props} />), props };
}

describe("pilot-ui stage (fresh conversation)", () => {
  it("renders the centered greeting without a name by default (name wiring = Part 2)", () => {
    renderPane();
    expect(screen.getByTestId("greeting")).toHaveTextContent("Welche Dichtungsfrage steht an?");
  });

  it("renders the greeting with the given name when provided", () => {
    renderPane({ greetingName: "Thorsten" });
    expect(screen.getByTestId("greeting")).toHaveTextContent("Welche Dichtungsfrage steht an, Thorsten?");
  });

  it("fresh login shows the clean stage: NO fact chips when no facts exist", () => {
    renderPane({ memory: EMPTY });
    expect(screen.queryByTestId("memory-panel")).toBeNull();
    expect(screen.queryByTestId("remembered-fact")).toBeNull();
  });

  it("renders mono fact chips under the pill when facts exist, with forget-all", () => {
    renderPane({ memory: WITH_FACTS });
    expect(screen.getAllByTestId("remembered-fact")).toHaveLength(2);
    expect(screen.getByTestId("forget-all")).toHaveTextContent("alles vergessen");
  });

  it("the '+' button opens the parameter form as a popover; submit closes it and writes via onSubmitParam", () => {
    const { props } = renderPane();
    expect(screen.queryByTestId("parameter-form")).toBeNull();
    fireEvent.click(screen.getByTestId("open-parameter-form"));
    expect(screen.getByTestId("parameter-form")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    expect(props.onSubmitParam).toHaveBeenCalledWith("wellendurchmesser", "50 mm");
    expect(screen.queryByTestId("parameter-form")).toBeNull(); // popover closed after submit
  });

  it("chip interactions are preserved: chip body = edit, × = forget", () => {
    const { props } = renderPane({ memory: WITH_FACTS });
    fireEvent.click(screen.getAllByTestId("edit-fact")[0]);
    expect(props.onEditFact).toHaveBeenCalledWith("wellendurchmesser", "50 mm");
    fireEvent.click(screen.getAllByTestId("forget-fact")[1]);
    expect(props.onForgetFact).toHaveBeenCalledWith("medium");
  });

  it("renders the Berechnungen panel (kernel channel) next to the chips when compute has a value", () => {
    renderPane({
      compute: {
        computed: [
          {
            calc_id: "umfangsgeschwindigkeit",
            name: "v_m_s",
            value: 16.7552,
            unit: "m/s",
            formula: "v = π·d1·n/60000",
            parent_fields: ["wellendurchmesser", "drehzahl"],
            input_origins: [],
            provenance: "kernel_computed",
          },
        ],
        not_computed: [],
        notes: [],
      },
    });
    expect(screen.getByTestId("berechnungen-panel")).toBeInTheDocument();
    expect(screen.getByTestId("kernel-value")).toHaveTextContent("16,76 m/s");
  });

  it("no Berechnungen panel on the clean stage (no compute)", () => {
    renderPane();
    expect(screen.queryByTestId("berechnungen-panel")).toBeNull();
  });
});

describe("P4b: live stage indicator (SSE progress — labels owned by the frontend)", () => {
  function sendPending(over: Partial<Parameters<typeof ChatPane>[0]> = {}) {
    const result = renderPane({
      onSend: () => new Promise<ChatResponse>(() => {}), // turn stays in flight
      ...over,
    });
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    return result;
  }

  function paneProps(over: Partial<Parameters<typeof ChatPane>[0]>): Parameters<typeof ChatPane>[0] {
    return {
      onSend: () => new Promise<ChatResponse>(() => {}),
      error: null,
      memory: EMPTY,
      onEditFact: vi.fn(),
      onForgetFact: vi.fn(),
      onForgetAll: vi.fn(),
      onSubmitParam: vi.fn(),
      onMakeBriefing: vi.fn(),
      canBriefing: false,
      briefing: null,
      ...over,
    };
  }

  it("no indicator before a turn is in flight", () => {
    renderPane({ liveStage: "generate" });
    expect(screen.queryByTestId("stage-indicator")).toBeNull();
  });

  it("shows the pending row while busy and maps stage keys to German labels", () => {
    const { rerender } = sendPending();
    expect(screen.getByTestId("stage-indicator")).toBeInTheDocument();
    rerender(<ChatPane {...paneProps({ liveStage: "ground" })} />);
    expect(screen.getByTestId("stage-label")).toHaveTextContent("Fakten suchen");
    rerender(<ChatPane {...paneProps({ liveStage: "generate" })} />);
    expect(screen.getByTestId("stage-label")).toHaveTextContent("Antwort formulieren");
    rerender(<ChatPane {...paneProps({ liveStage: "verify" })} />);
    expect(screen.getByTestId("stage-label")).toHaveTextContent("Prüfen");
  });

  it("keeps the last mapped label on unmapped keys (recall/cite/unknown — forward-compatible)", () => {
    const { rerender } = sendPending({ liveStage: "recall" });
    expect(screen.getByTestId("stage-indicator")).toBeInTheDocument();
    expect(screen.queryByTestId("stage-label")).toBeNull(); // nothing mapped yet — dots only
    rerender(<ChatPane {...paneProps({ liveStage: "verify" })} />);
    expect(screen.getByTestId("stage-label")).toHaveTextContent("Prüfen");
    rerender(<ChatPane {...paneProps({ liveStage: "cite" })} />);
    expect(screen.getByTestId("stage-label")).toHaveTextContent("Prüfen"); // retained, not cleared
  });
});

describe("pilot-ui shell (rail + doctrine line)", () => {
  it("the doctrine line stays persistently mounted in the shell", () => {
    render(
      <Shell onLogout={() => {}} onNewQuestion={() => {}}>
        <div />
      </Shell>,
    );
    expect(screen.getByTestId("claim-boundary")).toHaveTextContent(/Orientierung, keine Freigabe/i);
    expect(screen.getByTestId("claim-boundary")).toHaveTextContent(/Hersteller/i);
  });

  it("logout stays reachable via the avatar menu", () => {
    const onLogout = vi.fn();
    render(
      <Shell onLogout={onLogout} onNewQuestion={() => {}}>
        <div />
      </Shell>,
    );
    expect(screen.queryByTestId("logout")).toBeNull(); // menu closed
    fireEvent.click(screen.getByTestId("account-avatar"));
    fireEvent.click(screen.getByTestId("logout"));
    expect(onLogout).toHaveBeenCalled();
  });

  it("the rail's new-question action fires", () => {
    const onNew = vi.fn();
    render(
      <Shell onLogout={() => {}} onNewQuestion={onNew}>
        <div />
      </Shell>,
    );
    fireEvent.click(screen.getByTestId("rail-new-question"));
    expect(onNew).toHaveBeenCalled();
  });
});
