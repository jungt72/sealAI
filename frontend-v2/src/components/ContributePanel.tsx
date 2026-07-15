import { useState } from "react";

import type {
  ContributionGovernanceSelection,
  ContributionResponse,
  LifecycleReceiptResponse,
  PiiClassification,
} from "../contracts";

type RightsMode = ContributionGovernanceSelection["rights_basis"];
type DocumentType = ContributionGovernanceSelection["document_type"];

/** Governed contribution capture. Declarations are workflow input, never a legal determination. */
export function ContributePanel({
  onContribute,
  onWithdraw,
}: {
  onContribute: (
    anonym: boolean,
    outcome: string,
    governance: ContributionGovernanceSelection,
  ) => Promise<ContributionResponse>;
  onWithdraw?: (id: number) => Promise<LifecycleReceiptResponse>;
}) {
  const [open, setOpen] = useState(false);
  const [anonym, setAnonym] = useState(true);
  const [outcome, setOutcome] = useState("");
  const [rightsMode, setRightsMode] = useState<RightsMode>("review_required");
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [provenance, setProvenance] = useState("");
  const [documentType, setDocumentType] = useState<DocumentType>("other_review_required");
  const [pii, setPii] = useState<PiiClassification>("unknown");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [result, setResult] = useState<ContributionResponse | null>(null);
  const [withdrawal, setWithdrawal] = useState<LifecycleReceiptResponse | null>(null);
  const [withdrawing, setWithdrawing] = useState(false);

  async function submit() {
    if (!rightsConfirmed || !provenance.trim()) return;
    setState("sending");
    try {
      const response = await onContribute(anonym, outcome, {
        rights_confirmed: true,
        rights_basis: rightsMode,
        license_id: rightsMode,
        provenance: provenance.trim(),
        document_type: documentType,
        pii_classification: pii,
        prompt_trust: "untrusted",
      });
      setResult(response);
      setState("sent");
    } catch {
      setState("error");
    }
  }

  async function withdraw() {
    if (!result || !onWithdraw) return;
    setWithdrawing(true);
    try {
      setWithdrawal(await onWithdraw(result.id));
    } finally {
      setWithdrawing(false);
    }
  }

  if (state === "sent" && result) {
    return (
      <div className="contrib-done" data-testid="contrib-done">
        <strong className="contrib-ok">✓ Beitrag erfasst</strong>
        <p className="contrib-hinweis">{result.hinweis}</p>
        {withdrawal ? (
          <div data-testid="contrib-withdrawal-receipt">
            <strong>Beitrag gesperrt und in Quarantäne</strong>
            <p>Beleg: {withdrawal.receipt_id}</p>
            <p>Digest: {withdrawal.receipt_digest}</p>
          </div>
        ) : onWithdraw ? (
          <button
            type="button"
            className="contrib-cancel"
            disabled={withdrawing}
            onClick={() => void withdraw()}
          >
            {withdrawing ? "Wird gesperrt…" : "Beitrag zurückziehen"}
          </button>
        ) : null}
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
        Der Beitrag wird als untrusted markiert und zunächst in Review-Quarantäne erfasst. Er wird
        nicht automatisch für Antworten oder Empfehlungen verwendet. Rechts- und Aufbewahrungsregeln
        stammen aus der extern bereitgestellten Governance-Fassung.
      </p>
      <label className="contrib-check">
        <input
          type="checkbox"
          checked={anonym}
          data-testid="contrib-anonym"
          onChange={(event) => setAnonym(event.target.checked)}
        />
        <span>Ohne Namen anzeigen (serverseitige Besitzerzuordnung bleibt für Rückzug erhalten)</span>
      </label>
      <label className="contrib-field">
        <span>Ergebnis / Erfahrung (bitte keine unnötigen Namen oder Firmendaten)</span>
        <textarea
          value={outcome}
          rows={3}
          data-testid="contrib-outcome"
          placeholder="Ergebnis oder beobachtete Erfahrung"
          onChange={(event) => setOutcome(event.target.value)}
        />
      </label>
      <label className="contrib-field">
        <span>Herkunft / Provenienz</span>
        <input
          value={provenance}
          maxLength={255}
          data-testid="contrib-provenance"
          onChange={(event) => setProvenance(event.target.value)}
        />
      </label>
      <label className="contrib-field">
        <span>Deklarierte Rechte-/Lizenzgrundlage</span>
        <select
          value={rightsMode}
          data-testid="contrib-rights-basis"
          onChange={(event) => setRightsMode(event.target.value as RightsMode)}
        >
          <option value="review_required">Prüfung erforderlich</option>
          <option value="owner_supplied">Eigene Inhalte</option>
          <option value="documented_permission">Dokumentierte Erlaubnis</option>
        </select>
      </label>
      <label className="contrib-field">
        <span>Dokumenttyp</span>
        <select
          value={documentType}
          onChange={(event) => setDocumentType(event.target.value as DocumentType)}
        >
          <option value="other_review_required">Sonstiges – Prüfung erforderlich</option>
          <option value="field_outcome">Felddaten / Ergebnis</option>
          <option value="technical_note">Technische Notiz</option>
          <option value="test_report">Testbericht</option>
        </select>
      </label>
      <label className="contrib-field">
        <span>Personenbezogene Daten</span>
        <select value={pii} onChange={(event) => setPii(event.target.value as PiiClassification)}>
          <option value="unknown">Unbekannt – Prüfung erforderlich</option>
          <option value="none_declared">Keine deklariert</option>
          <option value="present">Enthalten</option>
        </select>
      </label>
      <label className="contrib-check">
        <input
          type="checkbox"
          checked={rightsConfirmed}
          data-testid="contrib-rights-confirmed"
          onChange={(event) => setRightsConfirmed(event.target.checked)}
        />
        <span>Ich bestätige die oben gewählte Rechte-/Lizenzdeklaration für diesen Beitrag.</span>
      </label>
      <div className="contrib-actions">
        <button
          type="button"
          className="contrib-submit"
          data-testid="contrib-submit"
          disabled={state === "sending" || !rightsConfirmed || !provenance.trim()}
          onClick={() => void submit()}
        >
          {state === "sending" ? "Wird erfasst…" : "In Review-Quarantäne erfassen"}
        </button>
        <button type="button" className="contrib-cancel" onClick={() => setOpen(false)}>
          Abbrechen
        </button>
      </div>
      {state === "error" ? (
        <p className="contrib-error">Erfassung fehlgeschlagen — bitte erneut versuchen.</p>
      ) : null}
    </div>
  );
}
