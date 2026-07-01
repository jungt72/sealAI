# sealingAI V2 — Systemüberblick & Workflow

> Stand: 2026-07-01 · Basis: `feat/v22-coverage-gate` (Kern deckungsgleich auf `main`) · Backend `backend/sealai_v2`
> Dieses Dokument beschreibt **präzise, was das System tut**, **welche Schichten es gibt** und **was nach der Eingabe im Chat technisch passiert**. Jede Aussage ist aus dem Code abgeleitet; die Dateipfade stehen jeweils dabei.

---

## 1. Was das System ist — in einem Satz

sealingAI V2 ist ein **KI-Beratungssystem für Dichtungstechnik**, das Fachauskünfte gibt, konkrete Dichtungsfälle prüft, deterministisch rechnet und jede Antwort gegen geprüftes Wissen verifiziert — nach **einem** Leitprinzip:

> **Der deterministische Kern besitzt die Zahlen und Urteile. Das Sprachmodell formuliert nur.**

Daraus folgt der Anspruch „keine Halluzinationen": Ein Wert oder ein Urteil erscheint in der Antwort **nur**, wenn er aus Code (Berechnung) oder aus einer geprüften Wissensquelle (Fachkarte, Verträglichkeitsmatrix) stammt — nicht, weil das Modell ihn „weiß".

---

## 2. Die vier Vertrauens-Schichten (Trust-Spine L1–L4)

Das ganze System ist um eine vierstufige Vertrauenskette gebaut. Jede fachliche Behauptung durchläuft sie:

| Schicht | Rolle | Umsetzung im Code |
|--------|-------|-------------------|
| **L1 — Narrator / Renderer** | Formuliert die Antwort. Erzählt, erfindet nicht. | `core/l1_generator.py` + `prompts/system_l1.jinja`; Modell **gpt-5.1** (prod) |
| **L2 — Grounding** | Liefert geprüfte Fakten, gegen die L1 erdet. | `pipeline/stages.py::ground` → Fachkarten-RAG (Qdrant) + §4 Verträglichkeitsmatrix |
| **L3 — Verifier** | Unabhängiger Kritiker + **deterministische** Hart-Schranken. Korrigiert/hedged. | `core/l3_verifier.py`; Kritiker-Modell **Mistral Small**, Schranken sind reiner Code |
| **L4 — Hersteller** | Die **finale** Werkstoff-/Bauteil-Freigabe. Bleibt beim Menschen. | Nie automatisiert; alle Draft-Aussagen sind „vorläufig — gegen Hersteller verifizieren" |

Kernidee: **L1 darf nie die letzte Instanz sein.** Zwischen Modell-Antwort und Nutzer sitzen L2 (erden) und L3 (prüfen), und die endgültige technische Freigabe (L4) verlässt das System bewusst.

---

## 3. Die technischen Schichten (Architektur)

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONTEND    frontend-v2 (Vite-SPA, /dashboard)                       │
│              Chat-Eingabe → POST /api/v2/chat  oder  /chat/stream(SSE)│
└───────────────┬──────────────────────────────────────────────────────┘
                │  Bearer-Token (Keycloak JWT)
┌───────────────▼──────────────────────────────────────────────────────┐
│  AUTH        security/auth.py  — tenant & session NUR aus dem Token   │
│              (P0, fail-closed: keine Auth-Config → 503, kein Serving) │
└───────────────┬──────────────────────────────────────────────────────┘
┌───────────────▼──────────────────────────────────────────────────────┐
│  API         api/routes/chat.py → pipeline.run(...)                   │
│              api/serializers.py::chat_response → JSON-Antwort         │
└───────────────┬──────────────────────────────────────────────────────┘
┌───────────────▼──────────────────────────────────────────────────────┐
│  PIPELINE    pipeline/pipeline.py  — die dünne Orchestrierung         │
│              verstehen → grounden → rechnen → antworten →             │
│              verifizieren → (rendern)                                 │
└───┬───────────────┬───────────────┬───────────────┬──────────────────┘
    │               │               │               │
┌───▼────┐   ┌──────▼──────┐  ┌─────▼──────┐  ┌─────▼───────┐
│ WISSEN │   │  MEMORY     │  │  CALC      │  │  LLM        │
│ (L2)   │   │  4 Schichten│  │  (Kern)    │  │  Provider   │
└────────┘   └─────────────┘  └────────────┘  └─────────────┘
```

### 3.1 Frontend
- **`frontend-v2`** (Vite-SPA, ausgeliefert unter `/dashboard`). Das eigentliche Beratungs-UI.
- (`frontend/` ist nur die Marketing-Seite — nicht das Dashboard.)
- Sendet die Nutzernachricht an **`POST /api/v2/chat`** (eine JSON-Antwort) oder **`POST /api/v2/chat/stream`** (Server-Sent-Events: Fortschritts-Frames während der Verarbeitung, dann **eine** vollständige, bereits geprüfte Antwort).

### 3.2 Auth (P0-Keystone)
- `api/deps.py::current_identity` leitet `tenant_id` + `session_id` **ausschließlich aus dem verifizierten Keycloak-Token** ab — nie aus Request-Body oder Header. Ohne konfigurierte Auth: **503** (fail-closed).

### 3.3 API-Routen
- `api/routes/chat.py` — dünne Projektion über `pipeline.run`. `/chat` und `/chat/stream` teilen sich denselben Body, dieselbe Auth, dieselben Flags; nur der Transport unterscheidet sich.
- `api/serializers.py::chat_response` — verpackt das `PipelineResult` in JSON: `answer` + alle strukturierten Panels (siehe §5).

### 3.4 Pipeline (das Herz)
- `pipeline/pipeline.py` (`Pipeline.run`, ~940 Zeilen) orchestriert den ganzen Turn. Die einzelnen Schritte liegen als reine Funktionen in `pipeline/stages.py`.

### 3.5 Wissen (L2)
Alles **reviewtes** Wissen, kein freies Modellwissen:
| Quelle | Datei | Zweck |
|--------|-------|-------|
| **Fachkarten** | `knowledge/retrieval.py`, Qdrant-Collection `sealai_v2_fachkarten` | Werkstoff-/Anwendungswissen (RAG) |
| **Verträglichkeitsmatrix (§4)** | `knowledge/matrix.py` | Material × Medium → verträglich / bedingt / unverträglich |
| **Versagensmodi** | `knowledge/versagensmodi.py` | Symptom → Ursache → Fix (Modus D) |
| **Archetypen** | `knowledge/archetypes.py` | Maschinen-Profile: Interview-Fragen + blinde Flecken |
| **Hersteller-Partner** | `knowledge/hersteller_partner.py` | Bezahlter Partner-Pool, Ranking **nur** nach Eignung (Modus F) |
| **Material-Parameter** | `knowledge/material_parameters_seed.json` | Geerdete Kennwerte-Tabelle (Temperatur, Shore …) |
| **Trap-Katalog** | `knowledge/traps.py` | Bekannte Denkfallen für den L3-Kritiker |

### 3.6 Memory (4 Schichten)
`memory/store.py`, `memory/distiller.py`:
- **L1 Working-Window** — die letzten Turns (Gesprächsverlauf).
- **L2 Case-State** — strukturierte, destillierte Fall-Fakten (Material, Medium, Maße …).
- **L3 History** — vollständige Turn-Historie.
- **L4 Cross-Session Durable** — dauerhafte Fakten über Sessions hinweg, unter eigenem, ehrlichem Rahmen („aus früheren Gesprächen — bei Bedarf bestätigen"). Fließt **nie** in die deterministische Berechnung.

### 3.7 LLM-Provider (per-Rolle-Routing)
`llm/factory.py`, konfiguriert in `.env.prod`. Jede Rolle kann ein anderes Modell/Provider haben:
| Rolle | Modell (prod) | Aufgabe |
|-------|---------------|---------|
| **L1** | OpenAI **gpt-5.1** | die Antwort formulieren |
| **Verifier (L3)** | **mistral-small-2603** | unabhängige Kritik |
| **Helper** | **mistral-small-2603** | Intent-Klassifikation, Medium-Recherche, Distiller |
| **Judge** | OpenAI **gpt-4.1-mini** | Eval-Bewertung (nur offline) |
| **Embeddings** | OpenAI **text-embedding-3-small** | Fachkarten-RAG (RAM-sicher, kein lokales Modell) |

### 3.8 Observability
`obs/tracing.py` — `@traceable`/`wrap_openai`: **jeder Turn = ein Trace** im LangSmith-Projekt `sealai-production`. Fail-open, reine Beobachtung, verändert die Antwort nie.

---

## 4. Der Ablauf nach der Eingabe — Routing & Technik

### 4.1 Die wichtigste Aussage zum „Routing"

**Es gibt kein hartes Intent-Routing.** Das System verzweigt **nicht** in „Wissensfrage-Zweig" vs. „Fallarbeit-Zweig".

- Der `understand`-Schritt (`stages.py::understand`, Helper-LLM) erzeugt eine **weiche Annotation**: `wissensfrage | fallarbeit | faktfrage | gespraech | unklar` (+ optional ein `archetype`). Er läuft **nebenläufig** zur Antwort und **steuert nichts** — im Code steht wörtlich: *„Dies ist eine WEICHE Annotation; sie steuert nichts."* Sie erscheint nur als `intent`-Feld in der API-Antwort.

- **Stattdessen aktiviert sich jede deterministische Operation selbst** anhand **struktureller Signale** aus Frage + Fall. Kein Signal → die Operation gibt `None` zurück → die Antwort ist **byte-identisch**, als gäbe es sie nicht. Das ist „self-gating" statt „routing":

| Operation | Modus | Feuert **nur** wenn … | Datei |
|-----------|-------|------------------------|-------|
| **Gegencheck** | E | Fall trägt **Material UND Medium** | `core/gegencheck.py` |
| **Diagnose** | D | ein **Symptom** erkannt wird | `stages.py::diagnose` |
| **Decode** | G | eine **Bezeichnung mit Maßen** vorliegt | `stages.py::decode` |
| **Alternativen / Hersteller** | F | ein **Hersteller-/Alternativ-Keyword** fällt | `stages.py::alternativen` |
| **Compute** | (Kern) | Parameter deterministisch **bindbar** sind | `stages.py::compute` |
| **Material-Parameter-Tabelle** | (Flag) | ein bekannter **Werkstoff** genannt wird | `knowledge/material_parameters.py` |

Die Basis-Beratung (Modus C — die eigentliche fachliche Empfehlung/Erklärung) **ist** die L1-Antwort selbst; die Operationen oben **reichern sie an**.

**Mit anderen Worten:** Das System routet nicht in Zweige — es baut **einen** Antwortpfad und hängt genau die geerdeten Bausteine an, die der Fall strukturell hergibt.

### 4.2 Der technische Ablauf, Schritt für Schritt

Nachdem die Nachricht (authentifiziert) in `pipeline.run` ankommt:

1. **Tenant-Gate** (`require_tenant`) — fail-closed, ohne Mandanten kein Turn.
2. **flush_memory** — Ordering-Guard: ein im Hintergrund laufendes „Merken" des Vor-Turns muss landen, bevor dieser Turn erinnert.
3. **recall** (`stages.recall`) — Memory-View laden: Window (L1) + Case-State (L2) + relevante Durable-Fakten (L4).
4. **Case bauen** (`Case.from_case_state`) — die getippte Fallstruktur (Material, Medium, Maße …) aus dem Case-State.
5. **understand** (nebenläufig gestartet) — weiche Intent-/Archetyp-Annotation (steuert nichts, §4.1).
6. **Deterministische Kerne** (rein, synchron, self-gating, §4.1): `gegencheck`, `diagnose`, `decode`, `alternativen`, `kandidaten_spec`. Jeder liefert ein strukturiertes Urteil **oder** `None`.
7. **ground** (`stages.ground`, L2) — reviewte **Fachkarten** via Qdrant-RAG **plus** die relevanten **§4-Matrix-Zellen**. Keine Quelle → Antwort wird „vorläufig".
8. **compute** (`stages.compute`, Kern) — die deterministische **Berechnungs-Kaskade** über die gebundenen Parameter (+ qualitative Fachkarten-Flags). **Fail-closed**: bei fehlenden/mehrdeutigen Eingaben lieber „nicht berechenbar" mit Grund als eine irreführende Zahl. Nie LLM-geschätzt.
9. **understand awaited** → `archetype_context` (Interview-Fragen + blinde Flecken des erkannten Profils, rein beratend).
10. **coverage / contract** (aus **derselben** geerdeten Evidenz) — deterministische Deckungs-/Antwort-Verträge (in prod: Contract **an**, Coverage-Gate default aus).
11. **material_params** (Flag an) — die geerdete Kennwerte-Tabelle für genannte Werkstoffe.
12. **generate** (`l1_generator.generate`, **L1**) — das Modell formuliert die Antwort **aus** geerdeten Fakten + Berechnung + Kontext. Mit aktivem Contract läuft L1 im **Renderer-Modus** (es rendert einen vorbestimmten Antwort-Vertrag, statt frei zu erzählen).
13. **output_guard** (Flag + Contract) — claim-level, **fail-closed**: findet die Antwort eine ungedeckte Behauptung → **BLOCK** → **einmal** neu generieren mit Korrekturnote, dann erneut prüfen (protokolliert unter GOVERNANCE).
14. **verify** (`stages.verify`, **L3**) — unabhängiger Kritiker gegen Trap-Katalog + Fachkarten + Berechnung + Matrix. Bei reviewter Hart-Schranken-Verletzung oder Matrix-Widerspruch → **regenerate-once oder Hedge**. Ist L3 abgeschaltet (Notfall-Killswitch), läuft trotzdem der **deterministische** `run_parametric_guard` (die Zahlen-Schranke überlebt ohne Modell).
15. **_exfil_guard** — deterministische **Exfiltrations-Schranke**: würde die Antwort den System-Prompt oder einen KB-Dump wörtlich ausgeben, wird sie durch eine zahl-freie Absage ersetzt, bevor sie ausliefert.
16. **cite** — Stub (Provenienz wird vom Serializer / L1-Selbstmarkierung getragen).
17. **remember** (nach der Antwort) — Turn protokollieren + destillierte **genannte** Fakten in den Case-State schreiben. Läuft (mit Distiller) **im Hintergrund**, ordering-guarded — kann den beobachteten Turn nie beeinflussen.
18. **PipelineResult → `chat_response`** — JSON: `answer` + alle Panels (§5) → SPA rendert die strukturierten Urteile **deterministisch** (nicht aus L1-Prosa).

Jeder Schritt ist **getimt** (`TurnTimer`) und sendet im Streaming-Modus einen Fortschritts-Frame (nur Stage-Schlüssel, nie Inhalt/PII).

---

## 5. Was der Nutzer zurückbekommt

`chat_response` (`api/serializers.py`) liefert neben `answer` diese **strukturierten, deterministischen** Felder — jedes vom Kern, wörtlich durchgereicht, **nicht** aus L1-Text geparst:

- `intent` — die weiche Annotation (nur Info)
- `citations` — die geerdeten Fachkarten/Matrix-Belege
- `computed` / `not_computed` — berechnete Werte + ehrliche „nicht berechenbar"-Gründe
- `gegencheck` — Modus-E-Verdikt (disqualifiziert-oder-nicht, nie ein affirmatives „passt")
- `coverage` / `contract` / `guard` — Deckungsstatus, Antwort-Vertrag, Guard-Urteil
- `diagnose` (D) / `decode` (G) / `alternativen` (F) — die weiteren Operationen
- `medium_intelligence` — recherchierte Medium-Eigenschaften (vorläufig)
- `kandidaten_spec` — Bauform/Werkstoff/DIN-Vorschlag (Flag, vorläufig)

---

## 6. Was das bedeutet (die Doktrin in Konsequenzen)

1. **Zahlen kommen aus Code, Urteile aus geprüftem Wissen — nie aus dem Modell.** Berechnung = `compute` (deterministische Kaskade). Verträglichkeit = §4-Matrix. Kennwerte = geerdeter Seed. Das LLM ist **Erzähler**, nicht Quelle.
2. **Jede Behauptung ist entweder geerdet oder markiert.** Ungedecktes wird als „Allgemeinwissen" / „vorläufig" gekennzeichnet — oder vom Guard/L3 blockiert.
3. **Fail-closed als Grundhaltung.** Im Zweifel „nicht berechenbar" / Hedge / Absage statt einer plausiblen falschen Zahl. Die deterministischen Schranken (parametric, exfil, matrix) halten sogar **ohne** das LLM.
4. **Intent steuert nichts.** Sicherheit hängt nie an einer LLM-Klassifikation; die Operationen aktivieren sich über harte strukturelle Signale.
5. **Die finale Freigabe bleibt beim Menschen (L4).** Werkstoff-/Bauteil-Empfehlungen sind Anfragebasis, nicht Freigabe — „gegen Datenblatt / Hersteller verifizieren".
6. **Feature-Flags + byte-identische Inertheit.** Neue Fähigkeiten werden hinter Flags gebaut; ist ein Flag aus, ist die Antwort byte-identisch zu vorher. Das macht Deploys risikoarm und den Eval-Vergleich sauber.

---

## 7. Live-Zustand (Produktion, Stand 2026-07-01)

**Immer aktiv (Kernschichten, kein Flag):** understand (weich), ground (L2/Qdrant-RAG), compute, verify (L3), memory sowie die self-gating Kerne gegencheck / diagnose / decode / alternativen.

**Per Flag AN (`.env.prod`):**
- `RESPONSE_CONTRACT_ENABLED=true` — Narrator-Contract + output_guard aktiv
- `MATERIAL_PARAM_TABLE_ENABLED=true` — Kennwerte-Tabelle
- `MEDIUM_INTEL_ENABLED=true` — Medium-Recherche + MEDIUM-Panel
- `RETRIEVER_BACKEND=qdrant` + OpenAI-Embeddings — Fachkarten-RAG

**Per Flag AUS (Default):** `coverage_gate`, `produktspec` (Owner-Governance-Gate), `baseline_hardening`.

**Modelle:** L1 = gpt-5.1 · Verifier + Helper = mistral-small-2603 · Judge = gpt-4.1-mini · Embeddings = text-embedding-3-small.

---

## 8. Landkarte der zentralen Dateien

| Thema | Datei |
|-------|-------|
| Orchestrierung (der Turn) | `backend/sealai_v2/pipeline/pipeline.py` |
| Stages (verstehen/grounden/…) | `backend/sealai_v2/pipeline/stages.py` |
| L1-Generator + Prompt | `backend/sealai_v2/core/l1_generator.py`, `prompts/system_l1.jinja` |
| L3-Verifier + Schranken | `backend/sealai_v2/core/l3_verifier.py` |
| Gegencheck-Kern (Modus E) | `backend/sealai_v2/core/gegencheck.py` |
| Verträglichkeitsmatrix (§4) | `backend/sealai_v2/knowledge/matrix.py` |
| Fachkarten-RAG (L2) | `backend/sealai_v2/knowledge/retrieval.py`, `knowledge/qdrant_retrieval.py` |
| Berechnung (Kern) | `backend/sealai_v2/core/calc/` |
| Memory (4 Schichten) | `backend/sealai_v2/memory/` |
| Contract + Guard | `backend/sealai_v2/core/response_contract.py`, `core/output_guard.py` |
| API + Serializer | `backend/sealai_v2/api/routes/chat.py`, `api/serializers.py` |
| Konfiguration / Flags | `backend/sealai_v2/config/settings.py`, `.env.prod` |
```
