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
import { MicIcon, PlusIcon, SendIcon } from "./icons";

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

/** The pilot-ui main surface, two states of ONE conversation:
 *  - stage (no messages yet): centered greeting over the radial glow, the pill, fact chips under it
 *    — the clean Gemini-like landing;
 *  - chat view (conversation started): the message log (markdown answers, honesty badges,
 *    citations) with the same pill + chips docked at the bottom.
 * On a failed send the assistant message is NOT appended (no stale/wrong content); the error is
 * surfaced and the persistent doctrine line (Shell) stays. */
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
  const [formOpen, setFormOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { ref: logRef, onScroll } = useStickToBottom<HTMLDivElement>(msgs.length);
  // latest mapped label survives unmapped keys (recall/cite) and clears when the turn ends
  const [stageLabel, setStageLabel] = useState<string | null>(null);
  useEffect(() => {
    if (!busy) setStageLabel(null);
    else if (liveStage && STAGE_LABELS[liveStage]) setStageLabel(STAGE_LABELS[liveStage]);
  }, [busy, liveStage]);

  useEffect(() => {
    if (!formOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFormOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [formOpen]);

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
      {formOpen && (
        <div className="pill-pop" role="dialog" aria-label="Parameter eingeben">
          <ParameterForm
            onSubmit={submitParams}
            onSubmitted={() => {
              setFormOpen(false);
              inputRef.current?.focus();
            }}
          />
        </div>
      )}
      <div className="pill">
        <button
          className="pill-icon"
          onClick={() => setFormOpen((o) => !o)}
          title="Parameter eingeben"
          aria-label="Parameter eingeben"
          aria-expanded={formOpen}
          data-testid="open-parameter-form"
        >
          <PlusIcon />
        </button>
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

  // the kernel channel renders right next to the input chips (both stage + chat views)
  const kernelPanel = (
    <BerechnungenPanel compute={compute ?? null} onConfirmUnit={onConfirmUnit} />
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

  // The case-state column (chips + kern) is empty when there are no remembered facts AND the kern has
  // nothing to show — this mirrors the MemoryPanel/BerechnungenPanel null-returns so the reserved right
  // column shows an honest placeholder instead of a blank box. Read-only over existing props: no data
  // flow, settle, clarify-confirm, or recompute logic is touched.
  const caseStateEmpty =
    memory.case_state.length === 0 &&
    (compute?.computed?.length ?? 0) === 0 &&
    (compute?.not_computed?.length ?? 0) === 0 &&
    (compute?.clarifications?.length ?? 0) === 0 &&
    (compute?.notes?.length ?? 0) === 0;

  if (msgs.length === 0) {
    return (
      <div className="stage" data-testid="chat-pane">
        <div className="stage-glow" aria-hidden="true" />
        <h1 className="greeting" data-testid="greeting">
          Welche Dichtungsfrage steht an{greetingName ? `, ${greetingName}` : ""}?
        </h1>
        {composer}
        {chips}
        {kernelPanel}
        {error && (
          <div className="error-banner" role="alert" data-testid="chat-error">
            {error}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="chat-view" data-testid="chat-pane">
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
        <div className="chat-foot">{composer}</div>
      </div>
      {/* case-state: right column on wide screens (≥1024px), stacked below on narrow.
          Reserved from the first message — an honest placeholder, never a blank box, until values arrive. */}
      <aside className="case-state" data-testid="case-state" aria-label="Fallkontext und Berechnungen">
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
    </div>
  );
}
