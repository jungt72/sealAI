"""Adversarial tests for the canonical production-RC evidence contract."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
IMAGE = "sha256:" + "1" * 64
IMAGE_CONFIG = "sha256:" + "7" * 64
SERVED_TREE = "2" * 64
MIGRATIONS = "3" * 64
POSTGRES = "4" * 64
QDRANT = "5" * 64
AUTHORITY = "sha256:" + "6" * 64
COLLECTION = "sealai_rc_knowledge_test"
SOURCE_GIT_SHA = "8" * 40


def _module():
    spec = importlib.util.spec_from_file_location(
        "v2_rc_evidence_test", REPO / "ops" / "v2_rc_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profile(**overrides):
    behavior = {
        "ground_enabled": True,
        "knowledge_authority_epoch": AUTHORITY,
        "qdrant_collection": COLLECTION,
        "retriever_backend": "qdrant",
    }
    behavior.update(overrides)
    return {"schema_version": 1, "behavior": behavior}


def _document(module, *, runtime_profile=None):
    return module.build_document(
        candidate_image_digest=IMAGE,
        candidate_image_config_digest=IMAGE_CONFIG,
        served_tree_sha256=SERVED_TREE,
        database_migration_sha256=MIGRATIONS,
        authority_epoch=AUTHORITY,
        postgres_database="sealai_v2_rc",
        postgres_snapshot_sha256=POSTGRES,
        qdrant_collection=COLLECTION,
        qdrant_snapshot_sha256=QDRANT,
        runtime_profile=runtime_profile or _profile(),
        source_git_sha=SOURCE_GIT_SHA,
    )


def _canonical(value) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def test_canonical_round_trip_binds_every_required_identity(tmp_path):
    module = _module()
    document = _document(module)
    raw = module.canonical_evidence_bytes(document)
    path = tmp_path / "rc.json"
    path.write_bytes(raw)
    expected_hash = hashlib.sha256(raw).hexdigest()

    loaded, actual_hash = module.load_evidence(path, expected_sha256=expected_hash)
    binding = module.manifest_binding(loaded, file_sha256=actual_hash)

    assert binding == {
        "schema_version": 1,
        "evidence_type": "sealai_v2_production_rc",
        "evidence_sha256": expected_hash,
        "payload_sha256": document["payload_sha256"],
        "candidate_image_config_digest": IMAGE_CONFIG,
        "candidate_image_digest": IMAGE,
        "candidate_image_digest_source": "gate10_backend_registry_manifest",
        "served_tree_sha256": SERVED_TREE,
        "database_migration_sha256": MIGRATIONS,
        "authority_epoch": AUTHORITY,
        "runtime_profile_sha256": document["payload"]["runtime_profile_sha256"],
        "retriever_backend": "qdrant",
        "retriever_fallback_allowed": False,
        "postgres_database": "sealai_v2_rc",
        "postgres_snapshot_sha256": POSTGRES,
        "qdrant_collection": COLLECTION,
        "qdrant_authentication": "api_key",
        "qdrant_snapshot_sha256": QDRANT,
        "source_git_sha": SOURCE_GIT_SHA,
    }


def test_payload_tamper_is_rejected(tmp_path):
    module = _module()
    document = _document(module)
    document["payload"]["isolation"]["postgres"]["snapshot_sha256"] = "a" * 64
    path = tmp_path / "tampered.json"
    path.write_bytes(_canonical(document))

    with pytest.raises(module.EvidenceError, match="payload hash"):
        module.load_evidence(path)


def test_rehashed_tamper_still_fails_external_gate10_file_hash(tmp_path):
    module = _module()
    original = _document(module)
    original_raw = module.canonical_evidence_bytes(original)
    approved_hash = hashlib.sha256(original_raw).hexdigest()

    tampered = copy.deepcopy(original)
    tampered["payload"]["isolation"]["qdrant"]["snapshot_sha256"] = "a" * 64
    payload_raw = _canonical(tampered["payload"])[0:-1]
    tampered["payload_sha256"] = hashlib.sha256(payload_raw).hexdigest()
    path = tmp_path / "rehashed.json"
    path.write_bytes(_canonical(tampered))

    # Self-consistent, but no longer the exact file approved by Gate 10.
    module.load_evidence(path)
    with pytest.raises(module.EvidenceError, match="externally approved hash"):
        module.load_evidence(path, expected_sha256=approved_hash)


@pytest.mark.parametrize(
    "profile",
    [
        _profile(retriever_backend="in_process"),
        _profile(ground_enabled=False),
        _profile(knowledge_authority_epoch="sha256:" + "a" * 64),
        _profile(qdrant_collection="sealai_rc_other"),
    ],
)
def test_runtime_profile_must_prove_exact_qdrant_authority_and_collection(profile):
    module = _module()
    with pytest.raises(module.EvidenceError):
        _document(module, runtime_profile=profile)


def test_semantically_equal_noncanonical_or_duplicate_json_is_rejected(tmp_path):
    module = _module()
    document = _document(module)
    pretty = tmp_path / "pretty.json"
    pretty.write_text(json.dumps(document, indent=2), encoding="utf-8")
    with pytest.raises(module.EvidenceError, match="canonical byte form"):
        module.load_evidence(pretty)

    duplicate = tmp_path / "duplicate.json"
    raw = module.canonical_evidence_bytes(document).decode("ascii")
    duplicate.write_text(
        raw.replace('{"evidence_type":', '{"schema_version":1,"evidence_type":', 1),
        encoding="ascii",
    )
    with pytest.raises(module.EvidenceError, match="duplicate key"):
        module.load_evidence(duplicate)


def test_symlink_evidence_is_rejected(tmp_path):
    module = _module()
    target = tmp_path / "target.json"
    target.write_bytes(module.canonical_evidence_bytes(_document(module)))
    link = tmp_path / "link.json"
    link.symlink_to(target)

    with pytest.raises(module.EvidenceError, match="unavailable"):
        module.load_evidence(link)


def test_boolean_schema_version_is_not_accepted():
    module = _module()
    document = _document(module)
    document["schema_version"] = True

    with pytest.raises(module.EvidenceError, match="schema_version"):
        module.validate_document(document)
