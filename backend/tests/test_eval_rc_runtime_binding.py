"""Fail-closed runtime checks for an eligible eval's RC descriptor binding."""

from __future__ import annotations

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
SOURCE = "8" * 40
COLLECTION = "sealai_rc_knowledge_test"
RC_KEY = "rc_qdrant_scoped_key_1234567890"


def _evidence_module():
    spec = importlib.util.spec_from_file_location(
        "v2_rc_evidence_runtime_test", REPO / "ops" / "v2_rc_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _settings(**overrides):
    from sealai_v2.config.settings import Settings

    values = {
        "database_url": (
            "postgresql+psycopg2://sealai_rc_eval:rc_password_123456789012"
            "@rc-postgres:5432/sealai_v2_rc"
        ),
        "ground_enabled": True,
        "knowledge_authority_epoch": AUTHORITY,
        "qdrant_api_key": RC_KEY,
        "qdrant_collection": COLLECTION,
        "qdrant_url": "http://rc-qdrant:6333",
        "retriever_backend": "qdrant",
    }
    values.update(overrides)
    return Settings(**values)


def _binding_file(tmp_path, settings):
    from sealai_v2.config.runtime_profile import runtime_profile

    module = _evidence_module()
    document = module.build_document(
        candidate_image_digest=IMAGE,
        candidate_image_config_digest=IMAGE_CONFIG,
        served_tree_sha256=SERVED_TREE,
        database_migration_sha256=MIGRATIONS,
        authority_epoch=AUTHORITY,
        postgres_database="sealai_v2_rc",
        postgres_snapshot_sha256=POSTGRES,
        qdrant_collection=COLLECTION,
        qdrant_snapshot_sha256=QDRANT,
        runtime_profile=runtime_profile(settings),
        source_git_sha=SOURCE,
    )
    binding = module.manifest_binding(document)
    path = tmp_path / "binding.json"
    path.write_text(
        json.dumps(binding, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="ascii",
    )
    return path, binding


def _set_environment(monkeypatch, binding):
    values = {
        "SEALAI_EVAL_EVIDENCE_CLASS": "PRODUCTION_RC_ELIGIBLE",
        "SEALAI_EVAL_RC_DESCRIPTOR_SHA256": binding["evidence_sha256"],
        "SEALAI_EVAL_IMAGE_DIGEST": IMAGE,
        "SEALAI_EVAL_IMAGE_CONFIG_DIGEST": IMAGE_CONFIG,
        "SEALAI_EVAL_SERVED_TREE_SHA256": SERVED_TREE,
        "SEALAI_EVAL_DATABASE_MIGRATION_SHA256": MIGRATIONS,
        "SEALAI_RC_POSTGRES_SNAPSHOT_SHA256": POSTGRES,
        "SEALAI_RC_QDRANT_SNAPSHOT_SHA256": QDRANT,
        "SEALAI_EVAL_GIT_SHA": SOURCE,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_valid_eligible_runtime_is_bound(tmp_path, monkeypatch):
    from sealai_v2.eval.__main__ import _release_candidate_binding

    settings = _settings()
    path, binding = _binding_file(tmp_path, settings)
    _set_environment(monkeypatch, binding)

    assert (
        _release_candidate_binding(str(path), settings, git_sha=SOURCE, dirty=False)
        == binding
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "database_url": (
                "postgresql+psycopg2://sealai_rc_eval:rc_password_123456789012"
                "@prod-postgres:5432/sealai_v2_rc"
            )
        },
        {
            "database_url": (
                "postgresql+psycopg2://prod_user:rc_password_123456789012"
                "@rc-postgres:5432/sealai_v2_rc"
            )
        },
        {
            "database_url": (
                "postgresql+psycopg2://sealai_rc_eval:rc_password_123456789012"
                "@rc-postgres:5433/sealai_v2_rc"
            )
        },
        {"qdrant_url": "https://prod-qdrant.example:6333"},
        {"qdrant_api_key": None},
        {"qdrant_api_key": "too-short"},
    ],
)
def test_prod_endpoints_or_unscoped_qdrant_auth_are_rejected(
    tmp_path, monkeypatch, overrides
):
    from sealai_v2.eval.__main__ import _release_candidate_binding

    baseline = _settings()
    path, binding = _binding_file(tmp_path, baseline)
    _set_environment(monkeypatch, binding)

    with pytest.raises(SystemExit):
        _release_candidate_binding(
            str(path), _settings(**overrides), git_sha=SOURCE, dirty=False
        )


@pytest.mark.parametrize(
    ("env_name", "value"),
    [
        ("SEALAI_EVAL_IMAGE_DIGEST", "sha256:" + "a" * 64),
        ("SEALAI_EVAL_IMAGE_CONFIG_DIGEST", "sha256:" + "b" * 64),
        ("SEALAI_EVAL_RC_DESCRIPTOR_SHA256", "c" * 64),
    ],
)
def test_runner_image_or_descriptor_measurement_drift_is_rejected(
    tmp_path, monkeypatch, env_name, value
):
    from sealai_v2.eval.__main__ import _release_candidate_binding

    settings = _settings()
    path, binding = _binding_file(tmp_path, settings)
    _set_environment(monkeypatch, binding)
    monkeypatch.setenv(env_name, value)

    with pytest.raises(SystemExit):
        _release_candidate_binding(str(path), settings, git_sha=SOURCE, dirty=False)


@pytest.mark.parametrize(
    ("evidence_class", "git_sha", "dirty"),
    [
        ("RC_STUB_NON_ELIGIBLE", SOURCE, False),
        ("PRODUCTION_RC_ELIGIBLE", "a" * 40, False),
        ("PRODUCTION_RC_ELIGIBLE", SOURCE, True),
    ],
)
def test_stub_source_or_dirty_lane_cannot_record_eligible_binding(
    tmp_path, monkeypatch, evidence_class, git_sha, dirty
):
    from sealai_v2.eval.__main__ import _release_candidate_binding

    settings = _settings()
    path, binding = _binding_file(tmp_path, settings)
    _set_environment(monkeypatch, binding)
    monkeypatch.setenv("SEALAI_EVAL_EVIDENCE_CLASS", evidence_class)

    with pytest.raises(SystemExit):
        _release_candidate_binding(str(path), settings, git_sha=git_sha, dirty=dirty)
