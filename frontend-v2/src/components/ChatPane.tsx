import { useEffect, useRef, useState } from "react";
import type { Briefing, ChatResponse, ConversationMemory } from "../contracts";
import { useStickToBottom } from "../lib/stickToBottom";
import { Answer } from "./Answer";
import { BriefingPane } from "./BriefingPane";
import { MemoryPanel } from "./MemoryPanel";
import { ParameterForm } from "./ParameterForm";
import { MicIcon, PlusIcon, SendIcon } from "./icons";

type Msg = { role: "user"; text: string } | { role: "assistant"; res: ChatResponse };

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
  onSubmitParam,
  onMakeBriefing,
  canBriefing,
  briefing,
  greetingName,
}: {
  onSend: (message: string) => Promise<ChatResponse>;
  error: string | null;
  memory: ConversationMemory;
  onEditFact: (feld: string, wert: string) => void;
  onForgetFact: (feld: string) => void;
  onForgetAll: () => void;
  onSubmitParam: (feld: string, wert: string) => void;
  onMakeBriefing: () => void;
  canBriefing: boolean;
  briefing: Briefing | null;
  greetingName?: string | null;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { ref: logRef, onScroll } = useStickToBottom<HTMLDivElement>(msgs.length);

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

  const composer = (
    <div className="pill-wrap">
      {formOpen && (
        <div className="pill-pop" role="dialog" aria-label="Parameter eingeben">
          <ParameterForm
            onSubmit={onSubmitParam}
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

  if (msgs.length === 0) {
    return (
      <div className="stage" data-testid="chat-pane">
        <div className="stage-glow" aria-hidden="true" />
        <h1 className="greeting" data-testid="greeting">
          Welche Dichtungsfrage steht an{greetingName ? `, ${greetingName}` : ""}?
        </h1>
        {composer}
        {chips}
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
      <div className="chat-log" data-testid="chat-log" ref={logRef} onScroll={onScroll}>
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="msg-user">
              {m.text}
            </div>
          ) : (
            <Answer key={i} res={m.res} />
          ),
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
        <div className="chat-foot-row">
          {chips}
          <button
            className="make-briefing"
            onClick={onMakeBriefing}
            disabled={!canBriefing}
            data-testid="make-briefing"
          >
            Briefing erstellen
          </button>
        </div>
      </div>
    </div>
  );
}
