# Feature-Flag-Register (sealAI backend-v2)

Generiert am 2026-07-18 im Zuge der GATE-10-Forensik/Konsolidierung. Quelle der Wahrheit für
Prod-Werte: `.env.prod` auf `sealai-vps:~/sealai` (nicht dieses Dokument — bei Abweichung gewinnt
`.env.prod`, dieses Dokument dann nachziehen). Code-Defaults aus
`backend/sealai_v2/config/settings.py`. "Letzte Änderung" = letzter Commit, der die jeweilige
Flag-Zeile in `settings.py` geändert hat (per `git blame`), nicht notwendigerweise der Commit, der
den Prod-Wert gesetzt hat (siehe `.env.prod` selbst ist ungetrackt, keine Git-Historie vorhanden —
Details dazu im Routing-Audit-Report vom 2026-07-17).

**Bitte pflegen:** jede Änderung eines Prod-Flags aktualisiert die Spalte "Prod" + "Letzte Änderung"
im selben Commit/derselben Session.

## Live im Produktionspfad (Prod = True, mit Verhaltenswirkung)

| Flag | Code-Default | Prod | Letzte Änderung (settings.py) | Kontext |
|---|---|---|---|---|
| `execution_policy_enabled` | False | **True** | 2026-07-10, `4993987d` "Introduce deterministic production execution policy" | Deaktiviert `understand()` als Nebeneffekt (Audit-Befund 2026-07-17) — siehe Routing-Audit-Report |
| `route_optimization_enabled` | False | **True** | 2026-07-07, `474820b9` "conservative route classification foundation (Phase 2B)" (#182) | Bei aktivem `execution_policy_enabled` nur noch telemetry-only |
| `semantic_router_enabled` | False | **True** | 2026-07-15, `416bc765` "Add bounded semantic routing fallback" | Einziger LLM-Beteiligter am Routing |
| `route_prompt_families_enabled` | False | **True** | 2026-07-07, `440d61ac` "Phase 2D - controlled smalltalk_navigation prompt wiring" (#185) | Smalltalk-Compact-Prompt aktiv |
| `smalltalk_token_streaming_enabled` | False | **True** | 2026-07-09, `46bc2b97` "Phase 3A: smalltalk-only token streaming" (#202) | |
| `draft_token_streaming_enabled` | False | **True** | 2026-07-09, `bd891ba1` "Phase 3B: draft-token streaming for all L1 routes" (#206) | |
| `suppress_calc_for_non_kernel_routes_enabled` | False | **True** | 2026-07-09, `542fe660` "Gate calc prompt context by route relevance" | |
| `coverage_gate_enabled` | False | **True** | 2026-06-29, `6e11ef38` "INC-COVERAGE-GATE step 2" | |
| `response_contract_enabled` | False | **True** | 2026-06-29, `330228db` "INC-NARRATOR-CONTRACT Phase 1" | |
| `response_contract_general_guard_enabled` | False | **True** | 2026-07-02, `824c4cbe` "P0-B — widen output_guard" | |
| `pack_suggestion_enabled` | False | **True** | 2026-07-04, `a4069ca9` "L1 pack suggestion + free-text medium hint" (#165) | |
| `adaptive_interview_enabled` | False | **True** | 2026-07-13, `77f5b525` "add default-off RWDR interview shadow" | War als Schatten-only gedacht (Name!), Prod-Wert ist aber True — feeds `PipelineResult.next_question` live |
| `adaptive_interview_shadow_enabled` | False | **True** | 2026-07-13, `77f5b525` | |
| `adaptive_interview_pack_rwdr_enabled` | False | **True** | 2026-07-13, `77f5b525` | |
| `adaptive_interview_shadow_reporting_enabled` | False | **True** | 2026-07-14, `7c80df75` "add gated RWDR shadow reporting" | |
| `baseline_hardening_enabled` | False | **True** | 2026-06-30, `054d869c` "INC-BASELINE-HARDENING" | |
| `material_param_table_enabled` | False | **True** | 2026-06-30, `5e3a2bdd` "material-parameter table" | |
| `structured_answer_enabled` | False | **True** | 2026-07-10, `4993987d` | |
| `exact_answer_cache_enabled` | False | **True** | 2026-07-10, `4993987d` | |
| `knowledge_mode_enabled` | False | **True** | 2026-07-11, `f038271b` "Implement SSoT v2 trust contracts" | |
| `medium_intel_enabled` | False | **True** | 2026-06-26, `d2adb06e` "Medium Intelligence Phase 2" | |

## Inert in Prod (Prod = False, egal ob Code-Default False oder unset)

| Flag | Code-Default | Prod | Letzte Änderung | Kontext |
|---|---|---|---|---|
| `produktspec_enabled` | False | False (unset) | 2026-06-28, `c7d7d90e` "wire the Kandidaten-Spezifikation — flag OFF" | OD-3-Marker (2026-07-18) aktuell nicht live-auslösbar |
| `compatibility_matrix_enabled` | False | False (explizit) | 2026-07-11, `f038271b` | |
| `knowledge_review_enabled` | False | False | 2026-07-11, `f038271b` | |
| `case_decision_records_enabled` | False | False | 2026-07-11, `f038271b` | |
| `capability_profiles_enabled` | False | False | 2026-07-11, `f038271b` | |
| `manufacturer_fit_enabled` | False | False | 2026-07-11, `f038271b` | |
| `manufacturer_handoff_enabled` | False | False | 2026-07-11, `f038271b` | |
| `qdrant_hybrid_enabled` | False | False | 2026-07-03, `361aa26a` "hybrid retrieval — flag-gated, OFF" | |
| `qdrant_rerank_enabled` | False | False | 2026-07-03, `361aa26a` | |
| `legal_gate_enabled` | False | False (unset) | 2026-07-08, `ff22fc18` "Legal-by-Design Phase A+B" | |
| `risk_flag_prompt_enabled` | False | False (unset) | 2026-07-08, `67d6867b` "Legal-by-Design Phase C-F" | |
| `memory_context_enabled` | False | False (unset) | 2026-07-03, `4d10f93f` "Context Assembler" | |

## Kern-Pipeline, immer an (Code-Default True, keine Prod-Abweichung bekannt)

| Flag | Letzte Änderung | Kontext |
|---|---|---|
| `default_compliance_hint` | 2026-06-08, `6b7c7efc` (v2-m1) | |
| `default_safety_critical` | 2026-06-08, `6b7c7efc` | |
| `understand_enabled` | 2026-06-08, `6b7c7efc` | **Faktisch tot in Prod** trotz Default/Prod=True — siehe `execution_policy_enabled` |
| `verify_enabled` | 2026-06-08, `158ece2f` (v2-m2) | |
| `ground_enabled` | 2026-06-09, `44e981f6` (v2-m3) | |
| `compute_enabled` | 2026-06-09, `93fe8094` (v2-m4a) | |
| `memory_enabled` | 2026-06-09, `595881f9` (v2-m5) | |
| `distill_enabled` | 2026-06-09, `595881f9` | |
| `llm_telemetry_enabled` | 2026-07-07, `f8daf070` "safe LangSmith tracing" (#180) | |
| `metrics_enabled` | 2026-07-10, `4993987d` | |

---

**Bekannte, nicht in dieser Runde behobene Auffälligkeiten** (aus dem Routing-Audit + der GATE-10-Forensik):
- `understand_enabled=True` bei gleichzeitig `execution_policy_enabled=True` ist ein stiller Widerspruch — die Kombination bedeutet "an, aber wirkungslos". `pipeline.py` loggt das seit 2026-07-17 einmalig beim Start (`build_pipeline()`-Warnung).
- `adaptive_interview_shadow_enabled=True` benennt sich "shadow", ist aber gemeinsam mit `adaptive_interview_enabled=True` live (kein reiner Schattenmodus mehr) — Namensgebung ist irreführend, nicht Teil dieser Konsolidierung korrigiert.
- Zwei weitere Flags mit denselben "OFF (default)"-Kommentar-Mustern wie die im Routing-Audit korrigierten (`smalltalk_token_streaming_enabled`, `draft_token_streaming_enabled`) sind ebenfalls Prod=True, aber ihre Code-Kommentare wurden in dieser Runde NICHT korrigiert (separater Folge-Auftrag).
