import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Briefing, ChatResponse, ConversationMemory } from "../contracts";
import { Answer } from "./Answer";
import { BriefingPane } from "./BriefingPane";
import { Citation } from "./Citation";
import { MemoryPanel } from "./MemoryPanel";
import { SafetyBanner } from "./SafetyBanner";

afterEach(cleanup);

describe("safety-framing (check 3: locked + ubiquitous)", () => {
  it("the claim-boundary (Orientierung≠Freigabe) renders persistently", () => {
    render(<SafetyBanner />);
    expect(screen.getByTestId("claim-boundary")).toHaveTextContent(/Orientierung, keine Freigabe/i);
    expect(screen.getByTestId("claim-boundary")).toHaveTextContent(/Hersteller/i);
  });

  it("an answer carries the candidate label, and 'vorläufig' iff NOT grounded", () => {
    const ungrounded: ChatResponse = { answer: "EPDM …", model: "m", grounded: false, intent: null, citations: [] };
    render(<Answer res={ungrounded} />);
    expect(screen.getByTestId("candidate-label")).toHaveTextContent(/Kandidat, nicht final/);
    expect(screen.getByTestId("vorlaeufig-label")).toHaveTextContent(/vorläufig/);

    cleanup();
    const grounded: ChatResponse = { ...ungrounded, grounded: true };
    render(<Answer res={grounded} />);
    expect(screen.getByTestId("candidate-label")).toBeInTheDocument();
    expect(screen.queryByTestId("vorlaeufig-label")).toBeNull(); // grounded → no 'vorläufig'
  });

  it("citations show the PRIMARY source, never the internal card_id", () => {
    render(<Citation cite={{ text: "Statische Verpressung ~15–25 %", sources: ["Parker O-Ring Handbook", "ISO 3601-2"] }} />);
    expect(screen.getByTestId("citation-source")).toHaveTextContent("Parker O-Ring Handbook");
    expect(screen.getByTestId("citation-source")).toHaveTextContent("ISO 3601-2");
    expect(screen.getByTestId("citation").textContent ?? "").not.toMatch(/FK-[A-Z]/); // no card_id leak
  });

  it("remembered facts are framed UNVERIFIED ('zuvor genannt — bei Bedarf bestätigen')", () => {
    const mem: ConversationMemory = {
      case_state: [{ feld: "medium", wert: "Hydrauliköl", provenance: "distilled-from-conversation" }],
      history: [],
    };
    render(<MemoryPanel memory={mem} onEdit={() => {}} onForget={() => {}} onForgetAll={() => {}} />);
    const fact = screen.getByTestId("remembered-fact");
    expect(within(fact).getByTestId("remembered-hint")).toHaveTextContent(/zuvor genannt — bei Bedarf bestätigen/);
  });

  it("UBIQUITY: the briefing surface carries the SAME claim-boundary as the chat surface", () => {
    const briefing: Briefing = { kind: "briefing", title: "RWDR", body: "…", provenance: ["Parker O-Ring Handbook"] };
    render(<BriefingPane briefing={briefing} />);
    // the briefing (a domain-content surface) renders the claim-boundary, not only the chat view
    expect(screen.getByTestId("claim-boundary")).toHaveTextContent(/Orientierung, keine Freigabe/i);
    expect(screen.getByTestId("briefing-provenance")).toHaveTextContent("Parker O-Ring Handbook");
  });
});
