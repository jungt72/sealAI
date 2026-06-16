import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type {
  Briefing,
  ChatResponse,
  ComputeResponse,
  ConfirmationResponse,
  ConversationMemory,
  ParamItem,
} from "../contracts";
import { clampCockpitPx, clearCockpitPx, loadCockpitPx, saveCockpitPx } from "../lib/cockpitWidth";
import { useStickToBottom } from "../lib/stickToBottom";
import { Answer } from "./Answer";
import { BerechnungenPanel } from "./BerechnungenPanel";
import { BriefingPane } from "./BriefingPane";
import { MemoryPanel } from "./MemoryPanel";
import { ParamConfirmation } from "./ParamConfirmation";
import { ParameterForm } from "./ParameterForm";
import { MicIcon, SendIcon } from "./icons";

type Msg =
  | { role: "user"; text: string }
  | { role: "assistant"; res: ChatResponse }
  | { role: "confirmation"; conf: ConfirmationResponse };

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
}: {
  onSend: (message: string) => Promise<ChatResponse>;
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
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  // form engagement (open-form affordance OR first field interaction): session-sticky. Turns the
  // cockpit to the WIDE focus — the dialog stays primary until the user deliberately works the form.
  const [formEngaged, setFormEngaged] = useState(false);
  // which surface is wide; the other collapses to a peekable rail (no remount — CSS only). Default
  // "chat" (dialog-first); flips to "cockpit" when the form engages. The rail toggles flip it back.
  const [focus, setFocus] = useState<"chat" | "cockpit">("chat");
  useEffect(() => {
    if (formEngaged) setFocus("cockpit");
  }, [formEngaged]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { ref: logRef, onScroll } = useStickToBottom<HTMLDivElement>(msgs.length);
  // resizable inner split (cockpit-focus, ≥1024px): the chosen width drives the `--readout-w` track
  // of the Parameter|Readout 2-pane; null = CSS default (40%). Persisted, restored, reset on dbl-click.
  const twoPaneRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const dragPxRef = useRef<number | null>(null);
  const [readoutW, setReadoutW] = useState<string | null>(() => {
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
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await onSend(text);
      setMsgs((m) => [...m, { role: "assistant", res }]);
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
          title="Spracheingabe — in Vorbereitung"
          aria-label="Spracheingabe (in Vorbereitung)"
        >
          <MicIcon />
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

  // the kernel channel renders inside the cockpit, under the chips
  const kernelPanel = <BerechnungenPanel compute={compute ?? null} onConfirmUnit={onConfirmUnit} />;

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

  // The cockpit is HIDDEN on the empty stage and during pure knowledge-Q&A (chat stays single-column,
  // full width) and appears ONLY when (a) the case is active (!caseStateEmpty — auto-trigger) OR
  // (b) the user engages the form. No narrowing for users who only ever ask a question. A case that
  // becomes active WITHOUT form engagement stays chat-focus (dialog primary); engaging the form
  // turns to cockpit-focus.
  const cockpitVisible = !caseStateEmpty || formEngaged;

  // Trigger (b): a subtle, low-key text link near the composer — present only while the cockpit is
  // hidden. Most users just chat; this stays unobtrusive (not a card).
  const openFormLink = cockpitVisible ? null : (
    <button
      type="button"
      className="open-cockpit-link"
      data-testid="open-cockpit"
      onClick={() => setFormEngaged(true)}
    >
      Parameter direkt eingeben
    </button>
  );

  // ── inner splitter drag (Parameter|Readout, cockpit-focus) — pointer-capture, self-contained ──
  // The Readout sits on the right of the 2-pane; new width = 2-pane right edge − pointer x, clamped.
  // Committed to localStorage on release (not per move). Double-click / Home → reset to the default.
  function onSplitterDown(e: ReactPointerEvent<HTMLDivElement>) {
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    draggingRef.current = true;
  }
  function onSplitterMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    const pane = twoPaneRef.current;
    if (!pane) return;
    const rect = pane.getBoundingClientRect();
    const px = clampCockpitPx(rect.right - e.clientX, rect.width);
    dragPxRef.current = px;
    setReadoutW(`${px}px`);
  }
  function onSplitterUp(e: ReactPointerEvent<HTMLDivElement>) {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    if (dragPxRef.current != null) saveCockpitPx(dragPxRef.current);
  }
  function onSplitterReset() {
    dragPxRef.current = null;
    setReadoutW(null);
    clearCockpitPx();
  }
  // keyboard support for the separator: ←/→ nudge (left widens the Readout), Home resets
  function onSplitterKey(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === "Home") {
      e.preventDefault();
      onSplitterReset();
      return;
    }
    const dir = e.key === "ArrowLeft" ? 1 : e.key === "ArrowRight" ? -1 : 0;
    if (dir === 0) return;
    const pane = twoPaneRef.current;
    if (!pane) return;
    e.preventDefault();
    const rect = pane.getBoundingClientRect();
    const current = dragPxRef.current ?? Math.round(rect.width * 0.4);
    const px = clampCockpitPx(current + dir * 24, rect.width);
    dragPxRef.current = px;
    setReadoutW(`${px}px`);
    saveCockpitPx(px);
  }

  // null → no inline override → the CSS default (40%) applies; a px string → the dragged width
  const twoPaneStyle = readoutW ? ({ "--readout-w": readoutW } as unknown as CSSProperties) : undefined;

  // Rail peeks (committed only — never a preview/draft value): the cockpit-summary-rail shows the
  // committed kern value + fact count; the chat-rail shows the last message. Both surfaces stay
  // MOUNTED in either focus (CSS collapse, no remount) so msgs + form vals survive every toggle.
  const firstComputed = compute?.computed?.[0];
  const committedV = firstComputed
    ? `${firstComputed.value.toFixed(2).replace(".", ",")} ${firstComputed.unit}`
    : null;
  const factCount = memory.case_state.length;
  const lastMsg = msgs[msgs.length - 1];
  const lastMsgPreview = !lastMsg
    ? "Neue Frage stellen"
    : lastMsg.role === "user"
      ? lastMsg.text
      : lastMsg.role === "confirmation"
        ? "Werte übernommen"
        : lastMsg.res.answer;

  // The right cockpit — a 2-pane in cockpit-focus (Parameter | Readout), a summary rail in chat-focus.
  // The fast-path form is the SINGLE form entry point; its batch submit reuses the SAME settle →
  // confirmation → chat-view transition. Pure placement: no data-flow / settle / recompute change.
  const cockpit = (
    <aside className="case-state" data-testid="case-state" aria-label="Fallkontext und Berechnungen">
      <button
        type="button"
        className="cockpit-rail-peek"
        data-testid="expand-cockpit"
        onClick={() => setFocus("cockpit")}
        aria-label="Cockpit öffnen"
      >
        <span className="rail-peek-kicker">Cockpit</span>
        {committedV && <span className="rail-peek-v">{committedV}</span>}
        {factCount > 0 && <span className="rail-peek-count">{factCount} Fakten</span>}
        <span className="rail-peek-expand" aria-hidden="true">›</span>
      </button>
      <div className="cockpit-2pane" data-testid="cockpit-2pane" ref={twoPaneRef} style={twoPaneStyle}>
        <div className="cockpit-pane cockpit-pane--param" data-testid="cockpit-param">
          <ParameterForm
            variant="stage"
            onSubmit={submitParams}
            onPreview={onPreview}
            committed={committed}
            onEngage={() => setFormEngaged(true)}
          />
        </div>
        <div
          className="cockpit-splitter"
          data-testid="cockpit-splitter"
          role="separator"
          aria-orientation="vertical"
          aria-label="Breite der Berechnungen anpassen"
          tabIndex={0}
          onPointerDown={onSplitterDown}
          onPointerMove={onSplitterMove}
          onPointerUp={onSplitterUp}
          onDoubleClick={onSplitterReset}
          onKeyDown={onSplitterKey}
        />
        <div className="cockpit-pane cockpit-pane--readout" data-testid="cockpit-readout">
          {caseStateEmpty ? (
            <p className="case-state-empty" data-testid="case-state-empty">
              Noch keine bestätigten Eingaben — sobald Werte vorliegen, erscheinen Fallkontext und der
              Rechenkern hier.
            </p>
          ) : (
            <>
              {chips}
              {kernelPanel}
            </>
          )}
          <div className="readout-briefing">
            <p className="readout-briefing-soon">Briefing · RFQ-Reife — kommt bald</p>
            {briefingButton}
          </div>
        </div>
      </div>
    </aside>
  );

  // one surface wide at a time: solo (no cockpit) · focus-chat (chat wide, cockpit rail) ·
  // focus-cockpit (cockpit wide, chat rail). Pure CSS class — both surfaces stay mounted.
  const workspaceMode = !cockpitVisible ? "solo" : focus === "cockpit" ? "focus-cockpit" : "focus-chat";

  return (
    <div className={`workspace workspace--${workspaceMode}`} data-testid="chat-pane">
      <main className="workspace-main">
        <button
          type="button"
          className="chat-rail-peek"
          data-testid="expand-chat"
          onClick={() => setFocus("chat")}
          aria-label="Chat öffnen"
        >
          <span className="rail-peek-kicker">Chat</span>
          <span className="rail-peek-last">{lastMsgPreview}</span>
          <span className="rail-peek-expand" aria-hidden="true">›</span>
        </button>
        {msgs.length === 0 ? (
          // stage center: ONLY the greeting + composer over the glow — calm and centered.
          <div className="stage" data-testid="stage-center">
            <div className="stage-glow" aria-hidden="true" />
            <h1 className="greeting" data-testid="greeting">
              Welche Dichtungsfrage steht an{greetingName ? `, ${greetingName}` : ""}?
            </h1>
            {composer}
            {openFormLink}
            {error && (
              <div className="error-banner" role="alert" data-testid="chat-error">
                {error}
              </div>
            )}
          </div>
        ) : (
          <div className="chat-main">
            <div className="chat-log" data-testid="chat-log" ref={logRef} onScroll={onScroll}>
              {msgs.map((m, i) =>
                m.role === "user" ? (
                  <div key={i} className="msg-user">
                    {m.text}
                  </div>
                ) : m.role === "confirmation" ? (
                  <ParamConfirmation key={i} conf={m.conf} />
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
            </div>
            <div className="chat-foot">
              {composer}
              {openFormLink}
            </div>
          </div>
        )}
      </main>
      {cockpitVisible && cockpit}
    </div>
  );
}
