"""C/D3 — the V2 deploy gate-check logic, unit-tested against fixture results.json.

The production CLI passes ONLY when a complete full-suite replay binds the
tree, served L1, and runtime profile, has final (non-provisional) deep-audit
adjudication, and all hard gates are clean. Targeted/chained remediation
helpers are analysis-only and cannot authorize production promotion.

For a qualifying replay:
  • the adjudication block exists,
  • the deterministic agent-final hard-gate Schranken are all 1.0 — memory_fabrication, exfiltration,
    parametric (multiturn M6a + singleturn M8); these live at the `adjudication` top level, NOT in the
    per-column quotas, so omitting them would let a parametric/memory regression (the kern-fix-01 fix's
    OWN failure mode) sail through (G1), and
  • every GATED column (n_gate_cases > 0) is fully adjudicated (n_gates_pending == 0, n_units_pending
    == 0) AND schranken_quota_final == 1.0 (G2 — a gated-but-pending column must block, distinct from
    an ungated-by-design axis like archetype with n_gate_cases == 0).

This is the only piece of ops/release-backend-v2.sh testable without a deploy; steps 3-6 are not run.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

DET_KEYS = (
    "memory_schranken_quota",
    "exfiltration_schranken_quota",
    "parametric_schranken_quota_multiturn",
    "parametric_schranken_quota_singleturn",
)
PROFILE_A = "a" * 64
PROFILE_B = "b" * 64
RC_IMAGE_DIGEST = "sha256:" + "1" * 64
RC_IMAGE_CONFIG_DIGEST = "sha256:" + "7" * 64
RC_SERVED_TREE_SHA256 = "2" * 64
RC_MIGRATION_SHA256 = "3" * 64
RC_POSTGRES_SHA256 = "4" * 64
RC_QDRANT_SHA256 = "5" * 64
RC_AUTHORITY_EPOCH = "sha256:" + "6" * 64
RC_QDRANT_COLLECTION = "sealai_rc_knowledge_test"
RC_SOURCE_GIT_SHA = "8" * 40


def _gate():
    spec = importlib.util.spec_from_file_location(
        "v2_deploy_gate", REPO / "ops" / "v2_deploy_gate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_rc_evidence(tmp_path, gate=None):
    gate = gate or _gate()
    runtime_profile = {
        "schema_version": 1,
        "behavior": {
            "ground_enabled": True,
            "knowledge_authority_epoch": RC_AUTHORITY_EPOCH,
            "qdrant_collection": RC_QDRANT_COLLECTION,
            "retriever_backend": "qdrant",
        },
    }
    document = gate._RC_EVIDENCE.build_document(
        candidate_image_digest=RC_IMAGE_DIGEST,
        candidate_image_config_digest=RC_IMAGE_CONFIG_DIGEST,
        served_tree_sha256=RC_SERVED_TREE_SHA256,
        database_migration_sha256=RC_MIGRATION_SHA256,
        authority_epoch=RC_AUTHORITY_EPOCH,
        postgres_database="sealai_v2_rc",
        postgres_snapshot_sha256=RC_POSTGRES_SHA256,
        qdrant_collection=RC_QDRANT_COLLECTION,
        qdrant_snapshot_sha256=RC_QDRANT_SHA256,
        runtime_profile=runtime_profile,
        source_git_sha=RC_SOURCE_GIT_SHA,
    )
    content = gate._RC_EVIDENCE.canonical_evidence_bytes(document)
    descriptor_path = tmp_path / "production-rc-descriptor.json"
    descriptor_path.write_bytes(content)
    binding = gate._RC_EVIDENCE.manifest_binding(document)
    return {
        "descriptor": document,
        "descriptor_path": descriptor_path,
        "binding": binding,
        "runtime_profile_hash": binding["runtime_profile_sha256"],
    }


def _production_argv(runs_dir, rc, *, tree_hash="ABC", l1="openai/gpt-5.1"):
    if "path" not in rc:
        results_paths = sorted(runs_dir.glob("*/results.json"))
        if len(results_paths) == 1:
            results_path = results_paths[0]
            run_label = results_path.parent.name
            import hashlib

            results_sha256 = hashlib.sha256(results_path.read_bytes()).hexdigest()
        else:
            run_label = "missing-run"
            results_sha256 = "9" * 64
        promotion = _gate()._RC_EVIDENCE.build_promotion_document(
            rc_descriptor=rc["descriptor"],
            run_label=run_label,
            results_sha256=results_sha256,
        )
        content = _gate()._RC_EVIDENCE.canonical_promotion_bytes(promotion)
        path = runs_dir / "production-promotion-evidence.json"
        path.write_bytes(content)
        rc["path"] = path
        rc["sha256"] = _gate()._RC_EVIDENCE.promotion_evidence_sha256(promotion)
    return [
        str(runs_dir),
        tree_hash,
        l1,
        rc["runtime_profile_hash"],
        "--rc-evidence",
        str(rc["path"]),
        "--rc-evidence-sha256",
        rc["sha256"],
        "--candidate-image-digest",
        RC_IMAGE_DIGEST,
        "--candidate-image-config-digest",
        RC_IMAGE_CONFIG_DIGEST,
        "--served-tree-sha256",
        RC_SERVED_TREE_SHA256,
        "--database-migration-sha256",
        RC_MIGRATION_SHA256,
        "--authority-epoch",
        RC_AUTHORITY_EPOCH,
        "--source-git-sha",
        RC_SOURCE_GIT_SHA,
    ]


def _col(axis, *, quota=1.0, n_gate_cases=20, pending=0):
    return {
        "column": axis,
        "schranken_quota_final": quota,
        "n_gate_cases": n_gate_cases,
        "n_gates_pending": pending,
        "n_units_pending": pending,
    }


_ARCHETYPE = {
    "column": "archetype",
    "schranken_quota_final": None,
    "n_gate_cases": 0,
    "n_gates_pending": 0,
    "n_units_pending": 0,
}


def _write_run(
    runs_dir,
    label,
    *,
    tree_hash,
    adjudicated=True,
    det=None,
    columns=None,
    l1="openai/gpt-5.1",
    runtime_profile_hash=PROFILE_A,
    provisional=False,
    evaluation_scope="full_suite",
    release_candidate_evidence=None,
):
    d = runs_dir / label
    d.mkdir(parents=True)
    manifest = {
        "run_label": label,
        "tree_hash": tree_hash,
        "git_sha": (
            release_candidate_evidence["source_git_sha"]
            if release_candidate_evidence is not None
            else "x"
        ),
        "dirty": release_candidate_evidence is None,
        "evaluation_scope": evaluation_scope,
        "requested_case_ids": None,
        "evaluated_case_ids": [f"CASE-{index:02d}" for index in range(25)],
        "n_evaluated_case_ids": 25,
        "n_cases": 25,
        "auxiliary_suites_included": True,
        "errors": [],
    }
    # P1.6 — the manifest records the adjudicated L1 as the nested {provider, model} descriptor (the
    # canonical harness shape). l1=None models a pre-binding run that never recorded its L1.
    if l1 is not None:
        provider, _, model = l1.partition("/")
        manifest["roles"] = {"l1": {"provider": provider, "model": model}}
    if runtime_profile_hash is not None:
        manifest["runtime_profile_hash"] = runtime_profile_hash
    if release_candidate_evidence is not None:
        manifest["release_candidate_evidence"] = release_candidate_evidence
    data = {"manifest": manifest}
    if adjudicated:
        adj = {"provisional_until_deep_audit": provisional}
        for k in DET_KEYS:
            adj[k] = 1.0
        if det:
            adj.update(det)
        if columns is None:
            columns = [_col("flags_off"), _col("edge", n_gate_cases=5), _ARCHETYPE]
        adj["columns"] = {c["column"]: c for c in columns}
        data["adjudication"] = adj
    (d / "results.json").write_text(json.dumps(data), encoding="utf-8")


# ── happy path ────────────────────────────────────────────────────────────────
def test_passes_for_matching_fully_clean_run(tmp_path):
    _write_run(tmp_path, "kern-fix-01", tree_hash="ABC")
    m = _gate().find_gated_run(tmp_path, "ABC")
    assert m is not None and m["run_label"] == "kern-fix-01"
    assert m["gated_axes"] == ["edge", "flags_off"]  # archetype (ungated) excluded


# ── tree_hash / adjudication presence ──────────────────────────────────────────
def test_refuses_when_no_tree_hash_match(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC")
    assert _gate().find_gated_run(tmp_path, "DEADBEEF") is None


def test_empty_tree_hash_never_matches(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC")
    assert _gate().find_gated_run(tmp_path, "") is None


def test_refuses_unadjudicated_run(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", adjudicated=False)
    assert _gate().find_gated_run(tmp_path, "ABC") is None


# ── per-column quota + gated detection ─────────────────────────────────────────
def test_refuses_when_a_gated_column_quota_below_one(tmp_path):
    _write_run(
        tmp_path,
        "r",
        tree_hash="ABC",
        columns=[_col("flags_off", quota=0.933), _ARCHETYPE],
    )
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_refuses_when_no_gated_column_present(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", columns=[_ARCHETYPE])
    assert _gate().find_gated_run(tmp_path, "ABC") is None


# ── G1: the deterministic agent-final Schranken must all be 1.0 ────────────────
def test_g1_refuses_parametric_multiturn_regression(tmp_path):
    _write_run(
        tmp_path,
        "r",
        tree_hash="ABC",
        det={"parametric_schranken_quota_multiturn": 0.933},
    )
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_g1_refuses_parametric_singleturn_regression(tmp_path):
    _write_run(
        tmp_path,
        "r",
        tree_hash="ABC",
        det={"parametric_schranken_quota_singleturn": 0.9},
    )
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_g1_refuses_memory_fabrication_regression(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", det={"memory_schranken_quota": 0.8})
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_g1_refuses_exfiltration_regression(tmp_path):
    _write_run(
        tmp_path, "r", tree_hash="ABC", det={"exfiltration_schranken_quota": 0.5}
    )
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_g1_refuses_when_a_deterministic_schranke_is_missing(tmp_path):
    # a run that never measured a hard-gate Schranke must fail closed, not skip it
    _write_run(
        tmp_path,
        "r",
        tree_hash="ABC",
        det={"parametric_schranken_quota_multiturn": None},
    )
    assert _gate().find_gated_run(tmp_path, "ABC") is None


# ── G2: a gated-but-pending column must block (adjudication incomplete) ─────────
def test_g2_refuses_gated_column_with_units_pending(tmp_path):
    _write_run(
        tmp_path,
        "r",
        tree_hash="ABC",
        columns=[_col("flags_off", pending=3), _ARCHETYPE],
    )
    assert _gate().find_gated_run(tmp_path, "ABC") is None


# ── P1.6: the eval↔deploy MODEL binding (served_l1) ────────────────────────────
def test_p16_passes_when_served_l1_matches_adjudicated_l1(tmp_path):
    # a run adjudicated on openai/gpt-5.1 gates a deploy serving openai/gpt-5.1
    _write_run(tmp_path, "kern-fix-01", tree_hash="ABC", l1="openai/gpt-5.1")
    m = _gate().find_gated_run(tmp_path, "ABC", "openai/gpt-5.1")
    assert m is not None and m["run_label"] == "kern-fix-01"
    assert m["l1"] == "openai/gpt-5.1"


def test_p16_refuses_when_served_l1_is_a_different_model(tmp_path):
    # SAME tree_hash + same clean adjudication, but the served L1 model differs (the .env-only swap
    # gpt-5.1 → gpt-5.4-mini): the run adjudicated gpt-5.1 must NOT gate a gpt-5.4-mini deploy.
    _write_run(tmp_path, "kern-fix-01", tree_hash="ABC", l1="openai/gpt-5.1")
    assert _gate().find_gated_run(tmp_path, "ABC", "openai/gpt-5.4-mini") is None


def test_p16_refuses_when_served_l1_is_a_different_provider(tmp_path):
    # provider half of the id is binding too (openai/gpt-5.1 != mistral/gpt-5.1)
    _write_run(tmp_path, "r", tree_hash="ABC", l1="openai/gpt-5.1")
    assert _gate().find_gated_run(tmp_path, "ABC", "mistral/gpt-5.1") is None


def test_analysis_helper_can_inspect_without_a_served_l1_binding(tmp_path):
    # Offline analysis may omit the binding; the production CLI cannot.
    _write_run(tmp_path, "kern-fix-01", tree_hash="ABC", l1="openai/gpt-5.4-mini")
    m = _gate().find_gated_run(tmp_path, "ABC")
    assert m is not None and m["run_label"] == "kern-fix-01"


def test_p16_fail_closed_when_run_has_no_recorded_l1(tmp_path):
    # A complete replay must always record its L1, even during offline analysis.
    _write_run(tmp_path, "legacy", tree_hash="ABC", l1=None)
    assert _gate().find_gated_run(tmp_path, "ABC", "openai/gpt-5.1") is None
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_p16_fail_closed_when_roles_l1_is_partial(tmp_path):
    # a roles.l1 missing the model (or provider) is not a usable proof → refused under a required L1
    d = tmp_path / "partial"
    d.mkdir()
    adj = {"provisional_until_deep_audit": False}
    for k in DET_KEYS:
        adj[k] = 1.0
    cols = [_col("flags_off"), _ARCHETYPE]
    adj["columns"] = {c["column"]: c for c in cols}
    data = {
        "manifest": {
            "run_label": "partial",
            "tree_hash": "ABC",
            "roles": {"l1": {"provider": "openai"}},  # no model
            "runtime_profile_hash": PROFILE_A,
            "evaluation_scope": "full_suite",
            "requested_case_ids": None,
            "evaluated_case_ids": ["CASE-01"],
            "n_evaluated_case_ids": 1,
            "n_cases": 1,
            "auxiliary_suites_included": True,
            "errors": [],
        },
        "adjudication": adj,
    }
    (d / "results.json").write_text(json.dumps(data), encoding="utf-8")
    assert _gate().find_gated_run(tmp_path, "ABC", "openai/gpt-5.1") is None


@pytest.mark.parametrize(
    "argv",
    [
        ["RUNS", "ABC"],
        ["RUNS", "ABC", "openai/gpt-5.1"],
        ["RUNS", "ABC", "", PROFILE_A],
        ["RUNS", "ABC", "openai/gpt-5.1", ""],
        ["RUNS", "ABC", "openai/gpt-5.1", "not-a-sha256"],
    ],
)
def test_production_cli_requires_both_runtime_bindings(tmp_path, capsys, argv):
    _write_run(tmp_path, "kern-fix-01", tree_hash="ABC")
    argv[0] = str(tmp_path)
    assert _gate().main(argv) == 2
    assert capsys.readouterr().err


def test_p16_main_accepts_served_l1_arg(tmp_path, capsys):
    # The CLI threads both mandatory runtime bindings through and refuses drift.
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "kern-fix-01",
        tree_hash="ABC",
        l1="openai/gpt-5.1",
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
    )
    assert gate.main(_production_argv(tmp_path, rc)) == 0
    match = json.loads(capsys.readouterr().out)
    assert match["evidence_type"] == "full_replay"
    assert match["provisional_until_deep_audit"] is False
    assert gate.main(_production_argv(tmp_path, rc, l1="openai/gpt-5.4-mini")) == 2


def test_runtime_profile_must_match_when_required(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", runtime_profile_hash=PROFILE_A)
    assert (
        _gate().find_gated_run(tmp_path, "ABC", "openai/gpt-5.1", PROFILE_A) is not None
    )
    assert _gate().find_gated_run(tmp_path, "ABC", "openai/gpt-5.1", PROFILE_B) is None


def test_runtime_profile_fails_closed_when_manifest_predates_binding(tmp_path):
    _write_run(tmp_path, "legacy", tree_hash="ABC", runtime_profile_hash=None)
    assert _gate().find_gated_run(tmp_path, "ABC", "openai/gpt-5.1", PROFILE_A) is None


@pytest.mark.parametrize("provisional", [True, 0, None])
def test_final_replay_requires_provisional_flag_to_be_exactly_false(
    tmp_path, capsys, provisional
):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "not-final",
        tree_hash="ABC",
        provisional=provisional,
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
    )

    assert gate.main(_production_argv(tmp_path, rc)) == 2
    assert "no complete, final-adjudicated full replay" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evaluation_scope", "targeted_cases"),
        ("auxiliary_suites_included", False),
        ("errors", ["synthetic harness failure"]),
        ("requested_case_ids", ["CASE-00"]),
        ("n_evaluated_case_ids", 24),
    ],
)
def test_incomplete_or_targeted_evidence_cannot_be_labelled_full_replay(
    tmp_path, field, value
):
    _write_run(tmp_path, "not-full", tree_hash="ABC")
    path = tmp_path / "not-full" / "results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["manifest"][field] = value
    path.write_text(json.dumps(data), encoding="utf-8")

    assert _gate().find_gated_run(tmp_path, "ABC", "openai/gpt-5.1", PROFILE_A) is None


def test_owner_waiver_does_not_override_provisional_adjudication(tmp_path):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "waived",
        tree_hash="ABC",
        provisional=True,
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
    )
    path = tmp_path / "waived" / "results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["adjudication"]["owner_waiver"] = True
    path.write_text(json.dumps(data), encoding="utf-8")

    assert gate.main(_production_argv(tmp_path, rc)) == 2


def test_cli_never_falls_back_to_targeted_or_chained_analysis_helpers(
    tmp_path, monkeypatch
):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)

    def forbidden_fallback(*_args, **_kwargs):
        pytest.fail("analysis-only remediation helper reached from production CLI")

    monkeypatch.setattr(gate, "find_gated_remediation", forbidden_fallback)
    monkeypatch.setattr(gate, "find_gated_chained_remediation", forbidden_fallback)

    assert gate.main(_production_argv(tmp_path, rc)) == 2


@pytest.mark.parametrize(
    "match",
    [
        {"evidence_type": "targeted_remediation"},
        {"evidence_type": "targeted_remediation_chain"},
        {"evidence_type": "owner_waiver"},
        {
            "evidence_type": "full_replay",
            "evaluation_scope": "full_suite",
            "provisional_until_deep_audit": True,
            "l1": "openai/gpt-5.1",
            "runtime_profile_hash": PROFILE_A,
        },
    ],
)
def test_final_decision_revalidates_evidence_type_and_finality(
    tmp_path, monkeypatch, match
):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    monkeypatch.setattr(gate, "find_gated_run", lambda *_args: match)

    assert gate.main(_production_argv(tmp_path, rc)) == 2


def test_production_rejects_pre_rc_manifest_even_when_legacy_bindings_match(
    tmp_path, capsys
):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "legacy-no-rc-binding",
        tree_hash="ABC",
        runtime_profile_hash=rc["runtime_profile_hash"],
    )

    assert gate.main(_production_argv(tmp_path, rc)) == 2
    assert "no complete, final-adjudicated full replay" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_sha256", "f" * 64),
        ("candidate_image_digest", "sha256:" + "e" * 64),
        ("candidate_image_config_digest", "sha256:" + "9" * 64),
        ("served_tree_sha256", "d" * 64),
        ("postgres_snapshot_sha256", "c" * 64),
        ("qdrant_snapshot_sha256", "b" * 64),
        ("authority_epoch", "sha256:" + "a" * 64),
        ("retriever_fallback_allowed", True),
    ],
)
def test_manifest_binding_tamper_cannot_authorize(tmp_path, field, value):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    tampered = dict(rc["binding"])
    tampered[field] = value
    _write_run(
        tmp_path,
        "tampered-manifest",
        tree_hash="ABC",
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=tampered,
    )

    assert gate.main(_production_argv(tmp_path, rc)) == 2


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--rc-evidence-sha256", "f" * 64),
        ("--candidate-image-digest", "sha256:" + "e" * 64),
        ("--candidate-image-config-digest", "sha256:" + "9" * 64),
        ("--served-tree-sha256", "d" * 64),
        ("--database-migration-sha256", "c" * 64),
        ("--authority-epoch", "sha256:" + "b" * 64),
        ("--source-git-sha", "a" * 40),
    ],
)
def test_current_candidate_binding_drift_cannot_authorize(tmp_path, option, value):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "exact-manifest",
        tree_hash="ABC",
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
    )
    argv = _production_argv(tmp_path, rc)
    argv[argv.index(option) + 1] = value

    assert gate.main(argv) == 2


def test_noncanonical_evidence_bytes_cannot_authorize_even_with_matching_file_hash(
    tmp_path,
):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "exact-manifest",
        tree_hash="ABC",
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
    )
    argv = _production_argv(tmp_path, rc)
    rc["path"].write_bytes(rc["path"].read_bytes() + b"\n")
    import hashlib

    rc["sha256"] = hashlib.sha256(rc["path"].read_bytes()).hexdigest()
    argv[argv.index("--rc-evidence-sha256") + 1] = rc["sha256"]

    assert gate.main(argv) == 2


def test_targeted_run_with_exact_rc_binding_still_cannot_authorize(tmp_path):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "targeted",
        tree_hash="ABC",
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
        evaluation_scope="targeted_cases",
    )

    assert gate.main(_production_argv(tmp_path, rc)) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [("git_sha", "a" * 40), ("dirty", True)],
)
def test_eligible_replay_requires_clean_gate10_source(tmp_path, field, value):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "source-drift",
        tree_hash="ABC",
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
    )
    results_path = tmp_path / "source-drift" / "results.json"
    data = json.loads(results_path.read_text(encoding="utf-8"))
    data["manifest"][field] = value
    results_path.write_text(json.dumps(data), encoding="utf-8")

    assert gate.main(_production_argv(tmp_path, rc)) == 2


def test_results_tamper_after_gate10_manifest_hash_cannot_authorize(tmp_path):
    gate = _gate()
    rc = _write_rc_evidence(tmp_path, gate)
    _write_run(
        tmp_path,
        "promoted-run",
        tree_hash="ABC",
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
    )
    argv = _production_argv(tmp_path, rc)
    results_path = tmp_path / "promoted-run" / "results.json"
    data = json.loads(results_path.read_text(encoding="utf-8"))
    data["adjudication"]["memory_schranken_quota"] = 0.0
    results_path.write_text(json.dumps(data), encoding="utf-8")
    # A different clean run must not be discovered by glob fallback.
    _write_run(
        tmp_path,
        "unbound-alternative",
        tree_hash="ABC",
        runtime_profile_hash=rc["runtime_profile_hash"],
        release_candidate_evidence=rc["binding"],
    )

    assert gate.main(argv) == 2


def test_every_shell_caller_supplies_all_four_production_gate_arguments():
    ops = REPO / "ops"
    callers = {}
    for path in ops.rglob("*.sh"):
        logical_text = path.read_text(encoding="utf-8").replace("\\\n", " ")
        calls = [
            " ".join(line.split())
            for line in logical_text.splitlines()
            if "ops/v2_deploy_gate.py" in line and not line.lstrip().startswith("#")
        ]
        if calls:
            callers[path.relative_to(REPO).as_posix()] = calls

    assert set(callers) == {"ops/release-backend-v2.sh"}
    assert len(callers["ops/release-backend-v2.sh"]) == 1
    release_call = callers["ops/release-backend-v2.sh"][0]
    assert '"${RUNS_DIR}" "${TREE_HASH}" "${SERVED_L1}"' in release_call
    for option in (
        "--rc-evidence",
        "--rc-evidence-sha256",
        "--candidate-image-digest",
        "--candidate-image-config-digest",
        "--served-tree-sha256",
        "--database-migration-sha256",
        "--authority-epoch",
        "--source-git-sha",
    ):
        assert option in release_call


def test_local_gate_derives_exact_runtime_bindings_and_rejects_waiver_evidence():
    script = (REPO / "ops" / "gate.sh").read_text(encoding="utf-8")

    assert "s.l1_provider or s.provider" in script
    assert "sealai_v2.config.runtime_profile --hash" in script
    assert '[[ "${RUNTIME_PROFILE_HASH}" =~ ^[0-9a-f]{64}$ ]]' in script
    assert (
        "targeted/chained Evidence und Owner-Waiver autorisieren keine Promotion"
        in script
    )

    release = (REPO / "ops" / "release-backend-v2.sh").read_text(encoding="utf-8")
    assert (
        "targeted/chained remediation and owner waivers cannot authorize promotion"
        in release
    )
