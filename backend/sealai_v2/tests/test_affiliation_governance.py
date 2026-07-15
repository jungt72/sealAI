from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.governance import record_decision
from sealai_v2.governance.affiliations import (
    ALLOWED_AUTHORITY_SOURCES,
    AffiliationGovernanceError,
    affiliation_snapshot_from_contract,
    build_affiliation_record,
    capture_affiliation_snapshot,
    resolve_independence,
)
from sealai_v2.tests.affiliation_fixtures import affiliation

NOW = "2026-07-15T10:00:00Z"


def _snapshot(
    subject: str,
    organization: str,
    *,
    purpose: str,
    role: str,
    version: int,
):
    return capture_affiliation_snapshot(
        (affiliation(subject, organization),),
        subject_ref=subject,
        roles=(role,),
        captured_at=NOW,
        purpose=purpose,
        resource_type="knowledge_claim",
        resource_ref="claim-1",
        resource_version=version,
    )


def test_missing_or_tampered_human_authority_fails_closed() -> None:
    with pytest.raises(AffiliationGovernanceError, match="no current"):
        capture_affiliation_snapshot(
            (),
            subject_ref="reviewer",
            roles=("knowledge_reviewer",),
            captured_at=NOW,
            purpose="knowledge_reviewer",
            resource_type="knowledge_claim",
            resource_ref="claim-1",
            resource_version=2,
        )

    record = affiliation("reviewer", "reviewer-org")
    tampered = replace(record, organization_ref="manufacturer-org")
    with pytest.raises(AffiliationGovernanceError, match="integrity mismatch"):
        capture_affiliation_snapshot(
            (tampered,),
            subject_ref="reviewer",
            roles=("knowledge_reviewer",),
            captured_at=NOW,
            purpose="knowledge_reviewer",
            resource_type="knowledge_claim",
            resource_ref="claim-1",
            resource_version=2,
        )


def test_revoked_latest_revision_and_malformed_record_id_fail_closed() -> None:
    active = affiliation("reviewer", "reviewer-org", revision=1)
    revoked = affiliation("reviewer", "reviewer-org", revision=2, status="revoked")
    with pytest.raises(AffiliationGovernanceError, match="no current"):
        capture_affiliation_snapshot(
            (active, revoked),
            subject_ref="reviewer",
            roles=("knowledge_reviewer",),
            captured_at=NOW,
            purpose="knowledge_reviewer",
            resource_type="knowledge_claim",
            resource_ref="claim-1",
            resource_version=2,
        )

    malformed_id = replace(active, record_id="not-a-sha256")
    with pytest.raises(AffiliationGovernanceError, match="record id"):
        capture_affiliation_snapshot(
            (malformed_id,),
            subject_ref="reviewer",
            roles=("knowledge_reviewer",),
            captured_at=NOW,
            purpose="knowledge_reviewer",
            resource_type="knowledge_claim",
            resource_ref="claim-1",
            resource_version=2,
        )


def test_affiliation_recorded_after_snapshot_time_fails_closed() -> None:
    record = affiliation("reviewer", "reviewer-org")
    fields = {
        key: value
        for key, value in record.contract().items()
        if key != "schema_version"
    }
    future_record = build_affiliation_record(
        **{**fields, "recorded_at": "2026-07-16T00:00:00Z"}
    )

    with pytest.raises(AffiliationGovernanceError, match="not yet recorded"):
        capture_affiliation_snapshot(
            (future_record,),
            subject_ref="reviewer",
            roles=("knowledge_reviewer",),
            captured_at=NOW,
            purpose="knowledge_reviewer",
            resource_type="knowledge_claim",
            resource_ref="claim-1",
            resource_version=2,
        )


def test_jwt_claim_and_self_recorded_affiliation_are_not_human_authority() -> None:
    record = affiliation("reviewer", "reviewer-org")
    fields = {
        key: value
        for key, value in record.contract().items()
        if key != "schema_version"
    }
    untrusted = build_affiliation_record(**{**fields, "authority_source": "jwt_claim"})
    self_recorded = build_affiliation_record(
        **{**fields, "recorded_by": record.subject_ref}
    )

    for candidate, message in (
        (untrusted, "untrusted affiliation authority"),
        (self_recorded, "recorded by a separate human"),
    ):
        with pytest.raises(AffiliationGovernanceError, match=message):
            capture_affiliation_snapshot(
                (candidate,),
                subject_ref="reviewer",
                roles=("knowledge_reviewer",),
                captured_at=NOW,
                purpose="knowledge_reviewer",
                resource_type="knowledge_claim",
                resource_ref="claim-1",
                resource_version=2,
            )


def test_stored_snapshot_rejects_extra_fields_and_noncanonical_roles() -> None:
    snapshot = _snapshot(
        "reviewer",
        "reviewer-org",
        purpose="knowledge_reviewer",
        role="knowledge_reviewer",
        version=2,
    )
    extra = {**snapshot.contract(), "client_attestation": True}
    with pytest.raises(AffiliationGovernanceError, match="snapshot schema"):
        affiliation_snapshot_from_contract(extra)

    blank_role = {**snapshot.contract(), "roles": [""]}
    with pytest.raises(AffiliationGovernanceError, match="roles are invalid"):
        affiliation_snapshot_from_contract(blank_role)


def test_bundle_schema_and_runtime_allow_the_same_human_authority_sources() -> None:
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "security/affiliation-authority-bundle.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    source_enum = schema["properties"]["records"]["items"]["properties"][
        "authority_source"
    ]["enum"]

    assert set(source_enum) == set(ALLOWED_AUTHORITY_SOURCES)


def test_server_resolver_blocks_self_shared_affiliation_and_role_overlap() -> None:
    reviewer = _snapshot(
        "reviewer",
        "reviewer-org",
        purpose="knowledge_reviewer",
        role="knowledge_reviewer",
        version=2,
    )
    same_subject = _snapshot(
        "reviewer",
        "reviewer-org",
        purpose="knowledge_approver",
        role="knowledge_approver",
        version=3,
    )
    shared = _snapshot(
        "approver-connected",
        "reviewer-org",
        purpose="knowledge_approver",
        role="knowledge_approver",
        version=3,
    )
    incompatible = capture_affiliation_snapshot(
        (affiliation("approver-operator", "approver-org"),),
        subject_ref="approver-operator",
        roles=("knowledge_approver", "system_operator"),
        captured_at=NOW,
        purpose="knowledge_approver",
        resource_type="knowledge_claim",
        resource_ref="claim-1",
        resource_version=3,
    )

    assert (
        resolve_independence(
            reviewer,
            same_subject,
            required_second_role="knowledge_approver",
            incompatible_second_roles=("system_operator", "knowledge_reviewer"),
        ).reason_code
        == "self_review"
    )
    shared_resolution = resolve_independence(
        reviewer,
        shared,
        required_second_role="knowledge_approver",
        incompatible_second_roles=("system_operator", "knowledge_reviewer"),
    )
    assert shared_resolution.reason_code == "shared_affiliation"
    assert len(shared_resolution.shared_organization_sha256) == 1
    assert "reviewer-org" not in str(shared_resolution.contract())
    assert (
        resolve_independence(
            reviewer,
            incompatible,
            required_second_role="knowledge_approver",
            incompatible_second_roles=("system_operator", "knowledge_reviewer"),
        ).reason_code
        == "incompatible_role_overlap"
    )


def test_distinct_human_authorities_produce_immutable_allow_decision() -> None:
    reviewer = _snapshot(
        "reviewer",
        "reviewer-org",
        purpose="knowledge_reviewer",
        role="knowledge_reviewer",
        version=2,
    )
    approver = _snapshot(
        "approver",
        "approver-org",
        purpose="knowledge_approver",
        role="knowledge_approver",
        version=3,
    )

    resolution = resolve_independence(
        reviewer,
        approver,
        required_second_role="knowledge_approver",
        incompatible_second_roles=("system_operator", "knowledge_reviewer"),
    )

    assert resolution.allowed is True
    assert resolution.reason_code == "no_shared_affiliation"
    assert len(reviewer.snapshot_sha256) == 64
    assert len(approver.snapshot_sha256) == 64
    assert len(resolution.decision_sha256) == 64


def test_resource_version_cannot_receive_a_second_decision(tmp_path) -> None:
    reviewer = _snapshot(
        "reviewer",
        "reviewer-org",
        purpose="knowledge_reviewer",
        role="knowledge_reviewer",
        version=2,
    )
    approver = _snapshot(
        "approver",
        "approver-org",
        purpose="knowledge_approver",
        role="knowledge_approver",
        version=3,
    )
    resolution = resolve_independence(
        reviewer,
        approver,
        required_second_role="knowledge_approver",
        incompatible_second_roles=("system_operator", "knowledge_reviewer"),
    )
    engine = make_engine(f"sqlite:///{tmp_path / 'decision.db'}")
    Base.metadata.create_all(engine)
    session_factory = make_sessionmaker(engine)

    with session_factory() as session:
        record_decision(
            session,
            decision_type="knowledge_approval",
            resource_type="knowledge_claim",
            resource_ref="claim-1",
            resource_version=3,
            resolution=resolution,
            created_at=NOW,
            binding_sha256="a" * 64,
        )
        session.commit()

    with session_factory() as session:
        with pytest.raises(AffiliationGovernanceError, match="integrity mismatch"):
            record_decision(
                session,
                decision_type="knowledge_approval",
                resource_type="knowledge_claim",
                resource_ref="claim-1",
                resource_version=3,
                resolution=resolution,
                created_at="2026-07-15T11:00:00Z",
                binding_sha256="a" * 64,
            )
