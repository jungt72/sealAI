#!/usr/bin/env python3
"""Promote the 38 challenge-verified draft Fachkarten into the seed as PROVISIONAL.

review_state stays "draft" on every promoted card/claim → they are served by the retriever's
`provisional` channel (advisory/pre-check), NEVER as authoritative grounding_facts. The circularity
guard does not bite draft claims, so "no LLM erdet LLM" is preserved and the 9 owner/trap-grounded
reviewed cards are untouched. Manufacturer release remains the product's final gate.
"""
import json, glob, shutil
from pathlib import Path

SEED = Path("/home/thorsten/sealai/backend/sealai_v2/knowledge/fachkarten_seed.json")
DRAFTS = "/home/thorsten/sealai/ops/fachkarten_drafts"

seed = json.load(open(SEED))
seed_ids = {c["id"] for c in seed["cards"]}
drafts = [json.load(open(f)) for f in sorted(glob.glob(f"{DRAFTS}/FK-DRAFT-*.json"))]

assert all(d["id"] not in seed_ids for d in drafts), "id collision with existing seed"
assert all(d["review_state"] == "draft" for d in drafts), "a promoted card is not review_state=draft"

shutil.copy(SEED, str(SEED) + ".bak-pre-promote-20260628")

seed["cards"] = seed["cards"] + drafts
seed["version"] = seed.get("version", "") + "+prov-promote-20260628"
seed["source"] = (
    seed.get("source", "")
    + " | + 38 challenge-verified PROVISIONAL Fachkarten (4-round GPT-5.5 challenge -> GO; "
    "review_state=draft -> served as provisional/pre-check; Herstellerfreigabe = final gate)"
)

SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("promoted", len(drafts), "draft cards; seed now has", len(seed["cards"]), "cards")
