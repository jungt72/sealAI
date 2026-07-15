from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest
from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import (
    V2GovernanceQuarantine,
    V2IdentityAffiliationRevision,
    V2ManufacturerCapabilityProfile,
)
from sealai_v2.tests.affiliation_fixtures import affiliation

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/reviewer_governance_cutover.py"


def _module():
    spec = importlib.util.spec_from_file_location("reviewer_governance_cutover", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bundle() -> dict:
    record = affiliation("manufacturer-subject", "manufacturer-org")
    raw_record = {
        key: value
        for key, value in record.contract().items()
        if key != "schema_version"
    }
    raw_record["record_sha256"] = record.record_sha256
    return {
        "schema_version": 1,
        "contract_id": "sealai.affiliation-authority-import",
        "authority_version": "test-roster-v1",
        "approved_at": "2026-07-01T00:00:00Z",
        "approved_by": "human-authority-owner",
        "records": [raw_record],
    }


def test_authority_dry_run_emits_only_counts_and_hashes(tmp_path, capsys) -> None:
    module = _module()
    bundle_path = tmp_path / "authority.json"
    bundle_path.write_text(json.dumps(_bundle()), encoding="utf-8")

    assert module.main(["authority", "--bundle", str(bundle_path)]) == 0
    receipt = capsys.readouterr().out

    assert "manufacturer-subject" not in receipt
    assert "manufacturer-org" not in receipt
    parsed = json.loads(receipt)
    assert parsed["mode"] == "dry-run"
    assert parsed["record_count"] == 1
    assert parsed["inserted_count"] == 0
    assert "authority_version" not in parsed
    assert len(parsed["authority_version_sha256"]) == 64
    assert parsed["feature_activation_changed"] is False


def test_apply_requires_exact_gate_and_input_hash(tmp_path, capsys) -> None:
    module = _module()
    bundle_path = tmp_path / "authority.json"
    bundle_path.write_text(json.dumps(_bundle()), encoding="utf-8")

    assert module.main(["authority", "--bundle", str(bundle_path), "--apply"]) == 1
    assert "requires --confirm-gate GATE-07" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "value"),
    (("schema_version", True), ("authority_version", None)),
)
def test_authority_bundle_rejects_non_schema_scalar_types(
    tmp_path, field, value
) -> None:
    module = _module()
    bundle = _bundle()
    bundle[field] = value
    bundle_path = tmp_path / "invalid-authority.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(module.CutoverError):
        module.load_authority_bundle(bundle_path)


def test_authority_bundle_rejects_non_string_record_fields(tmp_path) -> None:
    module = _module()
    bundle = _bundle()
    bundle["records"][0]["effective_from"] = None
    bundle_path = tmp_path / "invalid-record.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(module.CutoverError):
        module.load_authority_bundle(bundle_path)


def test_authority_bundle_rejects_non_object_root_without_traceback(tmp_path) -> None:
    module = _module()
    bundle_path = tmp_path / "invalid-root.json"
    bundle_path.write_text(json.dumps([{}]), encoding="utf-8")

    with pytest.raises(module.CutoverError, match="fields do not match"):
        module.load_authority_bundle(bundle_path)


def test_quarantine_apply_requires_timezone_bound_detection_timestamp(
    tmp_path, monkeypatch, capsys
) -> None:
    module = _module()
    monkeypatch.setenv(
        "SEALAI_V2_DATABASE_URL", f"sqlite:///{tmp_path / 'quarantine.db'}"
    )

    assert (
        module.main(
            [
                "quarantine",
                "--apply",
                "--confirm-gate",
                "GATE-07",
                "--expected-input-sha256",
                "0" * 64,
                "--detected-at",
                "2026-07-15T12:00:00",
            ]
        )
        == 1
    )
    assert "must include a timezone" in capsys.readouterr().err


def test_authority_import_is_append_only_and_idempotent(tmp_path) -> None:
    module = _module()
    bundle_path = tmp_path / "authority.json"
    bundle_path.write_text(json.dumps(_bundle()), encoding="utf-8")
    _bundle_data, records = module.load_authority_bundle(bundle_path)
    engine = make_engine(f"sqlite:///{tmp_path / 'authority.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)

    assert module.apply_authority_bundle(sf, records) == 1
    assert module.apply_authority_bundle(sf, records) == 0
    with sf() as session:
        rows = session.scalars(select(V2IdentityAffiliationRevision)).all()
        assert len(rows) == 1
        assert rows[0].record_sha256 == records[0].record_sha256


def test_legacy_profile_quarantines_fingerprint_without_mutating_source(
    tmp_path,
) -> None:
    module = _module()
    engine = make_engine(f"sqlite:///{tmp_path / 'quarantine.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    with sf() as session:
        session.add(
            V2ManufacturerCapabilityProfile(
                manufacturer_id="legacy-manufacturer",
                company_name="Legacy",
                status="verified",
                updated_at="2026-07-01T00:00:00Z",
                version=4,
            )
        )
        session.commit()

    candidates = module.profile_legacy_governance(
        sf, fingerprint_key=b"test-governance-fingerprint-key-32"
    )
    assert len(candidates) == 1
    assert candidates[0].resource_type == "manufacturer_capability"
    assert len(candidates[0].record_fingerprint) == 64
    assert "legacy-manufacturer" not in json.dumps(candidates[0].contract())
    assert module.apply_quarantine(sf, candidates, now="2026-07-15T12:00:00Z") == 1
    assert module.apply_quarantine(sf, candidates, now="2026-07-15T12:00:00Z") == 0

    with sf() as session:
        profile = session.get(V2ManufacturerCapabilityProfile, "legacy-manufacturer")
        quarantine = session.scalar(select(V2GovernanceQuarantine))
        assert profile is not None and profile.status == "verified"
        assert quarantine is not None
        assert quarantine.resolution_status == "unresolved"
