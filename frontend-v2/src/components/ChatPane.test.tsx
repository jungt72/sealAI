import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
      [
        { feld: "dichtungstyp", wert: "rwdr", label: "Dichtungstyp" }, // active type marker (gates the kern)
        { feld: "wellendurchmesser", wert: "50 mm", label: "Wellendurchmesser d₁" },
      ],
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
      [
        { feld: "dichtungstyp", wert: "rwdr", label: "Dichtungstyp" }, // active type marker (gates the kern)
        { feld: "wellendurchmesser", wert: "50 mm", label: "Wellendurchmesser d₁" },
      ],
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
    expect(screen.getByTestId("open-cockpit")).toBeInTheDocument(); // the parameter-entry CTA
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

describe("cockpit internals: parameter/readout matrix", () => {
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

  it("places the parameter form in the left column and the readout in the right column", () => {
    renderPane({ memory: WITH_FACTS });
    const cockpit = screen.getByTestId("case-state");
    const paramCol = within(cockpit).getByTestId("cockpit-param-column");
    const readoutCol = within(cockpit).getByTestId("cockpit-readout-column");
    const form = within(paramCol).getByTestId("cockpit-form");
    expect(within(form).getByTestId("param-compact")).toBeInTheDocument();
    expect(within(readoutCol).getByTestId("cockpit-calculation-readout")).toBeInTheDocument();
    expect(within(readoutCol).getByTestId("cockpit-medium-readout")).toBeInTheDocument();
    // DOM order mirrors the visual matrix: parameter column first, readout column second.
    expect(paramCol.compareDocumentPosition(readoutCol) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("the readout column holds Berechnungen first and Medium below; chips stay with parameters", () => {
    renderPane({ memory: WITH_FACTS, ...withV(13.09) });
    const cockpit = screen.getByTestId("case-state");
    const paramCol = within(cockpit).getByTestId("cockpit-param-column");
    const calc = within(cockpit).getByTestId("cockpit-calculation-readout");
    const medium = within(cockpit).getByTestId("cockpit-medium-readout");
    const berechnungen = within(calc).getByTestId("berechnungen-panel");
    expect(berechnungen).toHaveTextContent("13,09 m/s");
    expect(within(medium).getByText("Hydrauliköl")).toBeInTheDocument();
    expect(within(paramCol).getByTestId("memory-panel")).toBeInTheDocument();
    expect(calc.compareDocumentPosition(medium) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("projects the right rail as orientation, not a critical list of missing internal keys", () => {
    renderPane({
      memory: WITH_FACTS,
      compute: {
        computed: [],
        not_computed: [
          { calc_id: "umfangsgeschwindigkeit", reason: "nicht berechenbar: Eingaben fehlen (d1_mm, rpm)" },
        ],
        notes: [],
      },
    });
    const cockpit = screen.getByTestId("case-state");
    const rail = within(cockpit).getByTestId("cockpit-readout-column");
    expect(within(rail).getByTestId("cockpit-solution")).toHaveTextContent("RWDR plausibel");
    expect(within(rail).getByTestId("cockpit-next-step")).toHaveTextContent("Drehzahl ergänzen");
    expect(within(rail).getByTestId("cockpit-missing")).toHaveTextContent("Drehzahl n");
    expect(within(rail).getByTestId("cockpit-warning")).toHaveTextContent("Keine kritischen Punkte");
    expect(rail).not.toHaveTextContent("d1_mm");
    expect(rail).not.toHaveTextContent("rpm");
  });

  it("the cockpit body is a single scroll-area holding the two-column matrix", () => {
    renderPane({ memory: WITH_FACTS });
    const body = screen.getByTestId("case-state").querySelector(".cockpit-body");
    expect(body).not.toBeNull();
    expect(body).toHaveClass("scroll-area");
    expect(body).toHaveClass("cockpit-body--matrix");
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

  it("proxies wheel events from the broader chat column into the chat log", async () => {
    renderPane();
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    const log = await screen.findByTestId("chat-log");
    const col = log.closest(".chat-col");
    expect(col).not.toBeNull();

    Object.defineProperty(log, "clientHeight", { configurable: true, value: 400 });
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 1200 });
    log.scrollTop = 0;

    fireEvent.wheel(col as Element, { deltaY: 160 });

    expect(log.scrollTop).toBe(160);
  });

  it("proxies wheel events from the workspace background into the chat log", async () => {
    renderPane();
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    const log = await screen.findByTestId("chat-log");
    const pane = screen.getByTestId("chat-pane");

    Object.defineProperty(log, "clientHeight", { configurable: true, value: 400 });
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 1200 });
    log.scrollTop = 0;

    fireEvent.wheel(pane, { deltaY: 220 });

    expect(log.scrollTop).toBe(220);
  });

  it("normalizes line-mode mouse wheels to native-like scroll distance", async () => {
    renderPane();
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    const log = await screen.findByTestId("chat-log");
    const pane = screen.getByTestId("chat-pane");

    Object.defineProperty(log, "clientHeight", { configurable: true, value: 400 });
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 1200 });
    log.scrollTop = 0;

    fireEvent.wheel(pane, { deltaY: 3, deltaMode: WheelEvent.DOM_DELTA_LINE });

    expect(log.scrollTop).toBe(120);
  });

  it("settles the temporary spacer without jumping the viewport down after a short answer", async () => {
    let resolveSend: (value: ChatResponse) => void = () => {};
    renderPane({
      onSend: vi.fn(
        () =>
          new Promise<ChatResponse>((resolve) => {
            resolveSend = resolve;
          }),
      ),
    });
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    const log = await screen.findByTestId("chat-log");
    const spacer = log.querySelector(".chat-log-spacer") as HTMLElement;
    Object.defineProperty(log, "clientHeight", { configurable: true, value: 900 });
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 1600 });
    Object.defineProperty(spacer, "offsetHeight", { configurable: true, value: 900 });
    log.scrollTop = 500;
    spacer.style.minHeight = "600px";

    resolveSend({
      answer: "fertig",
      model: "m",
      grounded: true,
      intent: null,
      citations: [],
    });

    await screen.findByText("fertig");
    await waitFor(() => expect(log.scrollTop).toBe(500));
    expect(spacer.style.minHeight).toBe("700px");
  });

  it("does not steal wheel events from a nested scrollable answer surface", async () => {
    renderPane();
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage?" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    const log = await screen.findByTestId("chat-log");
    const pane = screen.getByTestId("chat-pane");
    const nested = document.createElement("div");
    nested.style.overflowY = "auto";
    pane.appendChild(nested);

    Object.defineProperty(log, "clientHeight", { configurable: true, value: 400 });
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 1200 });
    Object.defineProperty(nested, "clientHeight", { configurable: true, value: 100 });
    Object.defineProperty(nested, "scrollHeight", { configurable: true, value: 500 });
    nested.scrollTop = 10;
    log.scrollTop = 0;

    fireEvent.wheel(nested, { deltaY: 80 });

    expect(log.scrollTop).toBe(0);
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

describe("'Fälle'-Sidebar: hydration from memory.history", () => {
  it("hydrates the message log from history on first render", () => {
    renderPane({
      memory: {
        case_state: [],
        history: [
          { role: "user", text: "EPDM in Hydrauliköl?" },
          { role: "assistant", text: "EPDM quillt in unpolaren Medien." },
        ],
      },
    });
    expect(screen.getByText("EPDM in Hydrauliköl?")).toBeInTheDocument();
    const hydrated = screen.getByTestId("answer-history");
    expect(hydrated).toHaveTextContent("EPDM quillt in unpolaren Medien.");
  });

  it("renders a hydrated turn without citation/verification chrome (never persisted)", () => {
    renderPane({
      memory: { case_state: [], history: [{ role: "assistant", text: "Antwort." }] },
    });
    expect(screen.getByTestId("answer-history")).toBeInTheDocument();
    expect(screen.queryByTestId("answer")).toBeNull();
  });

  it("does NOT hydrate when history is empty (fresh/new case stays the clean stage)", () => {
    renderPane({ memory: EMPTY });
    expect(screen.queryByTestId("chat-log")).toBeNull();
    expect(screen.queryByTestId("answer-history")).toBeNull();
  });

  it("a live send is never clobbered by a later memory refetch (the length===0 guard)", async () => {
    const onSend = vi.fn(async (): Promise<ChatResponse> => ({
      answer: "live antwort",
      model: "m",
      grounded: true,
      intent: null,
      citations: [],
    }));
    const { rerender, props } = renderPane({ onSend, memory: EMPTY });
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Frage" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    await waitFor(() => expect(screen.getByTestId("answer")).toBeInTheDocument());
    // a memory refetch now resolves with (stale-looking) history — msgs already has content, so
    // the hydration effect's `prev.length === 0` guard must leave the live answer untouched.
    rerender(
      <ChatPane
        {...props}
        memory={{
          case_state: [],
          history: [
            { role: "user", text: "Frage" },
            { role: "assistant", text: "live antwort" },
          ],
        }}
      />,
    );
    expect(screen.getByTestId("answer")).toBeInTheDocument(); // still the rich live variant
    expect(screen.queryByTestId("answer-history")).toBeNull(); // never downgraded
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

describe("Phase 3A live token streaming (smalltalk-only)", () => {
  it("appends token deltas to an in-flight buffer, then REPLACES it with the final answer", async () => {
    let resolveSend: (r: ChatResponse) => void = () => undefined;
    const onSend = vi.fn((_msg: string, onToken?: (t: string) => void) => {
      onToken?.("Hal");
      onToken?.("lo, Welt!");
      return new Promise<ChatResponse>((res) => {
        resolveSend = res;
      });
    });
    renderPane({ onSend });
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Hallo" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    // interim: the streamed buffer is visible (raw deltas concatenated)
    await waitFor(() =>
      expect(screen.getByTestId("answer-streaming")).toHaveTextContent("Hallo, Welt!"),
    );
    // terminal result REPLACES the buffer with the authoritative answer (never appended)
    await act(async () => {
      resolveSend({ answer: "FINALE ANTWORT", model: "m", grounded: true, intent: null, citations: [] });
    });
    await waitFor(() => expect(screen.queryByTestId("answer-streaming")).toBeNull());
    expect(screen.getByText("FINALE ANTWORT")).toBeInTheDocument();
    expect(screen.queryAllByTestId("answer-streaming")).toHaveLength(0); // buffer replaced, not left
  });

  it("a turn that streams NO token behaves exactly as before (atomic assistant append)", async () => {
    const onSend = vi.fn(
      async (): Promise<ChatResponse> => ({
        answer: "ATOMARE ANTWORT",
        model: "m",
        grounded: true,
        intent: null,
        citations: [],
      }),
    );
    renderPane({ onSend });
    fireEvent.change(screen.getByTestId("composer-input"), { target: { value: "Hallo" } });
    fireEvent.click(screen.getByTestId("composer-send"));
    await screen.findByText("ATOMARE ANTWORT");
    expect(screen.queryByTestId("answer-streaming")).toBeNull(); // no streaming element ever
  });
});
