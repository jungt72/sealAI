/* TEMPORARY screenshot harness (pilot-ui HALT 1) — mounts the REAL Shell/ChatPane with fixture
 * data so the three review states render without auth/backend. Views via ?view=fresh|chips.
 * Not imported by the app; safe to delete. */
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";

import { ChatPane } from "./components/ChatPane";
import { Shell } from "./components/Shell";
import type { ChatResponse, ConversationMemory } from "./contracts";
import { FALLBACK_FRAMING } from "./framing";
import { FramingContext } from "./framing-context";
import "katex/dist/katex.min.css";
import "./styles/fonts.css";
import "./styles/theme.css";
import "./styles/app.css";

const view = new URLSearchParams(location.search).get("view") ?? "fresh";

const FIXTURE_ANSWER: ChatResponse = {
  answer: [
    "Bei **50 mm** Wellendurchmesser und **3.000 U/min** ergibt sich eine Umfangsgeschwindigkeit von",
    "",
    "$$v = \\frac{\\pi \\cdot d_1 \\cdot n}{60000} = 7{,}85\\ \\mathrm{m/s}$$",
    "",
    "Für Hydrauliköl HLP 46 bei 80 °C kommen als Orientierung in Frage:",
    "",
    "- **NBR** — Richtwert `~10 m/s`: liegt nahe am Richtwert, Herstellerangabe prüfen",
    "- **FKM** — Richtwert `~25–35 m/s`: Reserve bei Temperaturspitzen",
    "",
    "Die finale Werkstoffwahl bleibt eine Herstellerentscheidung auf Datenblattbasis.",
  ].join("\n"),
  model: "fixture",
  grounded: false,
  intent: "material_orientation",
  citations: [
    { text: "Richtwert Umfangsgeschwindigkeit NBR ~10 m/s (RWDR, drucklos)", sources: ["Parker O-Ring Handbook"] },
    { text: "FKM Temperatureinsatzbereich bis ~200 °C", sources: ["ISO 3601-2"] },
  ],
};

const FACTS: ConversationMemory = {
  case_state: [
    { feld: "wellendurchmesser", wert: "50 mm", provenance: "user-form" },
    { feld: "drehzahl", wert: "3000 U/min", provenance: "user-form" },
    { feld: "medium", wert: "Hydrauliköl HLP 46", provenance: "distilled-from-conversation" },
    { feld: "temperatur", wert: "80 °C", provenance: "user-form" },
  ],
  history: [],
};

function Harness() {
  const [memory, setMemory] = useState<ConversationMemory>(
    view === "fresh" ? { case_state: [], history: [] } : FACTS,
  );
  return (
    <FramingContext.Provider value={FALLBACK_FRAMING}>
      <Shell onLogout={() => {}} onNewQuestion={() => location.reload()}>
        <ChatPane
          onSend={async () => {
            await new Promise((r) => setTimeout(r, 150));
            return FIXTURE_ANSWER;
          }}
          error={null}
          memory={memory}
          onEditFact={() => {}}
          onForgetFact={(feld) =>
            setMemory((m) => ({ ...m, case_state: m.case_state.filter((f) => f.feld !== feld) }))
          }
          onForgetAll={() => setMemory({ case_state: [], history: [] })}
          onSubmitParams={async (items) => {
            setMemory((m) => ({
              ...m,
              case_state: [
                ...m.case_state.filter((f) => !items.some((it) => it.feld === f.feld)),
                ...items.map((it) => ({
                  feld: it.feld,
                  wert: it.wert,
                  provenance: "user-form",
                })),
              ],
            }));
            return {
              uebernommen: items.map((it) => ({ feld: it.feld, label: it.label, wert: it.wert })),
              rueckfragen: [],
              computed: [],
              not_computed: [],
              notes: [],
              clarifications: [],
            };
          }}
          onMakeBriefing={() => {}}
          canBriefing={false}
          briefing={null}
          // review fixture: a kernel result so the cockpit's Berechnungen panel renders (clean on ?view=fresh)
          compute={
            view === "fresh"
              ? null
              : {
                  computed: [
                    {
                      calc_id: "umfangsgeschwindigkeit",
                      name: "v_m_s",
                      value: 7.85,
                      unit: "m/s",
                      formula: "v = π·d1·n/60000",
                      parent_fields: ["wellendurchmesser", "drehzahl"],
                      input_origins: [],
                      provenance: "kernel_computed",
                    },
                  ],
                  not_computed: [],
                  notes: [],
                }
          }
        />
      </Shell>
    </FramingContext.Provider>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
);
