import type { KandidatenSpec } from "../contracts";

const AXIS_LABEL: Record<string, string> = {
  lip: "Lippe",
  od: "Außendurchmesser",
  pressure: "Druck",
  shaft: "Welle",
  material: "Werkstoff",
};

function Section({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="medium-panel-section">
      <span className="medium-panel-section-title">{title}</span>
      <ul className="medium-panel-list">
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * PRODUKT-KANDIDAT panel (Kandidaten-Spezifikation, Produktspec v3.1) — a deterministic, STRUCTURALLY
 * CAPPED candidate space (Bauform/Werkstoff/DIN) derived from the case. It is NEVER a release: the
 * backend's structural gates keep `final_design_code` null (G3) + `freigegeben` false (G1) + a free-text
 * medium → candidate-set only (G2), so the panel can only ever show a candidate space. The "vorläufig"
 * badge is mandatory and the backend's lawyer-reviewed `geltungsrahmen` is rendered VERBATIM (the UI
 * language is owner-governed — this panel invents none of it). Render-only.
 */
export function KandidatenSpecPanel({ data }: { data: KandidatenSpec }) {
  // OD-3 (routing audit follow-up): a non-RWDR seal type is a structural scope boundary, not an
  // empty/absent panel -- render the backend's own geltungsrahmen honestly instead of a candidate
  // space the rule engine never computed for this seal type. Render-only, no candidate content.
  if ("status" in data) {
    return (
      <section
        className="medium-panel"
        data-testid="kandidaten-spec-panel-unavailable"
        aria-label="Produkt-Kandidat"
      >
        <header className="medium-panel-head">
          <span className="medium-panel-title">PRODUKT-KANDIDAT</span>
        </header>
        <p className="medium-panel-unsicher">{data.geltungsrahmen}</p>
      </section>
    );
  }
  const axisItems = data.axes
    .filter((a) => a.value || a.status === "open_verification" || a.status === "gate_blocked")
    .map((a) => {
      const label = AXIS_LABEL[a.name] ?? a.name;
      const val = a.value ?? "offen";
      return a.status && a.status !== "ok" ? `${label}: ${val} (${a.status})` : `${label}: ${val}`;
    });
  const offen = [...data.defer_gruende, ...data.open_verifications, ...data.offene_punkte];
  return (
    <section
      className="medium-panel"
      data-testid="kandidaten-spec-panel"
      aria-label="Produkt-Kandidat"
    >
      <header className="medium-panel-head">
        <span className="medium-panel-title">
          PRODUKT-KANDIDAT
          {data.din_candidate_label ? (
            <span className="medium-panel-kat"> · {data.din_candidate_label}</span>
          ) : null}
        </span>
        <span
          className="medium-panel-badge"
          title="Kandidaten-Spezifikation (Screening) — keine Freigabe; gegen DIN + Datenblatt/Hersteller verifizieren"
        >
          vorläufig
        </span>
      </header>
      <Section title="Werkstoff-Kandidaten" items={data.material_candidate_set} />
      <Section title="Sonderwerkstoff (Eskalation)" items={data.material.escalation} />
      <Section title="Achsen" items={axisItems} />
      <Section title="Offene Punkte / zu verifizieren" items={offen} />
      {data.geltungsrahmen ? (
        <p className="medium-panel-unsicher">{data.geltungsrahmen}</p>
      ) : null}
    </section>
  );
}
