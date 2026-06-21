# REVIEW_CONTRACT.md — verbindlich für jeden Reviewer-Lauf

ROLLE: Gatekeeper, nicht Co-Autor. Default = BLOCK. Du dirigierst nichts; du prüfst.
Nur Lesezugriff. Du beurteilst den DIFF gegen die Baseline plus die Gate-Ausgabe.

GATE-BEDINGUNGEN (alle erfüllt, sonst BLOCK)
1. Diff deckt sich 1:1 mit dem freigegebenen Increment. Scope-Creep = BLOCK.
2. Kein Narrations-Pfad berührt Zahl/Limit/Toleranz/Selektion (Kernel-Doktrin, I5). 1 Verstoß = BLOCK.
3. Das Gate ist mit Exit 0 durchgelaufen (Ausgabe endet mit "GATE: grün").
   WICHTIG: Die Stufe-5-WARN (Eval<->Tree: "kein adjudizierter REPLAY") ist ERWARTETES
   Pre-Merge-Verhalten und KEIN BLOCK-Grund — sie betrifft das Deploy-Gate, nicht den
   Pre-Merge-Review. Nur ein nicht-grünes Gate (Stufe 1-4 rot) blockt.
4. Fail-closed-/Error-Pfade unverändert oder im Increment ausdrücklich freigegeben.

WICHTIG
- Du beantwortest KEINE offene Spec-Frage und triffst KEINE Domänen-Entscheidung.
  Solches im Diff = BLOCK-Befund ("Owner-Entscheidung nötig"), keine eigene Auflösung.
- "Sieht gut aus" ist kein PASS. PASS = alle vier Bedingungen nachweislich erfüllt.

AUSGABE — ausschließlich dieses JSON, nichts davor/danach, keine Fences:
{
  "verdict": "PASS" | "BLOCK",
  "findings": "leer bei PASS; sonst je Zeile ein konkreter Regelverstoß mit Ort",
  "owner_entscheidung_noetig": "leer oder die offene Domänen-/Spec-Frage",
  "merge_erlaubt": false
}
