# sealingAI V2 — Invarianten-Charter
Stand: 2026-06-22 | Quelle: IST-Audit (scratch/IST_V2.1_audit.md)
Ersetzt die informelle, nie verankerte "I1-I9"-Erzaehlung durch den verifizierten,
code-belegten Kanon. I5 = bestehender Code-Anker; uebrige Nummerierung HIER etabliert
(kein rekonstruiertes Original). Format: Aussage | Enforcer(file:line) | [STATUS].

I1  Kernel ist die einzige Zahl-/Selektions-Quelle; Binding fail-closed.
    core/calc/binding.py:238-294 (deklarierte Tabelle, normalize->exact-synonym, Konflikt-Erkennung) | [ENFORCED, Laufzeit, kein AST-Test]
I2  Kernel-computed Wert ist nie Eingabe (keine Rueckkopplung).
    core/calc/binding.py:252 | core/calc/derived.py:55,76-90 (Voll-Recompute) | [ENFORCED]
I3  Import-Grenze sealai_v2 <-> app, beidseitig.
    backend/tests/architecture/test_v2_import_boundary.py:54,71 | [ENFORCED]
I4  Fremdtext = Daten, nie Grounding (Untrusted-Quarantaene).
    backend/sealai_v2/tests/test_untrusted_quarantine.py:46-67 | [ENFORCED]
I5  Kein Narrations-Pfad erfindet eine Engineering-Zahl.  [Code-Anker: REVIEW_CONTRACT.md:8]
    test_i5_narration_no_numbers.py (statisch) + core/calc/leak_detector.py:145 (Laufzeit, in L3+Eval) | [PARTIAL: statisch float-only/5-Dateien/kein-Jinja]
I6  L3 korrigiert nur aus reviewed-Eintraegen; erfindet keine Wahrheit.
    core/l3_verifier.py (sonst deterministischer Hedge) | [ENFORCED, Code, kein AST-Test]
I7  Zirkularitaets-Guard auf Wissens-Stores (kein LLM erdet LLM).
    knowledge/calc_registry.py:138-153 | knowledge/matrix.py:93-98 | [ENFORCED]
I8  Tenant-Scope P0, server-seitig fail-closed.
    security/tenant.py via require_tenant @ pipeline.py:126, matrix.py:146 | [ENFORCED]
I9  Durable L4-Memory speist nie den Calc-Binder.
    pipeline.py:153-156 | [ENFORCED]

A0  (Meta) Eval-REPLAY / 8 Schranken halten 1.000 durch jedes Increment.
    Eval ist live-LLM + owner-adjudiziert (API-Key .env-denied) -> strukturell NICHT CI-automatisierbar;
    die menschliche Adjudikation IST die Doktrin. Bindung HART am Deploy: ops/v2_deploy_gate.py
    refuset Deploy (exit 2) ohne adjudizierten, tree-hash-gebundenen Run mit schranken_quota_final==1.0.
    | [ENFORCED AT DEPLOY (hart); gate.sh Stufe 5 pre-merge = WARN by design, relay-kompatibel]

## Benannte Durchsetzungs-Luecken (Haertungs-Reihenfolge)
1. I5-Scanner scope-begrenzt (Jinja + Integers ungescannt).
2. Architektur-Glob mischt V1: test_ssot_guardrails.py:13, test_single_writer_invariant.py:1,
   test_core_seal_type_branching.py:1 erzwingen den V1-app-Baum, nicht sealai_v2.
(A0 nicht hier: am Deploy hart gebunden, pre-merge-WARN ist by design. Kein Build —
 nur vor Deploy einen frischen adjudizierten Eval-Run auf HEAD erzeugen.)

## Trust-Spine heute
Getragen von: fail-closed-Design des Kernels (I1, I2) + die ENFORCED-Invarianten + manuelles
Owner-Gating fuer A0. NICHT von einem maschinell erzwungenen Voll-Kanon.
