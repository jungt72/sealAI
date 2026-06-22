import type { ConversationMemory } from "../contracts";
import { useFraming } from "../framing-context";

/** Fallkontext as quiet mono chips under the pill (pilot-ui): the M5 case-state with the
 * user-control surface preserved — chip body = edit, × = forget, "alles vergessen" at the end.
 * Chips render ONLY when facts exist (a fresh login keeps the clean stage). Every remembered fact
 * stays framed UNVERIFIED: the row label carries the hint visibly, and each chip carries it for
 * assistive tech + the safety contract ("zuvor genannt — bei Bedarf bestätigen") — remembered ≠
 * gospel. */
export function MemoryPanel({
  memory,
  onEdit,
  onForget,
  onForgetAll,
}: {
  memory: ConversationMemory;
  onEdit: (feld: string, wert: string) => void;
  onForget: (feld: string) => void;
  onForgetAll: () => void;
}) {
  const { remembered_hint } = useFraming();
  if (memory.case_state.length === 0) return null;
  return (
    <section className="fact-chips" data-testid="memory-panel" aria-label="Bekannter Fallkontext">
      <span className="chips-label">Fallkontext · {remembered_hint}</span>
      <ul className="chips-row">
        {memory.case_state.map((f) => (
          <li key={f.feld} className="fact-chip" data-testid="remembered-fact">
            <button
              className="fact-chip-body"
              onClick={() => onEdit(f.feld, f.wert)}
              title={`${f.feld} bearbeiten — ${remembered_hint}`}
              data-testid="edit-fact"
            >
              <span className="fact-feld">{f.feld}</span>
              <span className="fact-wert">{f.wert}</span>
            </button>
            <span className="sr-only" data-testid="remembered-hint">
              {remembered_hint}
            </span>
            <button
              className="fact-chip-x"
              onClick={() => onForget(f.feld)}
              title={`${f.feld} vergessen`}
              aria-label={`${f.feld} vergessen`}
              data-testid="forget-fact"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <button className="chips-forget-all" onClick={onForgetAll} data-testid="forget-all">
        alles vergessen
      </button>
    </section>
  );
}
