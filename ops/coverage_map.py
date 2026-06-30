#!/usr/bin/env python3
"""SealBench Coverage-/Bias-Map (Prio 1) — blind-spot map over the eval anchor set + the Fachkarten
knowledge. Approximate keyword classification (German), enough to reveal skew, not a ground truth."""
import json, glob
from collections import Counter
from pathlib import Path

ROOT = Path("/home/thorsten/sealai")
EVAL_DIR = ROOT / "backend/sealai_v2/eval/seed_cases"
SEED = ROOT / "backend/sealai_v2/knowledge/fachkarten_seed.json"

MATERIALS = {
    "NBR": ["nbr", "nitril", "acrylnitril", "perbunan"],
    "HNBR": ["hnbr", "therban"],
    "FKM": ["fkm", "viton", "fluorkautschuk", "fluorelastomer"],
    "FFKM": ["ffkm", "kalrez", "perfluorelast"],
    "FEPM/Aflas": ["fepm", "aflas", "tfe/p", "tfe-p"],
    "EPDM": ["epdm", "ethylen-propylen"],
    "VMQ/Silikon": ["vmq", "silikon", "silicone"],
    "FVMQ": ["fvmq", "fluorsilikon"],
    "ACM": ["acm", "polyacrylat"],
    "CR/Neopren": ["chloropren", "neopren"],
    "PU/AU/TPU": ["polyurethan", "urethan", "tpu"],
    "PTFE": ["ptfe", "teflon"],
    "POM": ["pom", "polyoxymethylen", "acetal"],
    "PEEK": ["peek"],
    "SiC": ["sic", "siliziumkarbid", "siliciumcarbid"],
}
SEAL_TYPES = {
    "RWDR": ["rwdr", "radialwellendicht", "simmerring", "wellendichtring"],
    "O-Ring": ["o-ring", "oring", "o ring"],
    "Hydraulik": ["hydraulik", "stangendicht", "kolbendicht", "nutring", "abstreifer", "stützring", "führungsring"],
    "Gleitring": ["gleitring", "glrd", "mechanical seal"],
    "Flachdichtung": ["flachdicht"],
    "Membran": ["membran"],
    "Formdichtung": ["formdicht", "profildicht"],
}
MEDIA = {
    "Mineralöl/Schmierstoff": ["mineralöl", "mineraloel", "motoröl", "getriebeöl", "atf", "schmieröl", "hydrauliköl", "schmierfett"],
    "Dampf/Heißwasser/SIP": ["dampf", "heißwasser", "heisswasser", "sattdampf", " sip", "sterilisation"],
    "Wasser": ["wasser"],
    "Glykol/Kühlmittel": ["glykol", "kühlmittel", "kuehlmittel", "coolant", "frostschutz"],
    "Bremsflüssigkeit": ["bremsflüssig", "bremsfluessig", "dot 3", "dot 4", "dot 5"],
    "Kraftstoff": ["kraftstoff", "benzin", "diesel", "ethanol", "methanol", "biodiesel", "fame", "e85", "kerosin"],
    "Säure/Lauge": ["säure", "saeure", "lauge", "essigsäure", "schwefelsäure", "salzsäure", "salpeter"],
    "Hochdruckgas/RGD": ["hochdruckgas", "wasserstoff", "rgd", "sco2", " co2", "methan", "erdgas", "explosive decompression"],
    "Kältemittel": ["kältemittel", "kaeltemittel", "r134", "r1234", "r744", "r410", "r717", "refrigerant"],
    "Lebensmittel/Trinkwasser": ["lebensmittel", "trinkwasser", " food", "fda", "hygien", "pharma"],
    "Ozon/Witterung": ["ozon", "witterung"],
}
AXES = {1: "Faktische Korrektheit", 2: "Fallen-Vermeidung", 3: "Ehrliche Unsicherheit",
        4: "Begründungstiefe", 5: "Proaktivität", 6: "Grounding/Provenienz", 7: "Grenze gehalten"}


def classify(text, taxo):
    t = " " + text.lower() + " "
    return {fam for fam, kws in taxo.items() if any(kw in t for kw in kws)}


def load_cases(f):
    d = json.load(open(f))
    if isinstance(d, list):
        return d
    for key in ("cases", "seed_cases", "items"):
        if isinstance(d.get(key), list):
            return d[key]
    for v in d.values():
        if isinstance(v, list):
            return v
    return []


out = ["# sealingAI — Coverage / Bias-Map (Prio 1)\n",
       "_Blind-Flecken-Karte über Eval-Anker + Fachkarten-Wissen (MedGenAI-Gedanke: kontrollierte "
       "Gegenbeispiele statt nur Wissen). Keyword-Klassifikation, approximativ — zeigt Schieflage, keine Wahrheit._\n"]

# ============ A) EVAL ============
cases = []
for f in sorted(glob.glob(str(EVAL_DIR / "*.json"))):
    for c in load_cases(f):
        c["_file"] = Path(f).stem
        cases.append(c)

out.append(f"\n## A) Eval-Anker — {len(cases)} Fälle\n")
out.append("**Nach Dimension (seed-file):**")
for k, v in Counter(c["_file"] for c in cases).most_common():
    out.append(f"- `{k}`: {v}")
out.append("\n**Nach Fallklasse:**")
for k, v in Counter((c.get("klass", "?").split("(")[-1].rstrip(")")) for c in cases).most_common():
    out.append(f"- {k}: {v}")
ax = Counter(a for c in cases for a in c.get("primary_axes", []))
out.append("\n**Achsen-Abdeckung (Fälle je Achse):**")
for a in range(1, 8):
    out.append(f"- Achse {a} ({AXES[a]}): {ax.get(a, 0)}")
hg = Counter(g for c in cases for g in c.get("hard_gates", []))
out.append("\n**Schranken-Abdeckung (gate-relevante Fälle):**")
for k, v in hg.most_common():
    out.append(f"- `{k}`: {v}")


def case_text(c):
    parts = [str(c.get(k, "")) for k in ("input", "must_catch", "kontext", "klass", "notiz")]
    parts += c.get("tags", []) + c.get("must_contain", []) + list(c.get("must_avoid", []))
    return " ".join(parts)


emat = Counter(); eseal = Counter(); emed = Counter()
for c in cases:
    t = case_text(c)
    for x in classify(t, MATERIALS): emat[x] += 1
    for x in classify(t, SEAL_TYPES): eseal[x] += 1
    for x in classify(t, MEDIA): emed[x] += 1


def show(title, ctr, taxo):
    out.append(f"\n**{title}:**")
    seen = set()
    for k, v in ctr.most_common():
        out.append(f"- {k}: {v}"); seen.add(k)
    missing = [k for k in taxo if k not in seen]
    if missing:
        out.append(f"- **⚠ 0 Treffer:** {', '.join(missing)}")


show("Eval — Werkstoff-Erwähnungen", emat, MATERIALS)
show("Eval — Dichtungstyp-Erwähnungen", eseal, SEAL_TYPES)
show("Eval — Medien-Erwähnungen", emed, MEDIA)

# ============ B) FACHKARTEN ============
seed = json.load(open(SEED))
cards = seed["cards"]
rev = [c for c in cards if c.get("review_state") == "reviewed"]
prov = [c for c in cards if c.get("review_state") == "draft"]
claims = [(c, cl) for c in cards for cl in c.get("claims", [])]
out.append(f"\n## B) Fachkarten — {len(cards)} Karten ({len(rev)} reviewed + {len(prov)} provisional), {len(claims)} Claims\n")
out.append("**kind-Verteilung (Claims):**")
for k, v in Counter(cl.get("kind", "family_tendency") for _, cl in claims).most_common():
    out.append(f"- `{k}`: {v}")

fmat = Counter(); fseal = Counter(); fmed = Counter()
for c in cards:
    sc = c.get("scope", {})
    base = c.get("id", "") + " " + c.get("titel", "") + " "
    for x in classify(base + " ".join(sc.get("material", []) or []), MATERIALS): fmat[x] += 1
    for x in classify(base + " ".join(sc.get("application", []) or []), SEAL_TYPES): fseal[x] += 1
    for x in classify(base + " ".join(sc.get("medium", []) or []), MEDIA): fmed[x] += 1
show("Fachkarten — Werkstoff-Abdeckung (Karten)", fmat, MATERIALS)
show("Fachkarten — Dichtungstyp-Abdeckung (Karten)", fseal, SEAL_TYPES)
show("Fachkarten — Medien-Abdeckung (Karten)", fmed, MEDIA)

# ============ C) CROSS ============
out.append("\n## C) Kreuzbefund — Wissen vorhanden, aber im Eval 0 Fälle (gefährlichster blinder Fleck)\n")
for label, fk, ev, taxo in [("Werkstoff", fmat, emat, MATERIALS),
                            ("Dichtungstyp", fseal, eseal, SEAL_TYPES),
                            ("Medium", fmed, emed, MEDIA)]:
    gaps = [k for k in taxo if fk.get(k, 0) > 0 and ev.get(k, 0) == 0]
    weak = [k for k in taxo if fk.get(k, 0) > 0 and ev.get(k, 0) == 1]
    out.append(f"- **{label}:** Wissen-aber-0-Eval → {', '.join(gaps) or '—'}")
    if weak:
        out.append(f"  - nur 1 Eval-Fall (dünn): {', '.join(weak)}")

DST = ROOT / "sealbench-coverage-map.md"
DST.write_text("\n".join(out) + "\n", encoding="utf-8")
print("written:", DST)
print("EVAL cases:", len(cases))
print("  materials w/ 0 eval-cases:", [k for k in MATERIALS if emat.get(k, 0) == 0])
print("  seal-types w/ 0 eval-cases:", [k for k in SEAL_TYPES if eseal.get(k, 0) == 0])
print("  media w/ 0 eval-cases:", [k for k in MEDIA if emed.get(k, 0) == 0])
print("FACHKARTEN cards:", len(cards), "claims:", len(claims))
print("  fk material top:", fmat.most_common(5))
print("  cross gaps (knowledge but 0 eval): MAT", [k for k in MATERIALS if fmat.get(k,0)>0 and emat.get(k,0)==0],
      "| SEAL", [k for k in SEAL_TYPES if fseal.get(k,0)>0 and eseal.get(k,0)==0],
      "| MED", [k for k in MEDIA if fmed.get(k,0)>0 and emed.get(k,0)==0])
