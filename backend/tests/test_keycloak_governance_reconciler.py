from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/keycloak_governance_reconcile.py"
MANIFEST = ROOT / "security/keycloak-governance-v1.json"


def _module():
    spec = importlib.util.spec_from_file_location(
        "keycloak_governance_reconcile", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _complete_state(manifest: dict) -> dict:
    return {
        "realm": manifest["realm"],
        "roles": [
            {"name": item["name"], "description": item["description"]}
            for item in manifest["roles"]
        ],
        "groups": [
            {
                "id": f"group-{index}",
                "path": item["path"],
                "roles": item["roles"],
                "members": [],
            }
            for index, item in enumerate(manifest["groups"])
        ],
        "forbidden_role_assignments": {"admin": 0},
    }


def test_manifest_has_exact_disjoint_application_authorities() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["forbidden_role_names"] == ["admin"]
    assert {item["name"] for item in manifest["roles"]} == {
        "tenant_admin",
        "platform_owner",
        "system_operator",
        "knowledge_contributor",
        "manufacturer",
        "capability_reviewer",
        "knowledge_reviewer",
        "knowledge_approver",
        "decision_reviewer",
    }
    assert all(len(group["roles"]) == 1 for group in manifest["groups"])
    assert {item["authority_class"] for item in manifest["roles"]} >= {
        "contributor",
        "reviewer",
        "approver",
        "administrator",
        "system_operator",
    }
    assert manifest["assignment_policy"] == {
        "manage_user_memberships": False,
        "managed_group_role_mappings": "exact",
        "incompatible_membership_overlap": "block_apply",
        "forbidden_direct_role_assignments": "block_apply",
    }


def test_complete_state_is_idempotent_and_legacy_mapping_is_removed() -> None:
    module = _module()
    manifest = module.load_manifest(MANIFEST)
    state = module.normalize_state(_complete_state(manifest), realm=manifest["realm"])
    assert module.compute_reconciliation(manifest, state).operations == ()

    drifted = _complete_state(manifest)
    drifted["groups"][0]["roles"] = ["tenant_admin", "admin"]
    drifted_state = module.normalize_state(drifted, realm=manifest["realm"])
    actions = module.compute_reconciliation(manifest, drifted_state).operations
    assert {tuple(sorted(item.items())) for item in actions} == {
        tuple(
            sorted(
                {
                    "action": "remove_group_role",
                    "path": "/sealai-tenant-administrators",
                    "role": "admin",
                }.items()
            )
        )
    }


def test_group_overlap_and_legacy_assignment_block_apply_without_identity_leak() -> (
    None
):
    module = _module()
    manifest = module.load_manifest(MANIFEST)
    raw = _complete_state(manifest)
    by_path = {item["path"]: item for item in raw["groups"]}
    by_path["/sealai-knowledge-contributors"]["members"] = ["sensitive-subject"]
    raw["role_members"] = {"knowledge_reviewer": ["sensitive-subject"]}
    raw["forbidden_role_assignments"] = {"admin": 2}
    state = module.normalize_state(raw, realm=manifest["realm"])

    result = module.compute_reconciliation(manifest, state)
    receipt = module.build_receipt(manifest, state, result, mode="dry-run")
    serialized = json.dumps(receipt, sort_keys=True)

    assert result.apply_blocked is True
    assert receipt["counts"]["incompatible_subjects"] == 1
    assert receipt["counts"]["forbidden_direct_assignments"] == 2
    assert receipt["counts"]["managed_role_subject_bindings"] == 1
    assert receipt["user_memberships_managed"] is False
    assert "sensitive-subject" not in serialized

    changed = _complete_state(manifest)
    changed_by_path = {item["path"]: item for item in changed["groups"]}
    changed_by_path["/sealai-knowledge-contributors"]["members"] = ["other-subject"]
    changed["role_members"] = {"knowledge_reviewer": ["other-subject"]}
    changed["forbidden_role_assignments"] = {"admin": 2}
    changed_receipt = module.build_receipt(
        manifest,
        module.normalize_state(changed, realm=manifest["realm"]),
        module.compute_reconciliation(
            manifest, module.normalize_state(changed, realm=manifest["realm"])
        ),
        mode="dry-run",
    )
    assert changed_receipt["counts"]["incompatible_subjects"] == 1
    assert (
        changed_receipt["sanitized_state_sha256"] != receipt["sanitized_state_sha256"]
    )
    assert "other-subject" not in json.dumps(changed_receipt, sort_keys=True)


def test_offline_fixture_can_never_be_used_for_apply(tmp_path: Path) -> None:
    module = _module()
    manifest = module.load_manifest(MANIFEST)
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(_complete_state(manifest)), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state-file",
            str(state_file),
            "--apply",
            "--expected-manifest-sha256",
            module._digest(manifest),
            "--expected-state-sha256",
            "0" * 64,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "cannot be used with an offline state file" in result.stderr


def test_apply_requires_manifest_and_exact_census_hash() -> None:
    module = _module()
    manifest = module.load_manifest(MANIFEST)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--apply",
            "--expected-manifest-sha256",
            module._digest(manifest),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "--expected-state-sha256" in result.stderr


def test_online_census_fails_closed_when_existing_role_members_are_unreadable() -> None:
    module = _module()
    manifest = module.load_manifest(MANIFEST)
    existing = manifest["roles"][0]
    client = module.KcadmClient(
        container="unused", server="https://unused.invalid", auth_realm="master"
    )

    def fake_kcadm(args: list[str]):
        endpoint = args[1]
        if endpoint == "roles":
            return [{"name": existing["name"], "description": existing["description"]}]
        if endpoint == "groups":
            return []
        if endpoint == f"roles/{existing['name']}/users":
            raise module.ReconcileError("member census denied")
        raise AssertionError(f"unexpected census endpoint: {endpoint}")

    client.kcadm = fake_kcadm

    with pytest.raises(module.ReconcileError, match="member census denied"):
        client.read_state(manifest)


def test_online_census_paginates_without_exposing_member_ids() -> None:
    module = _module()
    client = module.KcadmClient(
        container="unused", server="https://unused.invalid", auth_realm="master"
    )
    first_page = [{"id": f"opaque-{index}"} for index in range(100)]
    second_page = [{"id": "opaque-100"}]

    def fake_kcadm(args: list[str]):
        return second_page if "first=100" in args else first_page

    client.kcadm = fake_kcadm
    items = client._paged_get(
        endpoint="roles/knowledge_reviewer/users",
        realm="sealAI",
        fields="id",
        identity_field="id",
    )

    assert len(items) == 101
    receipt = {"member_count": len(items)}
    assert "opaque-100" not in json.dumps(receipt)


def test_broad_keycloak_hardener_cannot_assign_governance_roles() -> None:
    source = (ROOT / "ops/keycloak_ensure_roles.sh").read_text(encoding="utf-8")
    product_roles = source.split("PRODUCT_ROLES=(", 1)[1].split(")", 1)[0]
    role_descriptions = source.split("declare -A role_descriptions=(", 1)[1].split(
        ")", 1
    )[0]
    assert "admin" not in product_roles
    assert "reviewer" not in product_roles
    assert "manufacturer" not in product_roles
    assert "admin" not in role_descriptions
    assert "reviewer" not in role_descriptions
    assert "governance-reviewers" not in source
    assert "platform-admins" not in source
    assert "governance roles unchanged" in source
