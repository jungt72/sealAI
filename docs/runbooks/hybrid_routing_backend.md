# Hybrid Routing Backend Runbook

## Zweck
Dieser Runbook beschreibt Konfiguration, Betrieb, Telemetrie und Tests des Hybrid-Routing-Backends (Supervisor + Button-Overrides + Fallback). Gilt ab PR #2.

## Feature Flags & Konfiguration
- `HYBRID_ROUTING_ENABLED` (ENV, default `0`): aktiviert den erweiterten Supervisor-Flow. Flag `0` ⇒ Legacy-Verhalten.
- `ROUTING_CONF_PATH` (ENV, default `config/routing.yml`): YAML mit `confidence_threshold`, `min_delta`, `intents[..].synonyms`, `buttons.label/tooltip`.
- YAML wird beim ersten Zugriff geladen (Cache). Änderungen → Service-Restart oder `load_routing_config.cache_clear()` im Admin-Skript.

## Button-Overrides
- WebSocket-Payload `{ intent: "werkstoff", source: "ui_button", confidence: 0.95 }` → deterministische Route.
- Supervisor-Node `button_dispatch` persistiert `last_agent` (Redis) und emittiert Telemetrie `ui_button_selected`.
- Unterstützte Keys: `werkstoff`, `profil`, `validierung` (`BUTTON_INTENTS`).

## Semantic Router
- Node `semantic_router` nutzt `find_intent_from_text()` (Regex + Fuzzy Match). Score ≥ τ (`confidence_threshold`) ⇒ Delegation an Consult-Flow.
- Score < τ oder geringe Differenz zum Platz 2 → `fallback_node` mit Klärungsfrage + Vorschlagsbuttons.

## State & Memory
- Kurzzeit-Historie weiterhin über Redis (`chat:stm:{thread}:messages`).
- `last_agent` persistiert separat (`chat:stm:{thread}:last_agent`) und wird nur für Vorschlagsbuttons genutzt (keine Auto-Routen).

## Telemetrie
Alle Events JSON-logged via `[telemetry]`:
1. `ui_button_selected` → deterministische Pfade.
2. `routing_decision` → Ergebnis der semantischen Bewertung (inkl. `alternatives`, `reason`).
3. `routing_fallback` → ausgelöster Fallback inkl. `suggestions`.
Pflichtfelder: `thread_id`, `user_id`, `source`, `intent_candidate`, `intent_final`, `confidence`, `next_node`, `fallback`, `duration_ms`, `feature_flag_state`.

## Tests
```
$ export HYBRID_ROUTING_ENABLED=1
$ pytest backend/tests/test_hybrid_routing.py
```
- `test_find_intent_from_text_scores_above_threshold_for_synonym`
- `test_find_intent_from_text_flags_fallback_for_unknown_request`
- `test_extract_button_payload_defaults_to_ui_button`
- `test_last_agent_suggestion_uses_config_labels`

## Manuelle Checks
1. Flag off (`HYBRID_ROUTING_ENABLED=0`): WebSocket-Flow wie zuvor (Supervisor → Consult/Chitchat), keine Telemetrie-Einträge.
2. Flag on + Button → Sofort-Konnektor, Telemetrie `ui_button_selected` sichtbar, Consult-Nodes laufen.
3. Flag on + unsicherer Freitext → Fallback-Nachricht + UI-Event `routing_suggestions`.

## Rollback
- Sofort: Flag `HYBRID_ROUTING_ENABLED=0` (kein Code-Rollback erforderlich).
- Falls YAML fehlerhaft: entfernen oder korrigieren (`config/routing.yml`). Fehlende Datei ⇒ Defaults aus Code greifen.
- Redis-Ausfall: `set_last_agent`/`get_last_agent` degradieren lautlos; Buttons funktionieren weiter.

