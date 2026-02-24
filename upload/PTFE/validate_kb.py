import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft7Validator

def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def _path_str(path_iter):
    parts = [str(p) for p in path_iter]
    return "/".join(parts) if parts else "<root>"

def _print_errors(label, validator, data):
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        print(f"  ✅ {label} is schema-compliant.")
        return True
    print(f"  ❌ {label} validation failed with {len(errors)} error(s):")
    for err in errors[:20]:
        print(f"     Path: {_path_str(err.path)}")
        print(f"     Message: {err.message}")
    if len(errors) > 20:
        print(f"     ... {len(errors)-20} more errors omitted")
    return False

def _integrity_checks(kb_data):
    ok = True
    print("\nRunning Integrity Checks (Deep-Links & Source Consistency)...")
    defined_sources = kb_data.get("sources", {})
    source_keys = set(defined_sources.keys())
    missing_sources = []
    rank_mismatch = []
    for card in kb_data.get("factcards", []):
        src_id = card.get("source")
        if src_id not in source_keys:
            missing_sources.append((card.get("id"), src_id))
            continue
        src_rank = defined_sources[src_id].get("rank")
        if src_rank != card.get("source_rank"):
            rank_mismatch.append((card.get("id"), src_id, card.get("source_rank"), src_rank))
    if missing_sources:
        ok = False
        for card_id, src in missing_sources:
            print(f"  ❌ Undefined source link: FactCard {card_id} -> {src}")
    else:
        print("  ✅ All FactCard source references resolve.")
    if rank_mismatch:
        ok = False
        for card_id, src, card_rank, source_rank in rank_mismatch[:20]:
            print(f"  ❌ Source rank mismatch: {card_id} uses {src} with source_rank={card_rank}, registry rank={source_rank}")
        if len(rank_mismatch) > 20:
            print(f"  ... {len(rank_mismatch)-20} more rank mismatches omitted")
    else:
        print("  ✅ FactCard source_rank matches source registry.")
    # Gate sanity: required_fields_schema unique fields
    dup_gate_fields = []
    for gate in kb_data.get("gates", []):
        fields = [x.get("field") for x in gate.get("required_fields_schema", []) if isinstance(x, dict)]
        dups = sorted({f for f in fields if fields.count(f) > 1})
        if dups:
            dup_gate_fields.append((gate.get("id"), dups))
    if dup_gate_fields:
        ok = False
        for gid, dups in dup_gate_fields:
            print(f"  ❌ Gate {gid} has duplicate required_fields_schema entries: {dups}")
    else:
        print("  ✅ Gate required_fields_schema entries are unique.")
    return ok

def main():
    parser = argparse.ArgumentParser(description="SealAI KB strict validator")
    parser.add_argument("--kb-schema", default="kb_schema_v1_3.json")
    parser.add_argument("--matrix-schema", default="compound_matrix.schema.json")
    parser.add_argument("--kb-data", default="SEALAI_KB_PTFE_factcards_gates_v1_3.json")
    parser.add_argument("--matrix-data", default="SEALAI_KB_PTFE_compound_matrix_v1_3.json")
    args = parser.parse_args()

    print("🚀 Starting SealAI Knowledge Base Validation (v1.3 Strict Mode)...\n")
    try:
        kb_schema = load_json(args.kb_schema)
        matrix_schema = load_json(args.matrix_schema)
        kb_data = load_json(args.kb_data)
        matrix_data = load_json(args.matrix_data)
    except Exception as e:
        print(f"❌ Error loading files: {e}")
        sys.exit(1)

    success = True
    kb_validator = Draft7Validator(kb_schema)
    matrix_validator = Draft7Validator(matrix_schema)

    print("Checking FactCards & Gates...")
    success &= _print_errors("FactCards & Gates JSON", kb_validator, kb_data)

    print("\nChecking Compound Decision Matrix...")
    success &= _print_errors("Compound Matrix JSON", matrix_validator, matrix_data)

    if success:
        success &= _integrity_checks(kb_data)

    if not success:
        print("\n💥 Validation Failed. Do NOT ingest into Vector DB.")
        sys.exit(1)
    print("\n🎉 All checks passed! Ready for RAG Ingestion.")

if __name__ == "__main__":
    main()
