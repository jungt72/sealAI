import { useCallback, useEffect, useState } from "react";

import type { ApiClient } from "../api/client";
import type { AdminPartner, SelfLead, SelfPartnerUpdate } from "../contracts";

const csv = (xs: string[]) => xs.join(", ");
const parseCsv = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

function toDraft(p: AdminPartner): SelfPartnerUpdate {
  return {
    firmenname: p.firmenname,
    lead_email: p.lead_email,
    website: p.website,
    beschreibung: p.beschreibung,
    standort: p.standort,
    kontakt_oeffentlich: p.kontakt_oeffentlich,
    werkstoffe: p.werkstoffe,
    bauformen: p.bauformen,
    groessen: p.groessen,
    zertifikate: p.zertifikate,
  };
}

/**
 * Manufacturer SELF-SERVICE dashboard — a partner manages their OWN profile + reads their OWN leads.
 * Scoped SERVER-SIDE to the token's hersteller_id (no id is ever sent — the manufacturer cannot reach
 * another partner). aktiv/plan are READ-ONLY here (owner-controlled paid membership); the manufacturer
 * edits only their content + capabilities. If the owner has not onboarded them yet, GET 404s → a clear
 * "kein Profil" message rather than an empty form.
 */
export function PartnerSelfPane({
  api,
  onClose,
}: {
  api: ApiClient;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"profil" | "leads">("profil");
  const [profile, setProfile] = useState<AdminPartner | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [draft, setDraft] = useState<SelfPartnerUpdate | null>(null);
  const [leads, setLeads] = useState<SelfLead[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api
      .partnerSelfGet()
      .then((p) => {
        setProfile(p);
        setDraft(toDraft(p));
        setNotFound(false);
      })
      .catch((e: { status?: number } | null) => {
        if (e?.status === 404) setNotFound(true);
        else setError("Laden fehlgeschlagen.");
      });
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (tab === "leads")
      api
        .partnerSelfLeads()
        .then((r) => setLeads(r.leads))
        .catch(() => setError("Laden fehlgeschlagen."));
  }, [tab, api]);

  const patch = (p: Partial<SelfPartnerUpdate>) => {
    setDraft((d) => (d ? { ...d, ...p } : d));
    setSaved(false);
  };

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.partnerSelfUpdate(draft);
      setProfile(updated);
      setDraft(toDraft(updated));
      setSaved(true);
    } catch {
      setError("Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  function field(
    label: string,
    value: string,
    onChange: (v: string) => void,
    testid?: string,
  ) {
    return (
      <label className="admin-field">
        <span>{label}</span>
        <input
          value={value}
          data-testid={testid}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  }

  return (
    <section
      className="admin-pane"
      data-testid="partner-self-pane"
      aria-label="Mein Hersteller-Profil"
    >
      <header className="admin-head">
        <h1 className="admin-title">Mein Hersteller-Profil</h1>
        <button
          type="button"
          className="admin-close"
          onClick={onClose}
          data-testid="self-close"
        >
          Zurück zum Chat
        </button>
      </header>

      <div className="admin-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "profil"}
          className={`admin-tab${tab === "profil" ? " admin-tab--active" : ""}`}
          onClick={() => setTab("profil")}
          data-testid="self-tab-profil"
        >
          Mein Profil
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "leads"}
          className={`admin-tab${tab === "leads" ? " admin-tab--active" : ""}`}
          onClick={() => setTab("leads")}
          data-testid="self-tab-leads"
        >
          Meine Leads
        </button>
      </div>

      {error ? (
        <p className="admin-error" data-testid="self-error">
          {error}
        </p>
      ) : null}

      {tab === "profil" ? (
        notFound ? (
          <p className="admin-empty" data-testid="self-no-profile">
            Für Ihr Konto ist noch kein Hersteller-Profil angelegt. Bitte wenden Sie sich an den
            Betreiber, um als Partner aufgenommen zu werden.
          </p>
        ) : draft && profile ? (
          <div className="admin-form" data-testid="self-form">
            <div className="self-membership" data-testid="self-membership">
              <span
                className={`admin-row-badge${profile.aktiv ? " admin-row-badge--on" : ""}`}
              >
                {profile.aktiv ? "aktiv gelistet" : "nicht gelistet"}
              </span>
              {profile.plan ? (
                <span className="admin-row-plan">Plan: {profile.plan}</span>
              ) : null}
              <span className="self-membership-note">
                Mitgliedschaft &amp; Plan werden vom Betreiber verwaltet.
              </span>
            </div>

            {field("Firmenname", draft.firmenname, (v) => patch({ firmenname: v }), "sf-name")}
            {field(
              "Lead-E-Mail (Ihr Posteingang für Anfragen)",
              draft.lead_email,
              (v) => patch({ lead_email: v }),
              "sf-email",
            )}
            {field("Website", draft.website, (v) => patch({ website: v }))}
            <label className="admin-field">
              <span>Beschreibung</span>
              <textarea
                value={draft.beschreibung}
                rows={3}
                onChange={(e) => patch({ beschreibung: e.target.value })}
              />
            </label>
            {field("Standort", draft.standort, (v) => patch({ standort: v }))}
            {field("Öffentlicher Kontakt", draft.kontakt_oeffentlich, (v) =>
              patch({ kontakt_oeffentlich: v }),
            )}
            {field(
              "Werkstoffe (kommagetrennt)",
              csv(draft.werkstoffe),
              (v) => patch({ werkstoffe: parseCsv(v) }),
              "sf-werkstoffe",
            )}
            {field("Bauformen (kommagetrennt)", csv(draft.bauformen), (v) =>
              patch({ bauformen: parseCsv(v) }),
            )}
            {field("Größen", draft.groessen, (v) => patch({ groessen: v }))}
            {field("Zertifikate (kommagetrennt)", csv(draft.zertifikate), (v) =>
              patch({ zertifikate: parseCsv(v) }),
            )}
            <div className="admin-form-actions">
              <button
                type="button"
                className="admin-btn admin-btn--primary"
                onClick={() => void save()}
                disabled={busy}
                data-testid="self-save"
              >
                Speichern
              </button>
              {saved ? (
                <span className="self-saved" data-testid="self-saved">
                  ✓ Gespeichert
                </span>
              ) : null}
            </div>
          </div>
        ) : (
          <p className="admin-empty">Profil wird geladen…</p>
        )
      ) : (
        <div className="admin-body">
          {leads.length === 0 ? (
            <p className="admin-empty">Noch keine Anfragen eingegangen.</p>
          ) : (
            <ul className="admin-list">
              {leads.map((ld) => (
                <li
                  key={ld.id}
                  className="admin-lead"
                  data-testid={`self-lead-${ld.id}`}
                >
                  <div className="admin-lead-head">
                    <span className="admin-row-name">Anfrage #{ld.id}</span>
                    <span className="admin-lead-meta">{ld.created_at}</span>
                    <span className="admin-row-badge">{ld.status}</span>
                  </div>
                  <details className="admin-lead-briefing">
                    <summary>{ld.briefing_title || "Briefing"}</summary>
                    <pre className="admin-lead-body">{ld.briefing_body}</pre>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
