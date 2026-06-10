import { useState } from "react";
import type { ChatResponse } from "../contracts";
import { Answer } from "./Answer";

type Msg = { role: "user"; text: string } | { role: "assistant"; res: ChatResponse };

/** Center column: the conversation. On a failed send the assistant message is NOT appended (no
 * stale/wrong content); the error is surfaced and the persistent SafetyBanner (Shell) stays. */
export function ChatPane({
  onSend,
  error,
}: {
  onSend: (message: string) => Promise<ChatResponse>;
  error: string | null;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

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

  return (
    <div className="chat-pane" data-testid="chat-pane">
      <div className="chat-log">
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
      </div>
      <div className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Dichtungstechnische Frage …"
          data-testid="composer-input"
        />
        <button onClick={() => void send()} disabled={busy} data-testid="composer-send">
          Senden
        </button>
      </div>
    </div>
  );
}
