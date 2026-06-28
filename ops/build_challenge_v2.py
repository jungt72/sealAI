#!/usr/bin/env python3
"""Build the RE-CHALLENGE doc (post-audit, kind-tagged) from the draft queue ON THE VPS."""
import json, glob, os
from collections import Counter

DRAFTS = "/home/thorsten/sealai/ops/fachkarten_drafts"
DST = "/home/thorsten/sealingai-fachkarten-rechallenge3.md"

KIND_LABEL = {
    "family_tendency": "FAMILIEN-TENDENZ (qualitativ)",
    "example_value": "BEISPIELWERT (Compound/Prüfung, KEINE Familiengrenze)",
    "system_dependent": "SYSTEMABHÄNGIG (Geometrie/Spalt/Härte/PV/Paarung)",
    "safety_nogo": "SAFETY-NO-GO (harte Ausschlussregel)",
    "definition": "DEFINITION (Klassifikation / Was-ist-X / Norm-Kurzzeichen)",
    "regulatory_status": "REGULATORIK-STATUS (Norm/Verordnung; Konformität grade-/chargenspezifisch)",
    "qualification_required": "QUALIFIKATION ERFORDERLICH (Prüf-/Freigabepflicht, kein Hartausschluss)",
    "safety_caution": "SAFETY-CAUTION (bedingter Versagensmodus, weicher als No-Go)",
}

out = []
out.append("# sealingAI — Fachkarten 4. CHALLENGE / Promote-Verifikation (vorläufig, NICHT autoritativ)\n")
out.append(
    "Dein 3.-Runden-Audit ergab **0 ❌ / 0 🔴**, Verdikt GO-MIT-ÄNDERUNG, mit **19 ⚠️-Feinschliff-Punkten** "
    "und der Aussage: nach deren Korrektur sei die Basis promote-fähig als autoritative Vorprüfungs-SSoT. "
    "**Genau diese 19 Punkte sind jetzt umgesetzt** (chirurgisch, 17 Karten, sonst byte-identisch): u.a. "
    "HNBR/FKM-Heißwasser/POM-238°C entschärft, NBR/VMQ/CR/EPDM/FKM-Sub/FKM-Viton/FEPM Mischclaims gesplittet "
    "(Definition vs Beispielwert, Systemwert vs Qualifikation), Regulatorik/Qualifikation/Säure-Differenzierung korrekt getaggt. "
    "Diese Runde = **Verifikation**: prüfe pro Claim ZWEI Dinge (Fachtext + `kind`) und vergib je [✅]/[⚠️]/[❌]/[🔴]. "
    "Achte besonders auf die 17 geänderten Karten — sind die 19 Punkte sauber behoben und KEINE Regression entstanden?\n"
)
out.append(
    "1. **Fachliche Korrektheit des Textes** — Fehler, fehlende Differenzierung, fragwürdige Zahlen/Grenzen, unbelegte Aussagen.\n"
    "2. **Korrektheit des `kind`-Tags** gegen die 8er-Taxonomie — passt der epistemische Typ? "
    "Ist `safety_nogo` wirklich ein harter Ausschluss (kein Positivstandard/keine Qualifikationsregel)? "
    "Sind Norm-/Definitions-/Qualifikationsaussagen korrekt als `regulatory_status`/`definition`/`qualification_required` geführt?\n"
)
out.append(
    "**`kind`-Taxonomie (8):** `family_tendency` = qualitative Familientendenz · `example_value` = Compound-/Prüf-/Datenblattwert, NIE Familiengrenze · "
    "`system_dependent` = Geometrie/Spalt/Härte/Stützring/Medium/PV/Paarung/Bauart · `safety_nogo` = harter Sicherheits-Ausschluss · "
    "`safety_caution` = bedingter Versagensmodus (weicher) · `qualification_required` = Prüf-/Freigabepflicht · "
    "`regulatory_status` = Norm/Verordnung, Konformität grade-/chargenspezifisch · `definition` = Klassifikation/Was-ist-X.\n"
)
out.append(
    "Alle Claims `review_state=draft`. Die finale Werkstoff-/Auslegungs-/Konformitätsfreigabe liegt IMMER beim Hersteller. "
    "**Promote-Frage:** Ist die Basis jetzt als autoritative Single Source of Truth promote-fähig — oder welche Claims blocken noch? "
    "Themen: Werkstoff×Medium-Verträglichkeit, RWDR/Hydraulik/Gleitring-Konstruktion, Medien-Klassifikation, Regulatorik, Versagensbilder.\n"
)

fk = sorted(glob.glob(f"{DRAFTS}/FK-DRAFT-*.json"))
tot = 0
kinds = Counter()
out.append(f"\n## A) Fachkarten ({len(fk)})\n")
for f in fk:
    d = json.load(open(f))
    cl = d.get("claims", [])
    tot += len(cl)
    sc = d.get("scope", {})
    out.append(f"### {d.get('id')} — {d.get('titel', '')}")
    out.append(
        f"*scope:* material={sc.get('material', [])[:8]} · "
        f"medium={sc.get('medium', [])[:8]} · property={sc.get('property', [])[:6]} · "
        f"application={sc.get('application', [])[:6]}"
    )
    for i, c in enumerate(cl, 1):
        k = c.get("kind", "family_tendency")
        kinds[k] += 1
        src = ", ".join(c.get("sources", []) or c.get("provenance", []))
        out.append(f"- **C{i:02d}** `[{KIND_LABEL.get(k, k)}]`  \n  {c['text']}  \n  _Quelle: {src}_")
    out.append("")

nm = 0
vm = glob.glob(f"{DRAFTS}/versagensmodi_drafts.json")
if vm:
    d = json.load(open(vm[0]))
    modes = d.get("modes", [])
    nm = len(modes)
    out.append(f"\n## B) Versagensmodi / Diagnose ({nm}) — generische Schadensbilder (Symptom→Ursache→Fix)\n")
    for m in modes:
        arche = ", ".join(m.get("betrifft_archetypen", []))
        out.append(
            f"### {m['id']}\n- **Symptom:** {m.get('symptom', '')}\n"
            f"- **Ursache:** {m.get('ursache', '')}\n- **Fix:** {m.get('fix', '')}\n"
            f"- **betrifft:** {arche}\n"
            f"  _Quelle: {', '.join(m.get('sources', []) or m.get('provenance', []))}_\n"
        )

out.append("\n---\n## Zusammenfassung der zu prüfenden Menge")
out.append(f"- **{len(fk)} Fachkarten**, **{tot} Claims**, **{nm} Versagensmodi**")
out.append(f"- kind-Verteilung: " + " · ".join(f"`{k}`={v}" for k, v in kinds.most_common()))

open(DST, "w").write("\n".join(out))
print(f"geschrieben: {DST}  ({os.path.getsize(DST) // 1024} KB)")
print(f"  {len(fk)} Fachkarten ({tot} Claims) + {nm} Versagensmodi")
print(f"  kind-Verteilung: {dict(kinds)}")
