import type { ConversationMemory } from "../contracts";
import { useFraming } from "../framing-context";

/** Cockpit content: the M5 case-state (remembered facts) + history, with the user-control surface
 * (edit / forget). Every remembered fact is framed UNVERIFIED ("zuvor genannt — bei Bedarf
 * bestätigen") — remembered ≠ gospel. */
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
  return (
    <section className="memory-panel" data-testid="memory-panel">
      <header className="cockpit-head">
        <h3>Bekannter Fallkontext</h3>
        {memory.case_state.length > 0 && (
          <button className="link-danger" onClick={onForgetAll} data-testid="forget-all">
            alles vergessen
          </button>
        )}
      </header>
      {memory.case_state.length === 0 ? (
        <p className="muted">Noch nichts erinnert.</p>
      ) : (
        <ul className="fact-list">
          {memory.case_state.map((f) => (
            <li key={f.feld} className="fact" data-testid="remembered-fact">
              <div className="fact-kv">
                <span className="fact-feld">{f.feld}</span>
                <span className="fact-wert">{f.wert}</span>
              </div>
              <div className="fact-hint" data-testid="remembered-hint">
                {remembered_hint}
              </div>
              <div className="fact-actions">
                <button onClick={() => onEdit(f.feld, f.wert)} data-testid="edit-fact">
                  bearbeiten
                </button>
                <button className="link-danger" onClick={() => onForget(f.feld)} data-testid="forget-fact">
                  vergessen
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
