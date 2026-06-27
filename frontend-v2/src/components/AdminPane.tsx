import { useCallback, useEffect, useState } from "react";

import type { ApiClient } from "../api/client";
import type { AdminContribution, AdminLead, AdminPartner } from "../contracts";

const EMPTY: AdminPartner = {
  hersteller: "",
  firmenname: "",
  aktiv: false,
  lead_email: "",
  website: "",
  beschreibung: "",
  standort: "",
  kontakt_oeffentlich: "",
  partner_seit: "",
  plan: "",
  werkstoffe: [],
  bauformen: [],
  groessen: "",
  zertifikate: [],
};

const csv = (xs: string[]) => xs.join(", ");
const parseCsv = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

/**
 * Owner/admin dashboard for the Hersteller-Partner pool (Modus F). Manage the PAYING partners (CRUD)
 * and read the captured leads (the Anfragen routed to the manufacturers). Shown only to a token that
 * carries the admin realm-role; the backend independently re-checks the role on EVERY /admin call, so
 * a tampered token never grants access — this view only decides what the SPA renders. Neutrality:
 * `plan` is editable billing metadata here; it NEVER influences the user-facing pool ranking (which is
 * capability-fit only, §3.9). `lead_email` is the routing target the owner manages.
 */
export function AdminPane({
  api,
  onClose,
}: {
  api: ApiClient;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"hersteller" | "leads" | "beitraege">("hersteller");
  const [partners, setPartners] = useState<AdminPartner[]>([]);
  const [leads, setLeads] = useState<AdminLead[]>([]);
  const [contributions, setContributions] = useState<AdminContribution[]>([]);
  const [editing, setEditing] = useState<{
    draft: AdminPartner;
    isNew: boolean;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadPartners = useCallback(() => {
    setError(null);
    api
      .adminListHersteller()
      .then((r) => setPartners(r.hersteller))
      .catch(() => setError("Laden fehlgeschlagen."));
  }, [api]);
  const loadLeads = useCallback(() => {
    setError(null);
    api
      .adminListLeads()
      .then((r) => setLeads(r.leads))
      .catch(() => setError("Laden fehlgeschlagen."));
  }, [api]);
  const loadContributions = useCallback(() => {
    setError(null);
    api
      .adminListContributions()
      .then((r) => setContributions(r.contributions))
      .catch(() => setError("Laden fehlgeschlagen."));
  }, [api]);
  const setContributionStatus = (id: number, status: string) => {
    api
      .adminSetContributionStatus(id, status, "")
      .then(loadContributions)
      .catch(() => setError("Speichern fehlgeschlagen."));
  };

  useEffect(() => {
    if (tab === "hersteller") loadPartners();
    else if (tab === "leads") loadLeads();
    else loadContributions();
  }, [tab, loadPartners, loadLeads, loadContributions]);

  const patch = (p: Partial<AdminPartner>) =>
    setEditing((e) => (e ? { ...e, draft: { ...e.draft, ...p } } : e));

  async function save() {
    if (!editing) return;
    const { draft } = editing;
    if (!draft.hersteller.trim()) {
      setError("Die Hersteller-ID darf nicht leer sein.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { hersteller, ...body } = draft;
      await api.adminUpsertHersteller(hersteller, body);
      setEditing(null);
      loadPartners();
    } catch {
      setError("Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError(null);
    try {
      await api.adminDeleteHersteller(id);
      loadPartners();
    } catch {
      setError("Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  function field(
    label: string,
    value: string,
    onChange: (v: string) => void,
    testid?: string,
    disabled = false,
  ) {
    return (
      <label className="admin-field">
        <span>{label}</span>
        <input
          value={value}
          disabled={disabled}
          data-testid={testid}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  }

  return (
    <section
      className="admin-pane"
      data-testid="admin-pane"
      aria-label="Hersteller-Verwaltung"
    >
      <header className="admin-head">
        <h1 className="admin-title">Hersteller-Verwaltung</h1>
        <button
          type="button"
          className="admin-close"
          onClick={onClose}
          data-testid="admin-close"
        >
          Zurück zum Chat
        </button>
      </header>

      <div className="admin-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "hersteller"}
          className={`admin-tab${tab === "hersteller" ? " admin-tab--active" : ""}`}
          onClick={() => setTab("hersteller")}
          data-testid="tab-hersteller"
        >
          Hersteller
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "leads"}
          className={`admin-tab${tab === "leads" ? " admin-tab--active" : ""}`}
          onClick={() => setTab("leads")}
          data-testid="tab-leads"
        >
          Leads
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "beitraege"}
          className={`admin-tab${tab === "beitraege" ? " admin-tab--active" : ""}`}
          onClick={() => setTab("beitraege")}
          data-testid="tab-beitraege"
        >
          Beiträge
        </button>
      </div>

      {error ? (
        <p className="admin-error" data-testid="admin-error">
          {error}
        </p>
      ) : null}

      {tab === "hersteller" ? (
        <div className="admin-body">
          {editing ? (
            <div className="admin-form" data-testid="admin-form">
              <h2 className="admin-form-title">
                {editing.isNew
                  ? "Neuer Hersteller"
                  : `Bearbeiten: ${editing.draft.firmenname || editing.draft.hersteller}`}
              </h2>
              {field(
                "Hersteller-ID (stabil, keine Leerzeichen)",
                editing.draft.hersteller,
                (v) => patch({ hersteller: v }),
                "f-id",
                !editing.isNew,
              )}
              {field(
                "Firmenname",
                editing.draft.firmenname,
                (v) => patch({ firmenname: v }),
                "f-name",
              )}
              <label className="admin-check">
                <input
                  type="checkbox"
                  checked={editing.draft.aktiv}
                  data-testid="f-aktiv"
                  onChange={(e) => patch({ aktiv: e.target.checked })}
                />
                <span>Aktiv (im Pool gelistet — zahlender Partner)</span>
              </label>
              {field(
                "Lead-E-Mail (Routing-Ziel, intern)",
                editing.draft.lead_email,
                (v) => patch({ lead_email: v }),
                "f-email",
              )}
              {field("Website", editing.draft.website, (v) =>
                patch({ website: v }),
              )}
              <label className="admin-field">
                <span>Beschreibung</span>
                <textarea
                  value={editing.draft.beschreibung}
                  rows={3}
                  onChange={(e) => patch({ beschreibung: e.target.value })}
                />
              </label>
              {field("Standort", editing.draft.standort, (v) =>
                patch({ standort: v }),
              )}
              {field("Öffentlicher Kontakt", editing.draft.kontakt_oeffentlich, (v) =>
                patch({ kontakt_oeffentlich: v }),
              )}
              {field("Partner seit", editing.draft.partner_seit, (v) =>
                patch({ partner_seit: v }),
              )}
              {field(
                "Plan (nur Abrechnung — keine Auswirkung auf die Auswahl)",
                editing.draft.plan,
                (v) => patch({ plan: v }),
              )}
              {field(
                "Werkstoffe (kommagetrennt)",
                csv(editing.draft.werkstoffe),
                (v) => patch({ werkstoffe: parseCsv(v) }),
                "f-werkstoffe",
              )}
              {field("Bauformen (kommagetrennt)", csv(editing.draft.bauformen), (v) =>
                patch({ bauformen: parseCsv(v) }),
              )}
              {field("Größen", editing.draft.groessen, (v) =>
                patch({ groessen: v }),
              )}
              {field(
                "Zertifikate (kommagetrennt)",
                csv(editing.draft.zertifikate),
                (v) => patch({ zertifikate: parseCsv(v) }),
              )}
              <div className="admin-form-actions">
                <button
                  type="button"
                  className="admin-btn admin-btn--primary"
                  onClick={() => void save()}
                  disabled={busy}
                  data-testid="admin-save"
                >
                  Speichern
                </button>
                <button
                  type="button"
                  className="admin-btn"
                  onClick={() => setEditing(null)}
                  disabled={busy}
                >
                  Abbrechen
                </button>
              </div>
            </div>
          ) : (
            <>
              <button
                type="button"
                className="admin-btn admin-btn--primary"
                onClick={() => setEditing({ draft: EMPTY, isNew: true })}
                data-testid="admin-new"
              >
                + Neuer Hersteller
              </button>
              {partners.length === 0 ? (
                <p className="admin-empty">Noch keine Hersteller angelegt.</p>
              ) : (
                <ul className="admin-list">
                  {partners.map((p) => (
                    <li
                      key={p.hersteller}
                      className="admin-row"
                      data-testid={`row-${p.hersteller}`}
                    >
                      <div className="admin-row-main">
                        <span className="admin-row-name">
                          {p.firmenname || p.hersteller}
                        </span>
                        <span
                          className={`admin-row-badge${p.aktiv ? " admin-row-badge--on" : ""}`}
                        >
                          {p.aktiv ? "aktiv" : "inaktiv"}
                        </span>
                        {p.plan ? (
                          <span className="admin-row-plan">{p.plan}</span>
                        ) : null}
                      </div>
                      <div className="admin-row-actions">
                        <button
                          type="button"
                          className="admin-btn"
                          onClick={() => setEditing({ draft: p, isNew: false })}
                          data-testid={`edit-${p.hersteller}`}
                        >
                          Bearbeiten
                        </button>
                        <button
                          type="button"
                          className="admin-btn admin-btn--danger"
                          onClick={() => void remove(p.hersteller)}
                          data-testid={`del-${p.hersteller}`}
                        >
                          Löschen
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      ) : tab === "leads" ? (
        <div className="admin-body">
          {leads.length === 0 ? (
            <p className="admin-empty">Noch keine Leads eingegangen.</p>
          ) : (
            <ul className="admin-list">
              {leads.map((ld) => (
                <li
                  key={ld.id}
                  className="admin-lead"
                  data-testid={`lead-${ld.id}`}
                >
                  <div className="admin-lead-head">
                    <span className="admin-row-name">
                      {ld.firmenname || ld.partner_id}
                    </span>
                    <span className="admin-lead-meta">{ld.created_at}</span>
                    <span className="admin-row-badge">{ld.status}</span>
                  </div>
                  <div className="admin-lead-mail">{ld.lead_email}</div>
                  <details className="admin-lead-briefing">
                    <summary>{ld.briefing_title || "Briefing"}</summary>
                    <pre className="admin-lead-body">{ld.briefing_body}</pre>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="admin-body">
          <p className="admin-empty">
            Nutzer-Beiträge (ungeprüft). Prüfen, dann ggf. zu einer field_validated Fachkarte / einem
            Eval-Trap promoten — fließt nie automatisch in eine Empfehlung.
          </p>
          {contributions.length === 0 ? (
            <p className="admin-empty">Noch keine Beiträge eingegangen.</p>
          ) : (
            <ul className="admin-list">
              {contributions.map((c) => (
                <li
                  key={c.id}
                  className="admin-lead"
                  data-testid={`contrib-${c.id}`}
                >
                  <div className="admin-lead-head">
                    <span className="admin-row-name">Beitrag #{c.id}</span>
                    <span className="admin-row-badge">
                      {c.anonym ? "anonym" : c.subject_ref}
                    </span>
                    <span className="admin-lead-meta">{c.created_at}</span>
                    <span className="admin-row-badge">{c.status}</span>
                  </div>
                  <div className="contrib-outcome-row">
                    <strong>Ergebnis:</strong> {c.outcome || "—"}
                  </div>
                  <details className="admin-lead-briefing">
                    <summary>Situation + Empfehlung + Case-State</summary>
                    <pre className="admin-lead-body">
                      {c.situation}
                      {"\n\n"}
                      {c.recommendation}
                      {"\n\n"}
                      {c.case_state.map((f) => `${f.feld}: ${f.wert}`).join("\n")}
                    </pre>
                  </details>
                  <div className="admin-row-actions">
                    <button
                      type="button"
                      className="admin-btn"
                      data-testid={`contrib-reviewed-${c.id}`}
                      onClick={() => setContributionStatus(c.id, "reviewed")}
                    >
                      geprüft
                    </button>
                    <button
                      type="button"
                      className="admin-btn admin-btn--primary"
                      onClick={() => setContributionStatus(c.id, "promoted")}
                    >
                      promoten
                    </button>
                    <button
                      type="button"
                      className="admin-btn admin-btn--danger"
                      onClick={() => setContributionStatus(c.id, "rejected")}
                    >
                      verwerfen
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
