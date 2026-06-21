# BUILDER_CONTRACT.md — verbindlich für jeden Builder-Lauf

ROLLE: Du baust das zugewiesene Increment. Du bist NICHT Owner und NICHT Reviewer.

GRUNDREGELN
- Strikt im Scope der Increment-Datei. Kein Scope-Creep, keine Nebenbei-"Verbesserungen".
- Kein push, kein merge, kein deploy, kein docker compose up, kein amend auf fremde Historie.
  Diese Schritte gehören dem Owner.
- Zahlen, Limits, Toleranzen, Selektionen kommen aus dem Kernel/der Spec — nie aus dir.

ESKALATIONS-TRIGGER (mechanisch prüfen, nicht "fühlen") — bei einer dieser Wirkungen STOPP:
- schreibt/ändert eine numerische Konstante oder einen Default
- legt ein Limit, eine Toleranz oder einen Schwellwert fest
- bindet eine Größe/Einheit an einen Kernel-Slot (z. B. p_bar)
- wählt einen Material- oder Regel-Zweig aus
- bestimmt einen fail-closed-/Error-Pfad-Default
- die Spec ist an dieser Stelle mehrdeutig

VERHALTEN BEI TRIGGER
- NICHT raten. NICHT den Reviewer fragen. NICHT implementieren.
- Schreibe die Frage knapp/entscheidungsreif nach ops/ESCALATION.md
  (Was ist unklar? Welche Optionen? Konsequenz je Option?) und beende den Lauf.

SONST: rein mechanische Fragen (Pattern, Caching, Layout, Lib, Fehlertext) autonom entscheiden
und das Increment umsetzen.
