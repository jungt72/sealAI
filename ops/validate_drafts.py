#!/usr/bin/env python3
"""Full-tree validation of the Fachkarten draft queue before re-bundling for the external challenge."""
import json, glob, sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, "/home/thorsten/sealai/backend")
from sealai_v2.knowledge.fachkarten import load_fachkarten

DRAFTS = "/home/thorsten/sealai/ops/fachkarten_drafts"
files = sorted(glob.glob(f"{DRAFTS}/FK-DRAFT-*.json"))

raw_cards, missing_kind, nondraft, bad_json = [], [], [], []
for f in files:
    try:
        d = json.load(open(f))
    except Exception as e:
        bad_json.append((Path(f).name, repr(e)))
        continue
    raw_cards.append(d)
    if d.get("review_state") != "draft":
        nondraft.append((d.get("id"), "CARD", d.get("review_state")))
    for i, c in enumerate(d.get("claims", [])):
        if "kind" not in c:
            missing_kind.append((d.get("id"), i, (c.get("text", "")[:40])))
        if c.get("review_state") != "draft":
            nondraft.append((d.get("id"), f"claim{i}", c.get("review_state")))

print(f"FK-DRAFT files: {len(files)}")
print(f"bad JSON: {len(bad_json)}")
for b in bad_json:
    print("   ", b)

combined = Path("/tmp/_all_drafts.json")
combined.write_text(json.dumps({"version": "drafts", "cards": raw_cards}))
try:
    cat = load_fachkarten(combined)
    print(f"load_fachkarten(ALL): OK  -> {len(cat.cards)} cards")
    kinds, claims = Counter(), 0
    per_card = []
    for c in cat.cards:
        ks = Counter(cl.kind for cl in c.claims)
        per_card.append((c.id, len(c.claims), dict(ks)))
        for cl in c.claims:
            kinds[cl.kind] += 1
            claims += 1
    print(f"total claims: {claims}")
    print(f"kind-distribution: {dict(kinds)}")
    print("\nper-card (id, #claims, kinds):")
    for pid, n, ks in per_card:
        print(f"  {n:>3}  {pid}  {ks}")
except Exception as e:
    print(f"load_fachkarten(ALL): FAIL -> {e!r}")

print(f"\nclaims missing explicit 'kind' key: {len(missing_kind)}")
for m in missing_kind[:30]:
    print("   ", m)
print(f"non-draft review_state leaks: {len(nondraft)}")
for n in nondraft[:30]:
    print("   ", n)

vm = json.load(open(f"{DRAFTS}/versagensmodi_drafts.json"))
modes = vm.get("modes", [])
print(f"\nversagensmodi modes: {len(modes)}")
vm_nd = [m.get("id") for m in modes if m.get("review_state") != "draft"]
print(f"versagensmodi non-draft: {vm_nd}")
print(f"versagensmodi ids: {[m.get('id') for m in modes]}")
