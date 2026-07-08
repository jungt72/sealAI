import { useEffect, useState } from "react";

import { fetchLegalDoctrine, type LegalDoctrine } from "../api/legal";
import type { ApiClient, ApiError } from "../api/client";

interface LegalGateProps {
  api: ApiClient;
  onAccepted: () => void;
}

/** Legal-by-Design Phase B (Goal 3): blocks productive use (chat/upload/case functions — the whole
 * Shell) until a business user completes onboarding — company identity + the two required
 * confirmations. Mirrors the `.login` pre-auth screen's visual language (same stage-glow container)
 * so the flow reads as ONE continuous gate, not two unrelated screens.
 *
 * Frontend-side enable switch (`VITE_LEGAL_GATE_ENABLED`, checked by the caller in App.tsx) mirrors
 * the backend's `legal_gate_enabled` — both default OFF until the draft legal texts
 * (frontend/(marketing)/{nutzungsbedingungen,datenschutz,auftragsverarbeitung}) have had an
 * attorney review pass. This component itself has no opinion on that flag; App.tsx decides whether
 * to mount it at all. */
export function LegalGate({ api, onAccepted }: LegalGateProps) {
  const [doctrine, setDoctrine] = useState<LegalDoctrine | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [businessEmail, setBusinessEmail] = useState("");
  const [role, setRole] = useState("");
  const [vatId, setVatId] = useState("");
  const [legalBasisChecked, setLegalBasisChecked] = useState(false);
  const [dpaChecked, setDpaChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchLegalDoctrine().then((d) => {
      if (!cancelled) setDoctrine(d);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const canSubmit =
    Boolean(doctrine) &&
    companyName.trim().length > 0 &&
    businessEmail.trim().length > 0 &&
    role.trim().length > 0 &&
    legalBasisChecked &&
    dpaChecked &&
    !submitting;

  const submit = async () => {
    if (!doctrine) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.submitLegalAcceptance({
        company_name: companyName.trim(),
        business_email: businessEmail.trim(),
        role: role.trim(),
        vat_id: vatId.trim(),
        legal_basis_accepted: legalBasisChecked,
        dpa_accepted: dpaChecked,
        business_user_confirmed: legalBasisChecked,
        terms_version: doctrine.terms_version,
        privacy_version: doctrine.privacy_version,
        dpa_version: doctrine.dpa_version,
      });
      onAccepted();
    } catch (e) {
      const status = (e as ApiError).status;
      if (status === 422) {
        setError(
          "Bitte prüfen Sie Ihre Angaben — eine geschäftliche E-Mail-Adresse (kein privater Freemail-Anbieter) ist erforderlich.",
        );
      } else if (status === 409) {
        setError("Die Rechtstexte wurden zwischenzeitlich aktualisiert — bitte die Seite neu laden.");
      } else {
        setError("Die Bestätigung konnte nicht gespeichert werden — bitte erneut versuchen.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login legal-gate" data-testid="legal-gate">
      <div className="stage-glow" aria-hidden="true" />
      <div className="legal-gate-card">
        <h1 className="legal-gate-title">Bevor es losgeht</h1>
        <p className="legal-gate-intro">
          sealingAI ist eine geschäftliche Plattform. Bitte bestätigen Sie Ihre Angaben, um
          fortzufahren.
        </p>

        <div className="legal-gate-field">
          <label htmlFor="lg-company">Firma</label>
          <input
            id="lg-company"
            type="text"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            data-testid="legal-gate-company"
          />
        </div>
        <div className="legal-gate-field">
          <label htmlFor="lg-email">Geschäftliche E-Mail-Adresse</label>
          <input
            id="lg-email"
            type="email"
            value={businessEmail}
            onChange={(e) => setBusinessEmail(e.target.value)}
            data-testid="legal-gate-email"
          />
        </div>
        <div className="legal-gate-field">
          <label htmlFor="lg-role">Ihre Rolle</label>
          <input
            id="lg-role"
            type="text"
            placeholder="z. B. Einkauf, Konstruktion, Instandhaltung"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            data-testid="legal-gate-role"
          />
        </div>
        <div className="legal-gate-field">
          <label htmlFor="lg-vat">USt-IdNr. (optional)</label>
          <input
            id="lg-vat"
            type="text"
            value={vatId}
            onChange={(e) => setVatId(e.target.value)}
            data-testid="legal-gate-vat"
          />
        </div>

        <label className="legal-gate-checkbox">
          <input
            type="checkbox"
            checked={legalBasisChecked}
            onChange={(e) => setLegalBasisChecked(e.target.checked)}
            data-testid="legal-gate-checkbox-terms"
          />
          <span>
            Ich bestätige, dass ich sealingAI im Rahmen einer gewerblichen oder selbständigen
            beruflichen Tätigkeit nutze, und akzeptiere die{" "}
            <a href="/nutzungsbedingungen" target="_blank" rel="noopener noreferrer">
              Nutzungsbedingungen
            </a>{" "}
            sowie die{" "}
            <a href="/datenschutz" target="_blank" rel="noopener noreferrer">
              Datenschutzerklärung
            </a>
            .
          </span>
        </label>
        <label className="legal-gate-checkbox">
          <input
            type="checkbox"
            checked={dpaChecked}
            onChange={(e) => setDpaChecked(e.target.checked)}
            data-testid="legal-gate-checkbox-dpa"
          />
          <span>
            Ich akzeptiere die{" "}
            <a href="/auftragsverarbeitung" target="_blank" rel="noopener noreferrer">
              Auftragsverarbeitungsvereinbarung (AVV)
            </a>{" "}
            für den Fall, dass im Rahmen der Nutzung personenbezogene Daten Dritter verarbeitet
            werden.
          </span>
        </label>

        {error && (
          <p role="alert" className="legal-gate-error">
            {error}
          </p>
        )}

        <button onClick={() => void submit()} disabled={!canSubmit} data-testid="legal-gate-submit">
          {submitting ? "Wird gespeichert …" : "Bestätigen und fortfahren"}
        </button>
      </div>
    </div>
  );
}
