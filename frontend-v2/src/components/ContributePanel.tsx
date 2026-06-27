import { useState } from "react";

/**
 * "Lösung zum Wissensaufbau beitragen" — the user opts to share their worked-out situation + the REAL-WORLD
 * outcome to improve sealingAI. Anonymous by default. The contribution is an untrusted DRAFT in the owner
 * review queue; it NEVER auto-feeds a recommendation (it improves sealingAI only after a fachliche review).
 */
export function ContributePanel({
  onContribute,
}: {
  onContribute: (anonym: boolean, outcome: string) => Promise<{ hinweis: string }>;
}) {
  const [open, setOpen] = useState(false);
  const [anonym, setAnonym] = useState(true);
  const [outcome, setOutcome] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [hinweis, setHinweis] = useState("");

  async function submit() {
    setState("sending");
    try {
      const r = await onContribute(anonym, outcome);
      setHinweis(r.hinweis);
      setState("sent");
    } catch {
      setState("error");
    }
  }

  if (state === "sent") {
    return (
      <div className="contrib-done" data-testid="contrib-done">
        <strong className="contrib-ok">✓ Beitrag übermittelt</strong>
        <p className="contrib-hinweis">{hinweis}</p>
      </div>
    );
  }
  if (!open) {
    return (
      <button
        type="button"
        className="contrib-open"
        data-testid="contrib-open"
        onClick={() => setOpen(true)}
      >
        Lösung zum Wissensaufbau beitragen
      </button>
    );
  }
  return (
    <div className="contrib-form" data-testid="contrib-form">
      <p className="contrib-intro">
        Teile deine ausgearbeitete Situation + das Ergebnis, um sealingAI zu verbessern. Der Beitrag geht
        ungeprüft in die Wissens-Review-Queue und fließt nie automatisch in eine Empfehlung.
      </p>
      <label className="contrib-check">
        <input
          type="checkbox"
          checked={anonym}
          data-testid="contrib-anonym"
          onChange={(e) => setAnonym(e.target.checked)}
        />
        <span>Anonym beitragen (keine Identität übermittelt)</span>
      </label>
      <label className="contrib-field">
        <span>Ergebnis / Erfahrung (was hat funktioniert? bitte keine Namen/Firmen)</span>
        <textarea
          value={outcome}
          rows={3}
          data-testid="contrib-outcome"
          placeholder="z. B. FKM-AS hat bei 150 °C gehalten; der Hersteller bestätigte die Maße"
          onChange={(e) => setOutcome(e.target.value)}
        />
      </label>
      <div className="contrib-actions">
        <button
          type="button"
          className="contrib-submit"
          data-testid="contrib-submit"
          disabled={state === "sending"}
          onClick={() => void submit()}
        >
          {state === "sending" ? "Wird gesendet…" : "Beitragen"}
        </button>
        <button type="button" className="contrib-cancel" onClick={() => setOpen(false)}>
          Abbrechen
        </button>
      </div>
      {state === "error" ? (
        <p className="contrib-error">Übermittlung fehlgeschlagen — bitte erneut versuchen.</p>
      ) : null}
    </div>
  );
}
