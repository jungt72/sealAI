from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from sealai_v2.core.contracts import MaterialConstraintVerdict
from sealai_v2.core.material_evidence_ai_review import (
    AI_REVIEW_AUTHORITY,
    AIReviewSnapshotV1,
)
from sealai_v2.core.material_evidence_v2 import EvidenceManifestSnapshotV2
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.core.medium_catalog import MediumCatalogEntryV1
from sealai_v2.material_evidence_ai_review.rp001_pack import (
    EXPECTED_AI_PACKAGE,
    EXPECTED_MEDIA_COUNT,
    EXPECTED_RULE_COUNT,
    PACKAGE_CONTRACT_VERSION,
    RP001PackError,
    build_rp001_pack,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = (
    REPOSITORY_ROOT
    / "docs/ops/material-evidence-ai-review"
    / "RP-001_ELASTOMER_MEDIA_EXCLUSIONS_AI_V1"
)
CANDIDATE_REGISTER = (
    REPOSITORY_ROOT
    / "docs/ops/material-evidence-curation"
    / "RP-001_ELASTOMER_MEDIA_EXCLUSIONS_V1/candidate-register.json"
)
GENERATED = PACKAGE / "generated/draft"


def _raw_inputs() -> tuple[bytes, bytes, bytes]:
    return (
        (PACKAGE / "creator-input.json").read_bytes(),
        (PACKAGE / "creator-prompt.txt").read_bytes(),
        CANDIDATE_REGISTER.read_bytes(),
    )


def _build(*, source_directory: Path | None = None):
    creator_input, creator_prompt, candidate_register = _raw_inputs()
    return build_rp001_pack(
        creator_input_raw=creator_input,
        creator_prompt_raw=creator_prompt,
        candidate_register_raw=candidate_register,
        source_directory=source_directory,
    )


def _mutated_input(mutator) -> bytes:
    value = json.loads((PACKAGE / "creator-input.json").read_text())
    mutator(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def test_golden_pack_is_exact_disqualify_only_and_non_authoritative() -> None:
    artifacts = _build()

    assert artifacts.package_input["package_id"] == EXPECTED_AI_PACKAGE
    assert (
        artifacts.package_input["package_contract_version"] == PACKAGE_CONTRACT_VERSION
    )
    assert len(artifacts.ruleset.payload.rules) == EXPECTED_RULE_COUNT
    assert len(artifacts.review.payload.media_identities) == EXPECTED_MEDIA_COUNT
    assert artifacts.review.payload.authority == AI_REVIEW_AUTHORITY
    assert artifacts.review.payload.positive_statement_allowed is False
    assert artifacts.review.payload.eligibility_failures() == ()
    assert all(
        rule.verdict is MaterialConstraintVerdict.UNVERTRAEGLICH
        and rule.evidence_binding.state == "unbound"
        for rule in artifacts.ruleset.payload.rules
    )
    assert all(
        not isinstance(identity, MediumCatalogEntryV1)
        for identity in artifacts.review.payload.media_identities
    )
    assert all(
        len(claim.primary_source_refs) == 2 and len(claim.source_refs) == 2
        for claim in artifacts.review.payload.claims
    )
    assert {rule.rule_ref for rule in artifacts.ruleset.payload.rules} == {
        "MR-RP001-AI-ACM-GLYCOL-BRAKE-FLUID",
        "MR-RP001-AI-ACM-STEAM-GT150C",
        "MR-RP001-AI-NBR-GLYCOL-BRAKE-FLUID",
        "MR-RP001-AI-NBR-STEAM-GT150C",
        "MR-RP001-AI-VMQ-DIESEL-FUEL",
        "MR-RP001-AI-VMQ-STEAM-GT150C",
    }


def test_committed_draft_artifacts_rehydrate_and_are_byte_reproducible() -> None:
    artifacts = _build()

    assert (GENERATED / "creator-output.json").read_bytes() == (
        artifacts.creator_output_bytes
    )
    assert (GENERATED / "ruleset-payload.json").read_bytes() == (
        artifacts.ruleset.canonical_bytes
    )
    assert (GENERATED / "material-evidence-payload.json").read_bytes() == (
        artifacts.evidence.canonical_bytes
    )
    assert (GENERATED / "ai-review-payload.json").read_bytes() == (
        artifacts.review.canonical_bytes
    )
    assert (GENERATED / "claude-audit-input.json").read_bytes() == (
        artifacts.audit_input.canonical_bytes
    )
    assert (
        MaterialRulesetSnapshotV1.from_json(
            artifacts.ruleset.ruleset_id,
            (GENERATED / "ruleset-payload.json").read_bytes(),
        )
        == artifacts.ruleset
    )
    assert (
        EvidenceManifestSnapshotV2.from_json(
            artifacts.evidence.manifest_id,
            (GENERATED / "material-evidence-payload.json").read_bytes(),
        )
        == artifacts.evidence
    )
    assert (
        AIReviewSnapshotV1.from_json(
            artifacts.review.batch_id,
            (GENERATED / "ai-review-payload.json").read_bytes(),
        )
        == artifacts.review
    )
    for identity in artifacts.media_identity_evidence:
        path = GENERATED / f"media-identity-{identity.payload.target.media_ref}.json"
        assert (
            EvidenceManifestSnapshotV2.from_json(
                identity.manifest_id, path.read_bytes()
            )
            == identity
        )


def test_package_manifest_binds_draft_and_review_incomplete_evidence() -> None:
    manifest = json.loads((PACKAGE / "package-manifest.json").read_bytes())

    assert set(manifest) == {
        "activation_authority",
        "artifacts",
        "authority",
        "candidate_count",
        "challenge_status",
        "human_review_or_approval",
        "media_identity_count",
        "package_contract_version",
        "package_id",
        "positive_statement_allowed",
        "production_migration",
        "public_projection",
        "sampling",
        "source_count",
        "state",
    }
    assert manifest["activation_authority"] is False
    assert manifest["authority"] == AI_REVIEW_AUTHORITY
    assert manifest["candidate_count"] == EXPECTED_RULE_COUNT
    assert manifest["challenge_status"] == "REVIEW_INCOMPLETE"
    assert manifest["human_review_or_approval"] is False
    assert manifest["media_identity_count"] == EXPECTED_MEDIA_COUNT
    assert manifest["package_contract_version"] == PACKAGE_CONTRACT_VERSION
    assert manifest["package_id"] == EXPECTED_AI_PACKAGE
    assert manifest["positive_statement_allowed"] is False
    assert manifest["production_migration"] is False
    assert manifest["public_projection"] is False
    assert manifest["sampling"] == 0
    assert manifest["source_count"] == 2
    assert manifest["state"] == "ai_draft"
    for relative_path, expected_sha256 in manifest["artifacts"].items():
        artifact = PACKAGE / relative_path
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_sha256

    incomplete = json.loads(
        (PACKAGE / "generated/review-incomplete-20260718T220426Z.json").read_bytes()
    )
    assert incomplete["transport_status"] == "REVIEW_INCOMPLETE"
    assert incomplete["retry_state"] == "not_authorized_pending_owner_decision"
    assert incomplete["claude_result_artifact"] == "absent"
    assert incomplete["challenge_rows_persisted"] == 0
    assert incomplete["snapshot_rows_persisted"] == 1
    assert incomplete["audit_input_sha256"] == (
        "e74a5df39121fc47c8a648606aa7d831e9819cd6f3950012cd792f5a6620f93e"
    )
    assert incomplete["audit_input_file_sha256"] == (
        "b0f3a58d1211368e4beb3dc3d91247b5ea71d8242c0fc04d4b6dba3088b73a65"
    )

    retry_incomplete = json.loads(
        (PACKAGE / "generated/review-incomplete-20260719T045705Z.json").read_bytes()
    )
    assert retry_incomplete["attempt_number"] == 2
    assert retry_incomplete["transport_status"] == "REVIEW_INCOMPLETE"
    assert retry_incomplete["retry_state"] == (
        "transport_retry_exhausted_new_identical_review_job_required"
    )
    assert retry_incomplete["actual_model"] == "unavailable_no_result_envelope"
    assert retry_incomplete["claude_result_artifact"] == "absent"
    assert retry_incomplete["challenge_rows_persisted"] == 0
    assert retry_incomplete["adjudication_rows_persisted"] == 0
    assert retry_incomplete["snapshot_rows_persisted"] == 1
    assert retry_incomplete["configured_model"] == "claude-sonnet-5"
    assert retry_incomplete["configured_isolation"] == {
        "chrome_enabled": False,
        "hooks_enabled": False,
        "mcp_enabled": False,
        "session_persistence_enabled": False,
        "tools_enabled": False,
    }
    assert retry_incomplete["audit_input_sha256"] == incomplete["audit_input_sha256"]
    assert (
        retry_incomplete["audit_input_file_sha256"]
        == incomplete["audit_input_file_sha256"]
    )
    assert retry_incomplete["previous_attempt_receipt_sha256"] == (
        "746bc8248bacb1daf4255ec96891e97a8efec7cc45e6099d9f795d226c2a32fe"
    )

    planned_job = json.loads(
        (PACKAGE / "generated/review-job-planned-after-transport-02.json").read_bytes()
    )
    assert planned_job["job_status"] == "planned_not_executed"
    assert planned_job["automatic_execution_authority"] is False
    assert planned_job["challenge_or_verdict_created"] is False
    assert planned_job["content_change_allowed"] is False
    assert planned_job["model"] == "claude-sonnet-5"
    assert planned_job["review_snapshot_id"] == retry_incomplete["review_snapshot_id"]
    assert planned_job["audit_input_sha256"] == retry_incomplete["audit_input_sha256"]
    assert (
        planned_job["audit_input_file_sha256"]
        == retry_incomplete["audit_input_file_sha256"]
    )


def test_frozen_audit_corpus_is_safe_complete_and_excludes_private_context() -> None:
    artifacts = _build()
    corpus = json.loads(artifacts.audit_input.canonical_bytes)

    assert "tenant_id" not in corpus
    assert "creator" not in corpus
    assert any("No positive compatibility" in item for item in corpus["invariants"])
    assert any("non-authoritative" in item for item in corpus["invariants"])
    assert corpus["corpus_safety_receipt"]["secret_match_count"] == 0
    assert corpus["corpus_safety_receipt"]["direct_identifier_match_count"] == 0
    assert len(corpus["claims"]) == EXPECTED_RULE_COUNT + EXPECTED_MEDIA_COUNT
    assert len(corpus["sources"]) == 2
    assert len(corpus["media_identity_candidates"]) == EXPECTED_MEDIA_COUNT


def test_technical_snapshots_are_permutation_invariant() -> None:
    creator_input, creator_prompt, candidate_register = _raw_inputs()
    value = json.loads(creator_input)
    value["sources"].reverse()
    value["media_identities"].reverse()
    value["rules"].reverse()
    permuted = build_rp001_pack(
        creator_input_raw=json.dumps(value, ensure_ascii=False).encode(),
        creator_prompt_raw=creator_prompt,
        candidate_register_raw=candidate_register,
    )
    baseline = _build()

    assert permuted.ruleset == baseline.ruleset
    assert permuted.evidence == baseline.evidence
    assert permuted.media_identity_evidence == baseline.media_identity_evidence
    assert permuted.review.review_snapshot_id != baseline.review.review_snapshot_id
    assert (
        permuted.review.payload.creator.input_sha256
        != baseline.review.payload.creator.input_sha256
    )


@pytest.mark.parametrize(
    "mutator,match",
    (
        (
            lambda value: value.update({"positive_statement_allowed": True}),
            "fields drift",
        ),
        (
            lambda value: value["rules"][0].update(
                {"material_candidate_id": "material:not-registered"}
            ),
            "foreign material gap",
        ),
        (
            lambda value: value["rules"][0].update({"source_keys": ["parker"]}),
            "lacks both primary sources",
        ),
        (
            lambda value: value["media_identities"][0].update(
                {"source_keys": ["parker"]}
            ),
            "lacks both sources",
        ),
    ),
)
def test_creator_input_contract_fails_closed(mutator, match: str) -> None:
    _, creator_prompt, candidate_register = _raw_inputs()
    with pytest.raises(RP001PackError, match=match):
        build_rp001_pack(
            creator_input_raw=_mutated_input(mutator),
            creator_prompt_raw=creator_prompt,
            candidate_register_raw=candidate_register,
        )


def test_missing_or_drifted_source_bytes_fail_closed(tmp_path: Path) -> None:
    creator_input, creator_prompt, candidate_register = _raw_inputs()
    with pytest.raises(RP001PackError, match="absent"):
        build_rp001_pack(
            creator_input_raw=creator_input,
            creator_prompt_raw=creator_prompt,
            candidate_register_raw=candidate_register,
            source_directory=tmp_path,
        )
    for filename in (
        "Parker-ORD-5700.pdf",
        "Trelleborg-Chemical-Compatibility-Guide.pdf",
    ):
        (tmp_path / filename).write_bytes(b"not the bound source")
    with pytest.raises(RP001PackError, match="digest drift"):
        build_rp001_pack(
            creator_input_raw=creator_input,
            creator_prompt_raw=creator_prompt,
            candidate_register_raw=candidate_register,
            source_directory=tmp_path,
        )


def test_candidate_register_hash_and_53_gap_boundary_are_immutable() -> None:
    creator_input, creator_prompt, candidate_register = _raw_inputs()
    changed = deepcopy(json.loads(candidate_register))
    changed["proposed_rule_pairs"] = [{"forbidden": True}]
    with pytest.raises(RP001PackError, match="authority boundary drift"):
        build_rp001_pack(
            creator_input_raw=creator_input,
            creator_prompt_raw=creator_prompt,
            candidate_register_raw=json.dumps(changed, sort_keys=True).encode(),
        )


def test_builder_is_not_referenced_by_runtime_or_public_surfaces() -> None:
    forbidden_roots = (
        REPOSITORY_ROOT / "backend/sealai_v2/api",
        REPOSITORY_ROOT / "backend/sealai_v2/pipeline",
        REPOSITORY_ROOT / "backend/sealai_v2/core",
        REPOSITORY_ROOT / "frontend-v2/src",
    )
    for root in forbidden_roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx"}:
                assert "rp001_pack" not in path.read_text(errors="ignore")
