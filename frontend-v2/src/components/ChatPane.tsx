import { useEffect, useRef, useState } from "react";
import type {
  Briefing,
  ChatResponse,
  ComputeResponse,
  ConfirmationResponse,
  ConversationMemory,
  ParamItem,
} from "../contracts";
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
  onSubmitParams: (items: ParamItem[]) => Promise<ConfirmationResponse>;
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
  // explicit "open the form" affordance (trigger b): session-sticky, moot once the case is active
  const [userOpenedForm, setUserOpenedForm] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { ref: logRef, onScroll } = useStickToBottom<HTMLDivElement>(msgs.length);
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

  // The parameter form's batch submit: settle + recompute server-side, then append the DETERMINISTIC
  // confirmation (post-bind echo + kern result + Rückfragen) as a chat message. No LLM, no client compute.
  async function submitParams(items: ParamItem[]) {
    if (items.length === 0) return;
    try {
      const conf = await onSubmitParams(items);
      setMsgs((m) => [...m, { role: "confirmation", conf }]);
    } catch {
      // error surfaced via the `error` prop (the host sets it); append nothing (no stale content)
    }
  }

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
  // (b) the user explicitly opens the form. No narrowing for users who only ever ask a question.
  const cockpitVisible = !caseStateEmpty || userOpenedForm;

  // Trigger (b): a subtle, low-key text link near the composer — present only while the cockpit is
  // hidden. Most users just chat; this stays unobtrusive (not a card).
  const openFormLink = cockpitVisible ? null : (
    <button
      type="button"
      className="open-cockpit-link"
      data-testid="open-cockpit"
      onClick={() => setUserOpenedForm(true)}
    >
      Parameter direkt eingeben
    </button>
  );

  // The persistent right cockpit — IDENTICAL on the stage and in chat-view. The parameter fast-path
  // form (compact kernel card + the "weitere Parameter" expander) is now the SINGLE form entry point
  // (the chat-view "+" popover is retired); its batch submit reuses the SAME settle → confirmation →
  // chat-view transition as the chat input. Pure placement: no data-flow / settle / recompute change.
  const cockpit = (
    <aside className="case-state" data-testid="case-state" aria-label="Fallkontext und Berechnungen">
      <ParameterForm variant="stage" onSubmit={submitParams} />
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
      <div className="chat-foot-row">{briefingButton}</div>
    </aside>
  );

  return (
    <div className={`workspace${cockpitVisible ? "" : " workspace--solo"}`} data-testid="chat-pane">
      <main className="workspace-main">
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
