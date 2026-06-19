import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatResponse, Clarification, ConfirmationResponse, ConversationMemory } from "../contracts";
import { ChatPane } from "./ChatPane";
import { Shell } from "./Shell";

afterEach(cleanup);

const EMPTY: ConversationMemory = { case_state: [], history: [] };
const EMPTY_CONF: ConfirmationResponse = {
  uebernommen: [],
  rueckfragen: [],
  computed: [],
  not_computed: [],
  notes: [],
  clarifications: [],
};
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
    onSubmitParams: vi.fn(async () => EMPTY_CONF),
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

  it("the stage shows the fast-path card (not the '+' popover); 'Berechnen' settles + surfaces the confirmation", async () => {
    const conf: ConfirmationResponse = {
      ...EMPTY_CONF,
      uebernommen: [{ feld: "wellendurchmesser", label: "Wellendurchmesser d₁", wert: "50 mm" }],
    };
    const { props } = renderPane({ onSubmitParams: vi.fn(async () => conf) });
    // an empty stage hides the cockpit; the user opens it explicitly via the affordance
    fireEvent.click(screen.getByTestId("open-cockpit"));
    // the cockpit form IS the compact fast-path card; the "+" popover is absent
    expect(screen.getByTestId("param-compact")).toBeInTheDocument();
    expect(screen.queryByTestId("open-parameter-form")).toBeNull();
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.click(screen.getByTestId("param-submit"));
    // ONE batch call carrying the field + its schema label (not N per-field calls); R2 also passes
    // the reconcile deletes (empty here — nothing was committed yet)
    expect(props.onSubmitParams).toHaveBeenCalledWith(
      [{ feld: "wellendurchmesser", wert: "50 mm", label: "Wellendurchmesser d₁" }],
      [],
    );
    // the deterministic confirmation lands in the conversation (→ chat-view)
    expect(await screen.findByTestId("param-confirmation")).toHaveTextContent("übernommen");
  });

  it("the '+' popover is RETIRED: no second form entry point on the stage or in chat-view", async () => {
    renderPane();
    expect(screen.queryByTestId("open-parameter-form")).toBeNull(); // stage: no "+"
    // the cockpit form (opened via the affordance) is the single entry point — no "+"
    fireEvent.click(screen.getByTestId("open-cockpit"));
    expect(within(screen.getByTestId("case-state")).getByTestId("param-compact")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    await screen.findByTestId("chat-log");
    expect(screen.queryByTestId("open-parameter-form")).toBeNull(); // chat-view: still no "+"
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

  it("a not_computed-only kern shows the calm placeholder, not an empty Berechnungen panel", () => {
    renderPane({
      memory: EMPTY,
      compute: {
        computed: [],
        not_computed: [
          { calc_id: "umfangsgeschwindigkeit", reason: "nicht berechenbar: Eingaben fehlen (rpm)" },
        ],
        notes: [],
      },
    });
    // a not_computed-only kern keeps caseStateEmpty true → the cockpit is hidden until opened;
    // once opened, it shows the calm placeholder rather than an empty Berechnungen panel
    fireEvent.click(screen.getByTestId("open-cockpit"));
    expect(screen.getByTestId("case-state-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("berechnungen-panel")).toBeNull();
  });

  // ── cockpit re-layout: persistent right column, calm stage center ──────────────
  it("stage center is calm: no form / chips / Berechnungen in the center (they live in the cockpit)", () => {
    renderPane({
      memory: WITH_FACTS,
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
    const center = screen.getByTestId("stage-center");
    expect(within(center).queryByTestId("param-compact")).toBeNull();
    expect(within(center).queryByTestId("memory-panel")).toBeNull();
    expect(within(center).queryByTestId("berechnungen-panel")).toBeNull();
  });

  it("the cockpit is present ON THE STAGE and holds all three: form + chips + Berechnungen", () => {
    renderPane({
      memory: WITH_FACTS,
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
    const cockpit = screen.getByTestId("case-state");
    expect(within(cockpit).getByTestId("param-compact")).toBeInTheDocument();
    expect(within(cockpit).getByTestId("memory-panel")).toBeInTheDocument();
    expect(within(cockpit).getByTestId("berechnungen-panel")).toBeInTheDocument();
  });

  it("Berechnen FROM THE COCKPIT settles and transitions to chat-view (data flow unchanged)", async () => {
    const conf: ConfirmationResponse = {
      ...EMPTY_CONF,
      uebernommen: [{ feld: "wellendurchmesser", label: "Wellendurchmesser d₁", wert: "50 mm" }],
    };
    const { props } = renderPane({ onSubmitParams: vi.fn(async () => conf) });
    fireEvent.click(screen.getByTestId("open-cockpit")); // open the cockpit on the empty stage
    const cockpit = screen.getByTestId("case-state");
    fireEvent.change(within(cockpit).getByTestId("param-wellendurchmesser"), { target: { value: "50" } });
    fireEvent.click(within(cockpit).getByTestId("param-submit"));
    expect(props.onSubmitParams).toHaveBeenCalledWith(
      [{ feld: "wellendurchmesser", wert: "50 mm", label: "Wellendurchmesser d₁" }],
      [],
    );
    expect(await screen.findByTestId("param-confirmation")).toHaveTextContent("übernommen");
    expect(screen.getByTestId("chat-log")).toBeInTheDocument(); // transitioned to chat-view
  });

  it("an active case keeps the cockpit persistent across BOTH states (stage and chat-view)", async () => {
    renderPane({ memory: WITH_FACTS }); // a non-empty case auto-shows the cockpit
    expect(screen.getByTestId("case-state")).toBeInTheDocument(); // stage
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    await screen.findByTestId("chat-log");
    expect(screen.getByTestId("case-state")).toBeInTheDocument(); // chat-view — still present
    // NOTE: the ≥1024px vs <1024px stacking is a CSS @media concern — not assertable in jsdom;
    // verified visually in the harness/build, not here.
  });
});

describe("cockpit visibility (claude.ai chat-only ↔ split)", () => {
  it("empty case + cockpit not opened → chat-only, NO right panel, affordance present", () => {
    renderPane({ memory: EMPTY });
    expect(screen.queryByTestId("case-state")).toBeNull(); // cockpit not mounted yet (no panel)
    expect(screen.getByTestId("chat-pane")).toHaveClass("workspace--chat-only");
    expect(screen.getByTestId("open-cockpit")).toBeInTheDocument(); // the subtle affordance
  });

  it("opening the form splits (chat | cockpit) and it persists for the session", async () => {
    renderPane({ memory: EMPTY });
    fireEvent.click(screen.getByTestId("open-cockpit"));
    const cockpit = screen.getByTestId("case-state");
    expect(within(cockpit).getByTestId("param-compact")).toBeInTheDocument();
    expect(screen.getByTestId("chat-pane")).toHaveClass("workspace--split"); // two-column now
    expect(screen.queryByTestId("open-cockpit")).toBeNull(); // affordance gone once open
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    await screen.findByTestId("chat-log");
    expect(screen.getByTestId("case-state")).toBeInTheDocument();
  });

  it("a non-empty case_state auto-opens the cockpit (split)", () => {
    renderPane({ memory: WITH_FACTS });
    expect(screen.getByTestId("case-state")).toBeInTheDocument();
    expect(screen.getByTestId("chat-pane")).toHaveClass("workspace--split");
    expect(screen.queryByTestId("open-cockpit")).toBeNull();
  });

  it("a compute-only result (a clarification, case_state still empty) auto-opens the cockpit", () => {
    const clarification: Clarification = {
      feld: "drehzahl",
      input_name: "drehzahl",
      raw_value: "5000",
      raw_unit: "",
      reason: "unit_missing",
      suggested_unit: "U/min",
      known_dimension: "",
      expected_dimension: "frequency",
      one_click: true,
    };
    renderPane({
      memory: EMPTY,
      compute: { computed: [], not_computed: [], notes: [], clarifications: [clarification] },
    });
    expect(screen.getByTestId("case-state")).toBeInTheDocument();
    expect(screen.getByTestId("chat-pane")).toHaveClass("workspace--split");
  });

  it("the cockpit header closes back to centered chat-only (panel stays MOUNTED, hidden)", () => {
    renderPane({ memory: WITH_FACTS });
    expect(screen.getByTestId("chat-pane")).toHaveClass("workspace--split");
    fireEvent.click(screen.getByTestId("cockpit-close"));
    expect(screen.getByTestId("chat-pane")).toHaveClass("workspace--chat-only");
    expect(screen.getByTestId("case-state")).toBeInTheDocument(); // mounted (CSS-hidden), not unmounted
    expect(screen.getByTestId("open-cockpit")).toBeInTheDocument(); // affordance to reopen
  });

  it("reopening after a close keeps the form values (open/close = CSS only, no remount)", () => {
    renderPane({ memory: EMPTY });
    fireEvent.click(screen.getByTestId("open-cockpit"));
    fireEvent.change(screen.getByTestId("param-wellendurchmesser"), { target: { value: "40" } });
    fireEvent.click(screen.getByTestId("cockpit-close")); // → chat-only
    expect(screen.getByTestId("chat-pane")).toHaveClass("workspace--chat-only");
    fireEvent.click(screen.getByTestId("open-cockpit")); // reopen
    expect((screen.getByTestId("param-wellendurchmesser") as HTMLInputElement).value).toBe("40");
  });
});

describe("chat|cockpit divider (resizable ~50/50 — ≥1024px)", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  // jsdom does not lay out → mock the workspace rect (width 1200, right edge at 1200px)
  const mockRect = (el: HTMLElement) => {
    el.getBoundingClientRect = () =>
      ({ left: 0, right: 1200, top: 0, bottom: 800, width: 1200, height: 800, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect;
  };

  it("renders NO divider in chat-only (no cockpit)", () => {
    renderPane({ memory: EMPTY });
    expect(screen.queryByTestId("cockpit-splitter")).toBeNull();
  });

  it("renders a proper vertical separator when split", () => {
    renderPane({ memory: WITH_FACTS });
    const sp = screen.getByTestId("cockpit-splitter");
    expect(sp).toHaveAttribute("role", "separator");
    expect(sp).toHaveAttribute("aria-orientation", "vertical");
  });

  it("dragging the divider clamps --cockpit-w to [min 360px, max 55%]", () => {
    renderPane({ memory: WITH_FACTS });
    const pane = screen.getByTestId("chat-pane");
    const sp = screen.getByTestId("cockpit-splitter");
    mockRect(pane);
    fireEvent.pointerDown(sp, { pointerId: 1 });
    // pull toward the cockpit (right) → desired 300px < min → clamp 360
    fireEvent.pointerMove(sp, { pointerId: 1, clientX: 900 });
    expect(pane.style.getPropertyValue("--cockpit-w")).toBe("360px");
    // pull toward the chat (left) → desired 900px > 55% (660) → clamp 660
    fireEvent.pointerMove(sp, { pointerId: 1, clientX: 300 });
    expect(pane.style.getPropertyValue("--cockpit-w")).toBe("660px");
    fireEvent.pointerUp(sp, { pointerId: 1 });
  });

  it("persists the chosen width and restores it on a fresh mount", () => {
    const first = renderPane({ memory: WITH_FACTS });
    const pane = screen.getByTestId("chat-pane");
    mockRect(pane);
    const sp = screen.getByTestId("cockpit-splitter");
    fireEvent.pointerDown(sp, { pointerId: 1 });
    fireEvent.pointerMove(sp, { pointerId: 1, clientX: 760 }); // desired 440 (in range)
    fireEvent.pointerUp(sp, { pointerId: 1 });
    expect(localStorage.getItem("sealai-v2:split-w")).toBe("440");
    first.unmount();
    renderPane({ memory: WITH_FACTS });
    expect(screen.getByTestId("chat-pane").style.getPropertyValue("--cockpit-w")).toBe("440px");
  });

  it("double-click resets to the ~50/50 default (clears the inline var + storage)", () => {
    renderPane({ memory: WITH_FACTS });
    const pane = screen.getByTestId("chat-pane");
    mockRect(pane);
    const sp = screen.getByTestId("cockpit-splitter");
    fireEvent.pointerDown(sp, { pointerId: 1 });
    fireEvent.pointerMove(sp, { pointerId: 1, clientX: 760 });
    fireEvent.pointerUp(sp, { pointerId: 1 });
    expect(pane.style.getPropertyValue("--cockpit-w")).toBe("440px");
    fireEvent.doubleClick(sp);
    expect(pane.style.getPropertyValue("--cockpit-w")).toBe(""); // inline override cleared → CSS default ~45/55
    expect(localStorage.getItem("sealai-v2:split-w")).toBeNull();
  });
});

describe("cockpit internals: one column + split (Berechnungen | Kritische Punkte)", () => {
  const withV = (value: number): Partial<Parameters<typeof ChatPane>[0]> => ({
    compute: {
      computed: [
        {
          calc_id: "umfangsgeschwindigkeit",
          name: "v",
          value,
          unit: "m/s",
          formula: "v = π·d·n",
          parent_fields: [],
          input_origins: [],
          provenance: "kernel_computed",
        },
      ],
      not_computed: [],
      notes: [],
    },
  });

  it("stacks the parameter form on top, then the Berechnungen | Kritische Punkte split", () => {
    renderPane({ memory: WITH_FACTS });
    const cockpit = screen.getByTestId("case-state");
    const form = within(cockpit).getByTestId("cockpit-form");
    const split = within(cockpit).getByTestId("cockpit-split");
    expect(within(form).getByTestId("param-compact")).toBeInTheDocument();
    // the form sits ABOVE the split (DOM order)
    expect(form.compareDocumentPosition(split) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const cols = within(split).getAllByTestId(/^cockpit-col-(calc|critical)$/);
    expect(cols.map((c) => c.getAttribute("data-testid"))).toEqual([
      "cockpit-col-calc",
      "cockpit-col-critical",
    ]);
  });

  it("the calc column holds the deterministic Berechnungen; chips + Briefing sit below the split", () => {
    renderPane({ memory: WITH_FACTS, ...withV(13.09) });
    const cockpit = screen.getByTestId("case-state");
    const berechnungen = within(screen.getByTestId("cockpit-col-calc")).getByTestId("berechnungen-panel");
    expect(berechnungen).toHaveTextContent("13,09 m/s");
    const split = within(cockpit).getByTestId("cockpit-split");
    const chips = within(cockpit).getByTestId("memory-panel");
    const briefing = within(cockpit).getByTestId("make-briefing");
    // the split sits ABOVE the chips, which sit above the Briefing block (DOM order)
    expect(split.compareDocumentPosition(chips) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(chips.compareDocumentPosition(briefing) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("the cockpit body is a single scroll-area holding the whole column", () => {
    renderPane({ memory: WITH_FACTS });
    const body = screen.getByTestId("case-state").querySelector(".cockpit-body");
    expect(body).not.toBeNull();
    expect(body).toHaveClass("scroll-area");
    expect(body).toHaveClass("cockpit-body--stack");
  });
});

describe("scroll model (locked shell · one scroll region per surface · fade cues)", () => {
  it("the chat log is a scroll-area inside a fade-cue wrapper; the composer stays outside it", async () => {
    renderPane({ memory: WITH_FACTS });
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    const log = await screen.findByTestId("chat-log");
    expect(log).toHaveClass("scroll-area");
    const wrap = log.closest(".scroll-wrap");
    expect(wrap).not.toBeNull();
    // the docked composer is a sibling of the scroll region, never inside it
    expect(wrap?.querySelector('[data-testid="composer-input"]')).toBeNull();
    expect(screen.getByTestId("composer-input")).toBeInTheDocument();
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
      onSubmitParams: vi.fn(async () => EMPTY_CONF),
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

  it("the sidebar collapses/expands and persists the choice", () => {
    localStorage.clear();
    const { container, unmount } = render(
      <Shell onLogout={() => {}} onNewQuestion={() => {}}>
        <div />
      </Shell>,
    );
    const toggle = screen.getByTestId("rail-toggle");
    // default collapsed (icon rail)
    expect(container.querySelector(".shell")).not.toHaveClass("shell--nav-expanded");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // expand → wider with labels, persisted
    fireEvent.click(toggle);
    expect(container.querySelector(".shell")).toHaveClass("shell--nav-expanded");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(localStorage.getItem("sealai-v2:nav-expanded")).toBe("1");
    unmount();
    // the choice is restored on a fresh mount
    const { container: c2 } = render(
      <Shell onLogout={() => {}} onNewQuestion={() => {}}>
        <div />
      </Shell>,
    );
    expect(c2.querySelector(".shell")).toHaveClass("shell--nav-expanded");
    localStorage.clear();
  });
});
