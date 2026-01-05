# Audit: Jinja2-Integration in LangGraph v2

Datum: 2025-xx-xx
Scope: `backend/app/langgraph_v2` + `backend/app/prompts` (LangGraph v2 Prompt-Rendering)

## Überblick (Einsatz von Jinja2)
- Templates liegen zentral in `backend/app/prompts` und werden via `backend/app/langgraph_v2/utils/jinja.py` gerendert.
- Primäre Render-Pfade (v2):
  - Final Answer: `final_answer_router.j2` (Draft) + Wrapper-Templates `final_answer_smalltalk_v2.j2` / `final_answer_discovery_v2.j2` / `final_answer_recommendation_v2.j2` in `backend/app/langgraph_v2/sealai_graph_v2.py`.
  - Discovery/Confirm: `discovery_summarize.j2`, `confirm_gate.j2` in `backend/app/langgraph_v2/nodes/nodes_discovery.py`.
  - Flows: `material_comparison.j2`, `leakage_troubleshooting.j2`, `troubleshooting_explainer.j2` in `backend/app/langgraph_v2/nodes/nodes_flows.py`.
  - Response Router: `response_router.j2` in `backend/app/langgraph_v2/nodes/response_node.py`.
- Jinja2 Output an LLM:
  - `backend/app/langgraph_v2/sealai_graph_v2.py` erzeugt `SystemMessage(content=prompt_text)` aus Template-Output.
  - Weitere Nodes splitten System/User Prompt via `---` in Templates.

## Datenfluss (kurz)
- Intent/Goal Bestimmung: `backend/app/langgraph_v2/nodes/nodes_frontdoor.py` (Heuristik + LLM) setzt `intent.goal`.
- Template-Auswahl:
  - `_select_final_answer_template` in `backend/app/langgraph_v2/sealai_graph_v2.py` wählt anhand `goal` + `recommendation_go`.
- Kontext für Templates:
  - `build_final_answer_context` in `backend/app/langgraph_v2/nodes/nodes_flows.py` sammelt State (parameters, calc_results, choices, rag, troubleshooting etc.).
  - `_build_final_answer_template_context` in `backend/app/langgraph_v2/sealai_graph_v2.py` ergänzt coverage, draft, discovery summary, flags, plan, working_memory.
- Übergabe an LLM:
  - `_render_final_prompt_messages` erzeugt `SystemMessage` (Template + optional `senior_policy_de.j2`) und hängt User Messages an.

## Engine Setup Bewertung
- Status: Verbesserbar.
- Positiv: `StrictUndefined`, `trim_blocks`, `lstrip_blocks`, `autoescape=False` (bewusst), Environment-Caching via `@lru_cache`.
- Verbessern: keine explizite Template-Allowlist/Contract-Schicht; keine BytecodeCache; klare Trennung der finalen Prompt-Strategie fehlt.

## Findings
### P0 (kritisch)
- Keine P0-Findings identifiziert.

### P1 (hoch)
1) Template-Auswahl deckt Goals nicht vollständig ab
- Quelle: `backend/app/langgraph_v2/sealai_graph_v2.py`.
- Beobachtung: `_select_final_answer_template` behandelt nur `smalltalk` und `design_recommendation`. `explanation_or_comparison`, `troubleshooting_leakage` und `out_of_scope` landen im Discovery-Template.
- Risiko: Discovery-Wrapper stellt Rückfragen/Parameter-Logik in Flows, die eher Erklärung/Diagnose erwarten. Kann UX und Antwortstruktur verwässern.

2) Smalltalk-Prompt enthält schweren technischen Draft
- Quellen: `backend/app/prompts/final_answer_smalltalk_v2.j2`, `backend/app/prompts/final_answer_router.j2`, `backend/app/langgraph_v2/nodes/nodes_flows.py`.
- Beobachtung: Smalltalk-Template fordert stets Medium/Temperatur/Druck und hängt den technischen Draft aus `final_answer_router.j2` an. Das führt selbst bei Gruessen zu einer langen technischen System-Prompt-Struktur.
- Risiko: Smalltalk wirkt beratend/"zu schwer", Micro-Smalltalk fehlt; erhöht Tokenkosten und erschwert kurze Antworten.

3) Template-Contract-Tests wirken veraltet und spiegeln aktuelle Templates nicht
- Quelle: `backend/tests/contract/test_prompt_render_contract.py`.
- Beobachtung: Assertions erwarten Marker, die in `final_answer_router.j2`/`final_answer_discovery_v2.j2` nicht existieren (z. B. "## Allgemeines Fachwissen", "Fragen zur Vervollständigung").
- Risiko: Tests sind kein verlässlicher Guardrail; Drift zwischen Tests und Templates bleibt unerkannt.

### P2 (mittel)
1) Mehrere Final-Answer-Strategien parallel
- Quellen: `backend/app/langgraph_v2/nodes/nodes_validation.py` (`final_answer_v2.j2`) vs. `backend/app/langgraph_v2/sealai_graph_v2.py` (router + wrapper).
- Risiko: Single Source of Truth fehlt; Änderungen an einer Strategie können inkonsistente Ergebnisse erzeugen.

2) Fehlendes explizites Template-Context-Schema
- Quellen: `backend/app/langgraph_v2/utils/jinja.py`, `backend/app/langgraph_v2/sealai_graph_v2.py`.
- Beobachtung: Kontext wird als `dict` gebaut; kein Pydantic/TypedDict für Jinja-Variablen. StrictUndefined hilft zwar, aber Contract ist implizit.
- Risiko: schwer nachvollziehbar, welche Keys pro Template garantiert sind; erhöht Wartungskosten.

3) Nodes mit Jinja-Rendering, aber offenbar nicht im v2-Graph genutzt
- Quelle: `backend/app/langgraph_v2/nodes/nodes_discovery.py` und `backend/app/langgraph_v2/nodes/nodes_validation.py`.
- Risiko: tote/alte Render-Pfade können unentdeckt driften oder Fehler enthalten (z. B. fehlende Imports), ohne Testabdeckung.

## Empfehlungen (konkret)
- P0:
  - Keine.
- P1:
  - Template-Auswahl erweitern: eigene Wrapper-Templates fuer `explanation_or_comparison`, `troubleshooting_leakage`, `out_of_scope` oder explizit an `final_answer_router.j2` delegieren.
  - Smalltalk entschlacken: Micro-smalltalk-Branch einbauen; `draft` nur optional oder in gekuerzter Form fuer Smalltalk verwenden.
  - Contract-Tests aktualisieren, damit sie aktuelle Template-Abschnitte/Marker validieren (inkl. Smalltalk/Discovery/Recommendation).
- P2:
  - Einen zentralen Template-Context-Typ (Pydantic/TypedDict) definieren, um Required/Optional Keys pro Template klar zu machen.
  - Final-Answer-Strategie konsolidieren (entweder `final_answer_v2.j2` oder router+wrapper als einzige Quelle).
  - Unbenutzte Jinja-Render-Pfade markieren/entfernen oder explizit testen, damit Drift sichtbar bleibt.

## Verifikationskommandos
- Inventar Templates:
  - `find backend -type f \( -name "*.j2" -o -name "*.jinja" -o -name "*.jinja2" \) | sort`
  - `rg -n "\\{\\{|\\{%|macro |include\\(|import\\(|extends\\(" backend -S --glob="*.j2"`
- Render-Callsites (v2):
  - `rg -n "render_template\\(" backend/app/langgraph_v2 -S`
  - `rg -n "final_answer_.*\\.j2|\\.j2" backend/app/langgraph_v2 -S`
- Template-Auswahl-Logik:
  - `rg -n "_select_final_answer_template|final_prompt_selected|selected_template_name" backend/app/langgraph_v2 -S`
- Drift in Contract-Tests pruefen:
  - `rg -n "final_answer_router.j2|final_answer_discovery_v2.j2" backend/tests/contract/test_prompt_render_contract.py -S`

## Betroffene Dateien (Auszug)
- `backend/app/langgraph_v2/utils/jinja.py`
- `backend/app/langgraph_v2/sealai_graph_v2.py`
- `backend/app/langgraph_v2/nodes/nodes_flows.py`
- `backend/app/langgraph_v2/nodes/nodes_frontdoor.py`
- `backend/app/langgraph_v2/nodes/nodes_discovery.py`
- `backend/app/langgraph_v2/nodes/nodes_validation.py`
- `backend/app/prompts/final_answer_router.j2`
- `backend/app/prompts/final_answer_smalltalk_v2.j2`
- `backend/app/prompts/final_answer_discovery_v2.j2`
- `backend/app/prompts/final_answer_recommendation_v2.j2`
- `backend/app/prompts/confirm_gate.j2`
- `backend/app/prompts/discovery_summarize.j2`
- `backend/app/prompts/material_comparison.j2`
- `backend/app/prompts/leakage_troubleshooting.j2`
- `backend/app/prompts/troubleshooting_explainer.j2`
- `backend/tests/contract/test_prompt_render_contract.py`

## Next Steps (ohne Code-Aenderungen)
- Review-Entscheidungen: Template-Auswahl erweitern vs. neue Wrapper; Smalltalk-Design vereinfachen.
- Tests neu ausrichten: Contract-Tests aktualisieren und auf aktuelle Template-Abschnitte pinnen.
- Optionaler Smoke-Render lokal (ohne LLM) mit minimalem Kontext, um StrictUndefined-Faelle aufzudecken.
