import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type {
  AnfrageResponse,
  Briefing,
  ChatResponse,
  ComputeResponse,
  ConfirmationResponse,
  ContributePayload,
  ConversationMemory,
  ParamItem,
  Turn,
} from "../contracts";
import { clarifyMessage } from "../lib/clarify";
import { clampCockpitPx, clearCockpitPx, loadCockpitPx, saveCockpitPx } from "../lib/cockpitWidth";
import { pinNewTurn, settleNewTurnSpacer, useChatScroll } from "../lib/chatScroll";
import { Answer } from "./Answer";
import { BerechnungenPanel } from "./BerechnungenPanel";
import { BriefingPane } from "./BriefingPane";
import { AlternativenPanel } from "./AlternativenPanel";
import { ContributePanel } from "./ContributePanel";
import { KandidatenSpecPanel } from "./KandidatenSpecPanel";
import { Markdown } from "./Markdown";
import { MediumPanel } from "./MediumPanel";
import { MemoryPanel } from "./MemoryPanel";
import { ParamConfirmation } from "./ParamConfirmation";
import { ParameterForm } from "./ParameterForm";
import { ArrowDownIcon, PaperclipIcon, SendIcon } from "./icons";

type Msg =
  | { role: "user"; text: string }
  | { role: "assistant"; res: ChatResponse }
  // Phase 3A live token streaming (smalltalk-only): an in-flight assistant turn whose text buffer is
  // appended token-by-token as `token` frames arrive. On the terminal `result` it is REPLACED (never
  // appended) by the authoritative { role:"assistant", res } — the gated answer is the single source
  // of truth. Only ever created when a token actually arrives; a turn that streams no token is
  // byte-identical to before (a single atomic { role:"assistant", res } append in send()).
  | { role: "assistant-streaming"; text: string }
  // a HYDRATED historical turn ("Fälle"-Sidebar: loaded from memory.history on open/switch) — text
  // only, deliberately distinct from the live "assistant" variant above: citations/verification/
  // badges were never persisted for past turns, so rendering them as a plain answer would be
  // dishonest (looking identical to "checked, nothing found" rather than "not available").
  | { role: "assistant-history"; text: string }
  | { role: "confirmation"; conf: ConfirmationResponse };

/** memory.history → the hydrated Msg prefix for a freshly opened/switched case. */
function historyToMsgs(history: Turn[]): Msg[] {
  return history.map((t) =>
    t.role === "user" ? { role: "user", text: t.text } : { role: "assistant-history", text: t.text },
  );
}

function wheelDeltaYPx(e: WheelEvent, pageHeight: number): number {
  if (e.deltaMode === WheelEvent.DOM_DELTA_LINE) return e.deltaY * 40;
  if (e.deltaMode === WheelEvent.DOM_DELTA_PAGE) return e.deltaY * pageHeight;
  return e.deltaY;
}

function canScrollVertically(el: HTMLElement, deltaY: number): boolean {
  const style = window.getComputedStyle(el);
  if (!/(auto|scroll|overlay)/.test(style.overflowY)) return false;
  if (el.scrollHeight <= el.clientHeight) return false;
  if (deltaY > 0) return el.scrollTop + el.clientHeight < el.scrollHeight;
  if (deltaY < 0) return el.scrollTop > 0;
  return false;
}

const FACT_LABELS: Record<string, string> = {
  dichtungstyp: "Dichtungstyp",
  medium: "Medium",
  medium_kategorie: "Kategorie",
  druck: "Druck normal",
  druck_max: "Maximaldruck",
  betriebstemperatur: "Betriebstemperatur",
  spitzentemperatur: "Spitzentemperatur",
  wellendurchmesser: "Wellendurchmesser d1",
  drehzahl: "Drehzahl n",
  d1_mm: "Wellendurchmesser d1",
  rpm: "Drehzahl n",
  p_bar: "Druck normal",
  v_m_s: "Umfangsgeschwindigkeit",
  schnurstaerke_mm: "Schnurstärke",
  nuttiefe_mm: "Nuttiefe",
};

const SEAL_LABELS: Record<string, string> = {
  rwdr: "RWDR",
  hydraulik: "Hydraulikdichtung",
  statisch: "Statische Dichtung",
};

const FIELD_PRIORITY = [
  {
    key: "medium",
    label: "Medium",
    action: "Medium ergänzen",
    hint: "für Werkstoff- und Verträglichkeitsbewertung",
  },
  {
    key: "wellendurchmesser",
    label: "Wellendurchmesser d1",
    action: "Wellendurchmesser d1 ergänzen",
    hint: "für Umfangsgeschwindigkeit",
  },
  {
    key: "drehzahl",
    label: "Drehzahl n",
    action: "Drehzahl ergänzen",
    hint: "für Umfangsgeschwindigkeit",
  },
  {
    key: "druck",
    label: "Druck normal",
    action: "Betriebsdruck ergänzen",
    hint: "für PV-Bewertung",
  },
  {
    key: "druck_max",
    label: "Maximaldruck",
    action: "Maximaldruck ergänzen",
    hint: "für Betriebsgrenzen und RFQ-Reife",
  },
  {
    key: "betriebstemperatur",
    label: "Betriebstemperatur",
    action: "Temperatur ergänzen",
    hint: "für Werkstoffauswahl",
  },
] as const;

function labelKey(raw: string): string {
  const key = raw.trim();
  return FACT_LABELS[key] ?? key;
}

function humanizeComputeReason(reason: string): string {
  return reason.replace(/\(([^)]*)\)/g, (_match, inner: string) => {
    const labels = String(inner)
      .split(",")
      .map((part) => labelKey(part))
      .join(", ");
    return `(${labels})`;
  });
}

function factValue(committed: Record<string, string>, key: string): string {
  return (committed[key] ?? "").trim();
}

function activeSealType(committed: Record<string, string>): string {
  return factValue(committed, "dichtungstyp").toLowerCase() || "rwdr";
}

function solutionSummary(committed: Record<string, string>, computedCount: number): { title: string; meta: string } {
  const type = activeSealType(committed);
  const label = SEAL_LABELS[type] ?? "Dichtungssituation";
  if (factValue(committed, "dichtungstyp") || factValue(committed, "medium") || computedCount > 0) {
    return { title: `${label} plausibel`, meta: "vorläufig · wird mit den aktuellen Angaben plausibilisiert" };
  }
  return { title: "Dichtungssituation offen", meta: "vorläufig · Startpunkt oder Fallbeschreibung fehlt noch" };
}

function missingRows(committed: Record<string, string>) {
  return FIELD_PRIORITY.filter((f) => !factValue(committed, f.key));
}

function warningRows(compute: ComputeResponse | null): string[] {
  const clarificationRows = (compute?.clarifications ?? []).map(clarifyMessage);
  const noteRows = (compute?.notes ?? []).filter(
    (note) => note && !/nicht berechenbar|Eingaben fehlen/i.test(note),
  );
  return [...clarificationRows, ...noteRows].map(humanizeComputeReason);
}

/* P4b — the frontend owns the German stage labels; the backend streams keys only. Unmapped keys
 * (recall, cite, future stages) keep the last mapped label — forward-compatible by ignoring. */
const STAGE_LABELS: Record<string, string> = {
  understand: "Verstehen",
  ground: "Fakten suchen",
  compute: "Berechnen",
  generate: "Antwort formulieren",
  verify: "Prüfen",
};

/** The pilot-ui main surface: a persistent two-column workspace — the conversation on the left, a
 *  persistent cockpit (parameter fast-path form + Fallkontext chips + Berechnungen) on the right,
 *  present from the landing. Two states of ONE conversation:
 *  - stage (no messages yet): a calm, centered greeting + composer over the radial glow;
 *  - chat view (conversation started): the message log with the same composer docked at the bottom.
 *  The cockpit is IDENTICAL in both states. On a failed send the assistant message is NOT appended
 *  (no stale/wrong content); the error is surfaced and the persistent doctrine line (Shell) stays. */
export function ChatPane({
  onSend,
  error,
  memory,
  onEditFact,
  onForgetFact,
  onForgetAll,
  onSubmitParams,
  onPreview,
  onMakeBriefing,
  canBriefing,
  briefing,
  greetingName,
  liveStage,
  compute,
  onConfirmUnit,
  onAnfrage,
  onDownloadPdf,
  onContribute,
}: {
  onSend: (message: string, onToken?: (text: string) => void) => Promise<ChatResponse>;
  error: string | null;
  memory: ConversationMemory;
  onEditFact: (feld: string, wert: string) => void;
  onForgetFact: (feld: string) => void;
  onForgetAll: () => void;
  /** R2 adopt: the non-empty form items + the reconcile `deletes` (managed felder cleared since the
   * last commit) → the host forgets the deletes, then settles the batch (POST /facts). */
  onSubmitParams: (items: ParamItem[], deletes?: string[]) => Promise<ConfirmationResponse>;
  /** R2 live preview: the read-only backend kern over the form DRAFT (null on error/empty). */
  onPreview?: (items: ParamItem[]) => Promise<ComputeResponse | null>;
  onMakeBriefing: () => void;
  canBriefing: boolean;
  briefing: Briefing | null;
  greetingName?: string | null;
  liveStage?: string | null;
  compute?: ComputeResponse | null;
  onConfirmUnit?: (feld: string, value: string) => void;
  /** Modus F lead-gen: route a structured RFQ briefing to the chosen partner. The host supplies the
   * session message; the panel passes only the partner id. */
  onAnfrage?: (partnerId: string, message: string) => Promise<AnfrageResponse>;
  /** Download the Anfrage briefing as a PDF (no send). The host fetches the briefing for the session
   * message + builds the PDF; the panel passes nothing. */
  onDownloadPdf?: (message: string) => Promise<void>;
  /** Wissens-Beitrag: the user shares their solution + outcome to improve sealingAI (untrusted DRAFT). */
  onContribute?: (payload: ContributePayload) => Promise<{ hinweis: string }>;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  // "Fälle"-Sidebar: hydrate from the case's persisted history exactly ONCE per mount (App remounts
  // ChatPane — new `key` — on every case switch/"Neue Frage", so this naturally re-runs per case).
  // The `prev.length === 0` guard, checked inside the updater (never stale), means a later memory
  // refetch mid-conversation (after a live send) can never clobber the richer live "assistant"
  // entries with the flattened historical ones.
  useEffect(() => {
    if (memory.history.length === 0) return;
    setMsgs((prev) => (prev.length === 0 ? historyToMsgs(memory.history) : prev));
  }, [memory.history]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  // claude.ai chat↔artifact: the cockpit opens on the right (a case becomes active, or the user opens
  // the form) and closes back to centered chat-only. `userOpened`/`userClosed` capture explicit intent
  // over the auto-open; `everOpened` keeps the panel MOUNTED once shown (open/close is CSS-visibility
  // only — the form keeps its values, no remount).
  const [userOpened, setUserOpened] = useState(false);
  const [userClosed, setUserClosed] = useState(false);
  const [everOpened, setEverOpened] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { ref: logRef, onScroll, showJumpButton, scrollToBottom } = useChatScroll<HTMLDivElement>(
    msgs.length,
  );
  // No auto-follow (see chatScroll.ts). The ONE programmatic scroll: right after the user submits,
  // their new message is pinned ~1/3 down the log (ChatGPT/Claude/Gemini pattern) — the answer fills
  // in below it without moving anything further; the user reads/scrolls at their own pace from there
  // on (the jump button covers the rest). `spacerRef` is the trailing element `pinNewTurn` grows so
  // that position is reachable even before the (short, not-yet-arrived) answer exists.
  const [scrollToTopIndex, setScrollToTopIndex] = useState<number | null>(null);
  const scrollTargetRef = useRef<HTMLDivElement | null>(null);
  const spacerRef = useRef<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    if (scrollToTopIndex === null) return;
    pinNewTurn(logRef.current, scrollTargetRef.current, spacerRef.current);
    setScrollToTopIndex(null);
  }, [scrollToTopIndex]);
  useLayoutEffect(() => {
    if (busy) return;
    settleNewTurnSpacer(logRef.current, spacerRef.current);
  }, [busy, msgs.length]);
  // resizable chat|cockpit divider (split, ≥1024px): the chosen width drives the `--cockpit-w` track;
  // null = CSS default (~50/50). Persisted in localStorage, restored on mount, reset on double-click.
  const workspaceRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const dragPxRef = useRef<number | null>(null);
  const [cockpitW, setCockpitW] = useState<string | null>(() => {
    const px = loadCockpitPx();
    return px != null ? `${px}px` : null;
  });
  // latest mapped label survives unmapped keys (recall/cite) and clears when the turn ends
  const [stageLabel, setStageLabel] = useState<string | null>(null);
  useEffect(() => {
    if (!busy) setStageLabel(null);
    else if (liveStage && STAGE_LABELS[liveStage]) setStageLabel(STAGE_LABELS[liveStage]);
  }, [busy, liveStage]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setScrollToTopIndex(msgs.length); // the index this new user message is about to occupy
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await onSend(text, (delta) => {
        // Phase 3A: append the raw delta to the in-flight streaming buffer, creating it on the first
        // token. Never invoked when no token arrives (the non-streaming path stays byte-identical).
        setMsgs((m) => {
          const last = m[m.length - 1];
          if (last && last.role === "assistant-streaming") {
            const copy = m.slice();
            copy[copy.length - 1] = { role: "assistant-streaming", text: last.text + delta };
            return copy;
          }
          return [...m, { role: "assistant-streaming", text: delta }];
        });
      });
      // REPLACE the streaming buffer (if any) with the authoritative gated result; otherwise append
      // the normal atomic assistant message exactly as before (no-token / non-streaming path).
      setMsgs((m) => {
        const last = m[m.length - 1];
        if (last && last.role === "assistant-streaming") {
          const copy = m.slice();
          copy[copy.length - 1] = { role: "assistant", res };
          return copy;
        }
        return [...m, { role: "assistant", res }];
      });
    } catch {
      // error rendered via the `error` prop; deliberately append nothing (no stale content)
    } finally {
      setBusy(false);
    }
  }

  // R2 „Übernehmen": forget the reconciled (cleared) felder + settle the batch server-side, then
  // append the DETERMINISTIC confirmation (post-bind echo + kern result + Rückfragen) as a chat
  // message. No LLM, no client compute. On failure nothing is appended and the form keeps its values.
  async function submitParams(items: ParamItem[], deletes: string[] = []) {
    if (items.length === 0 && deletes.length === 0) return;
    try {
      const conf = await onSubmitParams(items, deletes);
      if (items.length > 0) setMsgs((m) => [...m, { role: "confirmation", conf }]);
    } catch {
      // error surfaced via the `error` prop (the host sets it); append nothing (no stale content)
    }
  }

  // The committed case-state as feld → settled value: hydrates the form fields (the single editable
  // surface) and is the baseline for the empty-field reconcile on „Übernehmen".
  const committed = Object.fromEntries(memory.case_state.map((f) => [f.feld, f.wert]));

  const composer = (
    <div className="pill-wrap">
      <div className="pill">
        <textarea
          ref={inputRef}
          className="pill-input"
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="sealingAI fragen"
          data-testid="composer-input"
        />
        <button
          className="pill-icon"
          disabled
          title="Anhang hinzufügen — in Vorbereitung"
          aria-label="Anhang hinzufügen (in Vorbereitung)"
        >
          <PaperclipIcon />
        </button>
        <button
          className="pill-send"
          onClick={() => void send()}
          disabled={busy || !input.trim()}
          title="Senden"
          aria-label="Senden"
          data-testid="composer-send"
        >
          <SendIcon />
        </button>
      </div>
    </div>
  );

  const chips = (
    <MemoryPanel memory={memory} onEdit={onEditFact} onForget={onForgetFact} onForgetAll={onForgetAll} />
  );

  const briefingButton = (
    <button
      className="make-briefing"
      onClick={onMakeBriefing}
      disabled={!canBriefing}
      data-testid="make-briefing"
    >
      Briefing erstellen
    </button>
  );

  // The cockpit's chips+kern area is empty when there are no remembered facts AND the kern has nothing
  // to show — an honest placeholder instead of a blank box (the parameter form above it is always shown).
  // Mirrors the calm Berechnungen visibility: a not_computed-only kern is "empty" here (it surfaces no
  // panel), so the placeholder shows rather than an empty box.
  const caseStateEmpty =
    memory.case_state.length === 0 &&
    (compute?.computed?.length ?? 0) === 0 &&
    (compute?.clarifications?.length ?? 0) === 0 &&
    (compute?.notes?.length ?? 0) === 0;

  // Medium Intelligence (Phase 2): the MEDIUM panel shows the most recent turn's researched medium
  // (vorläufig). Null until the backend ships the field + the feature flag is enabled.
  const latestMedium = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "assistant" && m.res.medium_intelligence)
        return m.res.medium_intelligence;
    }
    return null;
  }, [msgs]);

  // Produktspec v3.1: the PRODUKT-KANDIDAT panel shows the most recent turn's Kandidaten-Spezifikation
  // (always vorläufig). Null until the backend ships the field + the feature flag is enabled by the owner.
  const latestSpec = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "assistant" && m.res.kandidaten_spec) return m.res.kandidaten_spec;
    }
    return null;
  }, [msgs]);

  // Modus F (Hersteller-Auswahl): the most recent turn's manufacturer suggestion, or null (it fires
  // only on an explicit alternatives/manufacturer request).
  const latestAlternativen = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "assistant" && m.res.alternativen) return m.res.alternativen;
    }
    return null;
  }, [msgs]);

  // The Anfrage briefing is rendered server-side from the SESSION case-state; the message it runs is
  // the user's last substantive question (recalls the worked-out situation). The panel passes only the
  // partner id — the host injects this message + talks to /api/v2/anfrage.
  const lastUserMessage = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "user") return m.text;
    }
    return "";
  }, [msgs]);
  const panelOnAnfrage = useMemo(
    () =>
      onAnfrage
        ? (partnerId: string) =>
            onAnfrage(
              partnerId,
              lastUserMessage || "Anfrage zur besprochenen Dichtungslösung",
            )
        : undefined,
    [onAnfrage, lastUserMessage],
  );
  const panelOnDownloadPdf = useMemo(
    () =>
      onDownloadPdf
        ? () =>
            onDownloadPdf(
              lastUserMessage || "Anfrage zur besprochenen Dichtungslösung",
            )
        : undefined,
    [onDownloadPdf, lastUserMessage],
  );
  const lastAnswer = useMemo(() => {
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.role === "assistant") return m.res.answer;
    }
    return "";
  }, [msgs]);
  // Wissens-Beitrag: the host builds the full payload (situation + case-state + recommendation) from the
  // session; the panel supplies only anonym + outcome.
  const panelOnContribute = useMemo(
    () =>
      onContribute
        ? (anonym: boolean, outcome: string) =>
            onContribute({
              anonym,
              situation: lastUserMessage,
              recommendation: lastAnswer,
              outcome,
              case_state: memory.case_state.map((f) => ({ feld: f.feld, wert: f.wert })),
            })
        : undefined,
    [onContribute, lastUserMessage, lastAnswer, memory.case_state],
  );

  // claude.ai chat↔artifact: the cockpit is OPEN when the case is active OR the user opened it,
  // and NOT explicitly closed. Default / pure Q&A → chat-only (centered, no right panel). Opening
  // moves the chat left and splits ~50/50; closing returns to centered chat-only.
  const caseActive = !caseStateEmpty;
  const cockpitVisible = (caseActive || userOpened) && !userClosed;
  const openCockpit = () => {
    setUserOpened(true);
    setUserClosed(false);
  };
  const closeCockpit = () => {
    setUserClosed(true);
    setUserOpened(false);
  };
  // mount the cockpit once it has been shown, then keep it mounted (open/close = CSS only → the form
  // keeps its values; no remount).
  useEffect(() => {
    if (cockpitVisible) setEverOpened(true);
  }, [cockpitVisible]);

  // High-level parameter action in the workspace chrome — present only while the cockpit is closed.
  const openFormCta = cockpitVisible ? null : (
    <button type="button" className="open-cockpit-cta" data-testid="open-cockpit" onClick={openCockpit}>
      Parameter eingeben
    </button>
  );

  // ── chat|cockpit divider drag (split, ≥1024px) — pointer-capture, self-contained ─────────────
  // The cockpit sits on the right; new width = workspace right edge − pointer x, clamped. Committed
  // to localStorage on release (not per move). Double-click / Home → reset to the ~50/50 default.
  function onSplitterDown(e: ReactPointerEvent<HTMLDivElement>) {
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    draggingRef.current = true;
  }
  function onSplitterMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    const ws = workspaceRef.current;
    if (!ws) return;
    const rect = ws.getBoundingClientRect();
    const px = clampCockpitPx(rect.right - e.clientX, rect.width);
    dragPxRef.current = px;
    setCockpitW(`${px}px`);
  }
  function onSplitterUp(e: ReactPointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    if (dragPxRef.current != null) saveCockpitPx(dragPxRef.current);
  }
  function onSplitterReset() {
    dragPxRef.current = null;
    setCockpitW(null);
    clearCockpitPx();
  }
  // keyboard support for the separator: ←/→ nudge (left widens the cockpit), Home resets
  function onSplitterKey(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === "Home") {
      e.preventDefault();
      onSplitterReset();
      return;
    }
    const dir = e.key === "ArrowLeft" ? 1 : e.key === "ArrowRight" ? -1 : 0;
    if (dir === 0) return;
    const ws = workspaceRef.current;
    if (!ws) return;
    e.preventDefault();
    const rect = ws.getBoundingClientRect();
    const current = dragPxRef.current ?? Math.round(rect.width * 0.5);
    const px = clampCockpitPx(current + dir * 24, rect.width);
    dragPxRef.current = px;
    setCockpitW(`${px}px`);
    saveCockpitPx(px);
  }

  useEffect(() => {
    const workspace = workspaceRef.current;
    if (!workspace) return;

    const onWorkspaceWheel = (e: WheelEvent) => {
      if (e.defaultPrevented || e.ctrlKey) return;
      const log = logRef.current;
      if (!log) return;
      const target = e.target;
      if (!(target instanceof Element) || !workspace.contains(target)) return;
      if (target.closest(".cockpit-panel, .cockpit-splitter")) return;

      const path = e.composedPath();
      for (const node of path) {
        if (node === workspace) break;
        if (!(node instanceof HTMLElement)) continue;
        if (node === log) return;
        if (canScrollVertically(node, e.deltaY)) return;
      }

      const maxTop = Math.max(0, log.scrollHeight - log.clientHeight);
      if (maxTop === 0) return;
      const deltaY = wheelDeltaYPx(e, log.clientHeight);
      if (deltaY === 0) return;
      const nextTop = Math.max(0, Math.min(maxTop, log.scrollTop + deltaY));
      if (nextTop === log.scrollTop) return;

      e.preventDefault();
      log.scrollTop = nextTop;
      onScroll();
    };

    workspace.addEventListener("wheel", onWorkspaceWheel, { capture: true, passive: false });
    return () => workspace.removeEventListener("wheel", onWorkspaceWheel, { capture: true });
  }, [onScroll]);

  // null → no inline override → the CSS default (~50/50) applies; a px string → the dragged width
  const workspaceStyle = cockpitW ? ({ "--cockpit-w": cockpitW } as unknown as CSSProperties) : undefined;

  // The right cockpit panel (the artifact-equivalent): a clean header (closeable → centered chat-only)
  // + the Parameter | Readout 2-pane (side-by-side when the panel is wide, stacked when narrow — a CSS
  // container query). The fast-path form is the SINGLE form entry point; its batch submit reuses the
  // SAME settle → confirmation path. Pure placement: no data-flow / settle / recompute change.
  const missing = missingRows(committed);
  const warnings = warningRows(compute ?? null);
  const primaryClarification = (compute?.clarifications ?? [])[0];
  const solution = solutionSummary(committed, compute?.computed?.length ?? 0);
  const nextStep =
    missing[0]?.action ?? (warnings[0] ? "Kritischen Punkt prüfen" : "Herstelleranfrage vorbereiten");
  const rfqReady = caseActive && missing.length === 0 && warnings.length === 0;
  const rfqStatus = rfqReady
    ? "Vorbereitbar · aktuelle Angaben sind ausreichend strukturiert"
    : `Noch nicht bereit · ${missing.length || 1} ${missing.length === 1 ? "Punkt" : "Punkte"} offen`;
  const mediumReadoutRows = [
    { key: "medium", label: "Medium" },
    { key: "medium_kategorie", label: "Kategorie" },
    { key: "druck", label: "Druck normal" },
    { key: "druck_max", label: "Druck max." },
    { key: "betriebstemperatur", label: "Betriebstemperatur" },
    { key: "spitzentemperatur", label: "Spitzentemperatur" },
    { key: "additive", label: "Additive" },
  ].flatMap(({ key, label }) => {
    const value = committed[key];
    return value ? [{ key, label, value }] : [];
  });

  const cockpit = (
    <aside className="cockpit-panel" data-testid="case-state" aria-label="Fallkontext und Berechnungen">
      <header className="cockpit-header">
        <span className="cockpit-title">Cockpit</span>
        <button
          type="button"
          className="cockpit-close"
          data-testid="cockpit-close"
          onClick={closeCockpit}
          title="Cockpit schließen"
          aria-label="Cockpit schließen"
        >
          ×
        </button>
      </header>
      <div className="cockpit-body cockpit-body--matrix scroll-area">
        <section className="cockpit-param-column" data-testid="cockpit-param-column" aria-label="Parameter">
          <span className="cockpit-section-title">Parameter</span>
          <div className="cockpit-form" data-testid="cockpit-form">
            <ParameterForm
              variant="stage"
              onSubmit={submitParams}
              onPreview={onPreview}
              committed={committed}
            />
          </div>
          {chips}
        </section>

        <section className="cockpit-readout-column right-rail" data-testid="cockpit-readout-column" aria-label="Orientierung">
          <section className="cockpit-readout-block right-rail-block" data-testid="cockpit-solution" aria-label="Aktuelle Lösungsrichtung">
            <span className="cockpit-section-title">Aktuelle Lösungsrichtung</span>
            <p className="right-rail-main">{solution.title}</p>
            <p className="right-rail-meta">{solution.meta}</p>
          </section>

          <section className="cockpit-readout-block right-rail-block" data-testid="cockpit-next-step" aria-label="Nächster Schritt">
            <span className="cockpit-section-title">Nächster Schritt</span>
            <p className="right-rail-main">{nextStep}</p>
          </section>

          <section className="cockpit-readout-block right-rail-block" data-testid="cockpit-missing" aria-label="Wichtigste fehlende Angaben">
            <span className="cockpit-section-title">Wichtigste fehlende Angaben</span>
            {missing.length > 0 ? (
              <ul className="right-rail-list">
                {missing.slice(0, 4).map((item) => (
                  <li key={item.key}>
                    <span>{item.label}</span>
                    <small>{item.hint}</small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="cockpit-readout-empty">Keine Kernangaben offen.</p>
            )}
          </section>

          <section className="cockpit-readout-block right-rail-block" data-testid="cockpit-calculation-readout" aria-label="Berechnungen">
            <span className="cockpit-section-title">Berechnungen</span>
            <BerechnungenPanel compute={compute ?? null} view="results" />
            {(compute?.computed?.length ?? 0) === 0 ? (
              <p className="cockpit-readout-empty" data-testid="case-state-empty">
                Noch keine Werte vom Rechenkern.
              </p>
            ) : null}
          </section>

          <section className="cockpit-readout-block right-rail-block" data-testid="cockpit-warning" aria-label="Kritischster Punkt">
            <span className="cockpit-section-title">Kritischster Punkt</span>
            {warnings.length > 0 ? (
              <>
                <p className="right-rail-warning">{warnings[0]}</p>
                {primaryClarification?.one_click && onConfirmUnit ? (
                  <button
                    type="button"
                    className="right-rail-action"
                    data-testid="right-rail-confirm-unit"
                    onClick={() =>
                      onConfirmUnit(
                        primaryClarification.feld,
                        `${primaryClarification.raw_value} ${primaryClarification.suggested_unit}`,
                      )
                    }
                  >
                    Einheit bestätigen
                  </button>
                ) : null}
              </>
            ) : (
              <p className="cockpit-readout-empty">Keine kritischen Punkte zu den aktuellen Eingaben.</p>
            )}
          </section>

          <section className="cockpit-readout-block right-rail-block" data-testid="cockpit-medium-readout" aria-label="Medium">
            <span className="cockpit-section-title">Medium</span>
            {latestMedium ? (
              <MediumPanel data={latestMedium} />
            ) : mediumReadoutRows.length > 0 ? (
              <dl className="cockpit-medium-facts">
                {mediumReadoutRows.map((row) => (
                  <div key={row.key} className="cockpit-medium-fact">
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="cockpit-readout-empty">Noch keine Mediumdaten im Fallkontext.</p>
            )}
          </section>

          {latestSpec ? <KandidatenSpecPanel data={latestSpec} /> : null}
          {latestAlternativen ? (
            <AlternativenPanel
              data={latestAlternativen}
              onAnfrage={panelOnAnfrage}
              onDownloadPdf={panelOnDownloadPdf}
            />
          ) : null}

          <section className="cockpit-readout-block right-rail-block" data-testid="cockpit-rfq" aria-label="Hersteller/RFQ">
            <span className="cockpit-section-title">Hersteller/RFQ</span>
            <p className="right-rail-main">{rfqStatus}</p>
            {briefingButton}
            {panelOnContribute ? <ContributePanel onContribute={panelOnContribute} /> : null}
          </section>
        </section>
      </div>
    </aside>
  );

  // chat-only (centered, no right panel) ⟷ split (chat | divider | cockpit ~50/50). The cockpit panel
  // stays mounted once shown (everOpened); chat-only just hides it (CSS) — no remount, no state loss.
  return (
    <div
      ref={workspaceRef}
      className={`workspace workspace--${cockpitVisible ? "split" : "chat-only"}`}
      style={workspaceStyle}
      data-testid="chat-pane"
    >
      {openFormCta}
      <div className="chat-col">
        {msgs.length === 0 ? (
          // stage center: ONLY the greeting + composer over the glow — calm and centered.
          <div className="stage" data-testid="stage-center">
            <div className="stage-glow" aria-hidden="true" />
            <h1 className="greeting" data-testid="greeting">
              Welche Dichtungsfrage steht an{greetingName ? `, ${greetingName}` : ""}?
            </h1>
            {composer}
            {error && (
              <div className="error-banner" role="alert" data-testid="chat-error">
                {error}
              </div>
            )}
          </div>
        ) : (
          <div className="chat-main">
            {/* the scroll region (fade cues on the wrapper); the composer below stays docked/sticky */}
            <div className="scroll-wrap chat-scroll-wrap">
              <div className="chat-log scroll-area" data-testid="chat-log" ref={logRef} onScroll={onScroll}>
                {msgs.map((m, i) =>
                  m.role === "user" ? (
                    <div
                      key={i}
                      className="msg-user"
                      ref={i === scrollToTopIndex ? scrollTargetRef : undefined}
                    >
                      {m.text}
                    </div>
                  ) : m.role === "confirmation" ? (
                    <ParamConfirmation key={i} conf={m.conf} />
                  ) : m.role === "assistant-history" ? (
                    <div key={i} className="answer answer-history" data-testid="answer-history">
                      <Markdown source={m.text} />
                    </div>
                  ) : m.role === "assistant-streaming" ? (
                    <div
                      key={i}
                      className="answer answer-streaming"
                      data-testid="answer-streaming"
                      aria-live="polite"
                    >
                      <Markdown source={m.text} />
                    </div>
                  ) : (
                    <Answer key={i} res={m.res} />
                  ),
                )}
                {busy && (
                  <div className="msg-pending" data-testid="stage-indicator" aria-live="polite">
                    <span className="pending-dots" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                    {stageLabel && (
                      <span className="pending-label" data-testid="stage-label">
                        {stageLabel}
                      </span>
                    )}
                  </div>
                )}
                {error && (
                  <div className="error-banner" role="alert" data-testid="chat-error">
                    {error}
                  </div>
                )}
                <BriefingPane briefing={briefing} />
                <div ref={spacerRef} className="chat-log-spacer" aria-hidden="true" />
              </div>
              {showJumpButton && (
                <button
                  type="button"
                  className="chat-jump-button"
                  onClick={scrollToBottom}
                  aria-label="Zum Ende des Gesprächs springen"
                  data-testid="chat-jump-button"
                >
                  <ArrowDownIcon />
                </button>
              )}
            </div>
            <div className="chat-foot">
              {composer}
            </div>
          </div>
        )}
      </div>
      {cockpitVisible && (
        <div
          className="cockpit-splitter"
          data-testid="cockpit-splitter"
          role="separator"
          aria-orientation="vertical"
          aria-label="Breite des Cockpits anpassen"
          tabIndex={0}
          onPointerDown={onSplitterDown}
          onPointerMove={onSplitterMove}
          onPointerUp={onSplitterUp}
          onDoubleClick={onSplitterReset}
          onKeyDown={onSplitterKey}
        />
      )}
      {everOpened && cockpit}
    </div>
  );
}
