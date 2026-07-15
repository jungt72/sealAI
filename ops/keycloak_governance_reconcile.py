#!/usr/bin/env python3
"""Narrow, deny-by-default Keycloak governance-role reconciler.

The default mode reads and reports drift. ``--apply`` is the only mutation
switch and never changes user memberships. Receipts contain aggregate counts
and contract hashes only; user identifiers and credentials are never emitted.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "security" / "keycloak-governance-v1.json"
_CONFIG_PATH = f"/tmp/sealai-governance-kcadm-{os.getpid()}.config"


class ReconcileError(RuntimeError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconcileError("governance manifest is unreadable or invalid") from exc
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != 1:
        raise ReconcileError("unsupported governance manifest schema")
    if manifest.get("contract_id") != "sealai.keycloak.governance-roles":
        raise ReconcileError("unexpected governance contract id")
    if not str(manifest.get("contract_version", "")).strip():
        raise ReconcileError("governance contract version is required")
    if manifest.get("realm") != "sealAI":
        raise ReconcileError("governance manifest may target only the sealAI realm")

    forbidden = manifest.get("forbidden_role_names")
    if forbidden != ["admin"]:
        raise ReconcileError("the exact forbidden legacy role set must be ['admin']")

    roles = manifest.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ReconcileError("managed roles are required")
    role_names = [str(item.get("name", "")).strip() for item in roles]
    if any(not name for name in role_names) or len(set(role_names)) != len(role_names):
        raise ReconcileError("managed role names must be non-empty and unique")
    if set(role_names) & set(forbidden):
        raise ReconcileError("a forbidden legacy role cannot be managed")
    allowed_classes = {
        "administrator",
        "system_operator",
        "contributor",
        "manufacturer",
        "reviewer",
        "approver",
    }
    if any(item.get("authority_class") not in allowed_classes for item in roles):
        raise ReconcileError("a managed role has an invalid authority class")
    if any(not str(item.get("description", "")).strip() for item in roles):
        raise ReconcileError("every managed role requires a description")

    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ReconcileError("managed groups are required")
    paths = [str(item.get("path", "")) for item in groups]
    if len(set(paths)) != len(paths):
        raise ReconcileError("managed group paths must be unique")
    for item, path in zip(groups, paths, strict=True):
        if not path.startswith("/sealai-") or path.count("/") != 1:
            raise ReconcileError("managed groups must use exact flat /sealai-* paths")
        mapped_roles = item.get("roles")
        if (
            not isinstance(mapped_roles, list)
            or not mapped_roles
            or len(set(mapped_roles)) != len(mapped_roles)
            or not set(mapped_roles) <= set(role_names)
        ):
            raise ReconcileError("managed group role mappings are invalid")

    incompatibilities = manifest.get("incompatibility_sets")
    if not isinstance(incompatibilities, list) or not incompatibilities:
        raise ReconcileError("incompatibility sets are required")
    ids: set[str] = set()
    for item in incompatibilities:
        set_id = str(item.get("id", "")).strip()
        referenced = item.get("groups")
        if not set_id or set_id in ids:
            raise ReconcileError("incompatibility ids must be non-empty and unique")
        ids.add(set_id)
        if item.get("maximum_groups_per_subject") != 1:
            raise ReconcileError("incompatibility sets must allow at most one group")
        if (
            not isinstance(referenced, list)
            or len(referenced) < 2
            or not set(referenced) <= set(paths)
        ):
            raise ReconcileError("incompatibility set references unknown groups")

    expected_policy = {
        "manage_user_memberships": False,
        "managed_group_role_mappings": "exact",
        "incompatible_membership_overlap": "block_apply",
        "forbidden_direct_role_assignments": "block_apply",
    }
    if manifest.get("assignment_policy") != expected_policy:
        raise ReconcileError("assignment policy must remain fail closed")


def normalize_state(raw: dict[str, Any], *, realm: str) -> dict[str, Any]:
    if raw.get("realm") != realm:
        raise ReconcileError("observed state belongs to a different realm")
    roles = raw.get("roles", [])
    groups = raw.get("groups", [])
    forbidden_assignments = raw.get("forbidden_role_assignments", {})
    if not isinstance(roles, list) or not isinstance(groups, list):
        raise ReconcileError("observed roles and groups must be arrays")
    normalized_roles: dict[str, str] = {}
    for role in roles:
        name = str(role.get("name", "")).strip()
        if not name or name in normalized_roles:
            raise ReconcileError("observed role names must be non-empty and unique")
        normalized_roles[name] = str(role.get("description", ""))
    normalized_groups: dict[str, dict[str, Any]] = {}
    for group in groups:
        path = str(group.get("path", ""))
        if not path or path in normalized_groups:
            raise ReconcileError("observed group paths must be non-empty and unique")
        group_id = str(group.get("id", ""))
        role_names = sorted({str(item) for item in group.get("roles", []) if item})
        members = sorted({str(item) for item in group.get("members", []) if item})
        normalized_groups[path] = {
            "id": group_id,
            "roles": role_names,
            "members": members,
        }
    assignment_counts = {
        str(name): int(count) for name, count in forbidden_assignments.items()
    }
    if any(count < 0 for count in assignment_counts.values()):
        raise ReconcileError("forbidden role assignment counts cannot be negative")
    return {
        "realm": realm,
        "roles": normalized_roles,
        "groups": normalized_groups,
        "forbidden_role_assignments": assignment_counts,
    }


@dataclass(frozen=True)
class Reconciliation:
    operations: tuple[dict[str, str], ...]
    overlap_count: int
    overlap_sets: dict[str, int]
    forbidden_assignment_count: int

    @property
    def apply_blocked(self) -> bool:
        return self.overlap_count > 0 or self.forbidden_assignment_count > 0


def compute_reconciliation(
    manifest: dict[str, Any], state: dict[str, Any]
) -> Reconciliation:
    operations: list[dict[str, str]] = []
    observed_roles = state["roles"]
    observed_groups = state["groups"]
    for role in manifest["roles"]:
        name = role["name"]
        description = role["description"]
        if name not in observed_roles:
            operations.append(
                {"action": "create_role", "role": name, "description": description}
            )
        elif observed_roles[name] != description:
            operations.append(
                {
                    "action": "update_role_description",
                    "role": name,
                    "description": description,
                }
            )
    for group in manifest["groups"]:
        path = group["path"]
        desired_roles = set(group["roles"])
        observed = observed_groups.get(path)
        if observed is None:
            operations.append({"action": "create_group", "path": path})
            observed_group_roles: set[str] = set()
        else:
            observed_group_roles = set(observed["roles"])
        for role in sorted(desired_roles - observed_group_roles):
            operations.append({"action": "add_group_role", "path": path, "role": role})
        for role in sorted(observed_group_roles - desired_roles):
            operations.append(
                {"action": "remove_group_role", "path": path, "role": role}
            )

    overlap_subjects: set[str] = set()
    overlap_sets: dict[str, int] = {}
    for policy in manifest["incompatibility_sets"]:
        memberships: Counter[str] = Counter()
        for path in policy["groups"]:
            memberships.update(observed_groups.get(path, {}).get("members", []))
        conflicted = {subject for subject, count in memberships.items() if count > 1}
        overlap_subjects.update(conflicted)
        overlap_sets[policy["id"]] = len(conflicted)

    forbidden_assignment_count = sum(
        state["forbidden_role_assignments"].get(role, 0)
        for role in manifest["forbidden_role_names"]
    )
    return Reconciliation(
        operations=tuple(operations),
        overlap_count=len(overlap_subjects),
        overlap_sets=overlap_sets,
        forbidden_assignment_count=forbidden_assignment_count,
    )


def build_receipt(
    manifest: dict[str, Any],
    state: dict[str, Any],
    reconciliation: Reconciliation,
    *,
    mode: str,
) -> dict[str, Any]:
    sanitized_groups = {
        path: {
            "roles": group["roles"],
            "member_count": len(group["members"]),
        }
        for path, group in sorted(state["groups"].items())
    }
    operation_counts = Counter(item["action"] for item in reconciliation.operations)
    return {
        "schema_version": 1,
        "mode": mode,
        "realm": manifest["realm"],
        "contract_version": manifest["contract_version"],
        "manifest_sha256": _digest(manifest),
        "sanitized_state_sha256": _digest(
            {
                "roles": sorted(state["roles"]),
                "groups": sanitized_groups,
                "forbidden_assignment_counts": state["forbidden_role_assignments"],
            }
        ),
        "counts": {
            "managed_roles": len(manifest["roles"]),
            "managed_groups": len(manifest["groups"]),
            "observed_roles": len(state["roles"]),
            "observed_groups": len(state["groups"]),
            "planned_operations": len(reconciliation.operations),
            "incompatible_subjects": reconciliation.overlap_count,
            "forbidden_direct_assignments": reconciliation.forbidden_assignment_count,
        },
        "operation_counts": dict(sorted(operation_counts.items())),
        "incompatibility_counts": dict(sorted(reconciliation.overlap_sets.items())),
        "apply_blocked": reconciliation.apply_blocked,
        "user_memberships_managed": False,
    }


class KcadmClient:
    def __init__(self, *, container: str, server: str, auth_realm: str) -> None:
        self.container = container
        self.server = server
        self.auth_realm = auth_realm

    def _docker(self, args: list[str], *, env: dict[str, str] | None = None) -> str:
        command = ["docker", "exec"]
        for name in sorted(env or {}):
            command.extend(["--env", name])
        command.extend([self.container, *args])
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )
        if completed.returncode != 0:
            raise ReconcileError("Keycloak Admin CLI command failed")
        return completed.stdout

    def kcadm(self, args: list[str]) -> Any:
        output = self._docker(
            ["/opt/keycloak/bin/kcadm.sh", *args, "--config", _CONFIG_PATH]
        )
        if not output.strip():
            return None
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise ReconcileError("Keycloak returned a non-JSON response") from exc

    def authenticate(self) -> None:
        client_id = os.environ.get("KEYCLOAK_ADMIN_CLIENT_ID", "")
        client_secret = os.environ.get("KEYCLOAK_ADMIN_CLIENT_SECRET", "")
        admin_user = os.environ.get("KEYCLOAK_ADMIN_USER", "")
        admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
        if client_id and client_secret:
            self._docker(
                [
                    "/bin/bash",
                    "-ec",
                    'exec /opt/keycloak/bin/kcadm.sh config credentials --server "$1" --realm "$2" --client "$3" --secret "$SEALAI_KCADM_SECRET" --config "$4"',
                    "--",
                    self.server,
                    self.auth_realm,
                    client_id,
                    _CONFIG_PATH,
                ],
                env={"SEALAI_KCADM_SECRET": client_secret},
            )
            return
        if admin_user and admin_password:
            self._docker(
                [
                    "/bin/bash",
                    "-ec",
                    'exec /opt/keycloak/bin/kcadm.sh config credentials --server "$1" --realm "$2" --user "$3" --password "$SEALAI_KCADM_PASSWORD" --config "$4"',
                    "--",
                    self.server,
                    self.auth_realm,
                    admin_user,
                    _CONFIG_PATH,
                ],
                env={"SEALAI_KCADM_PASSWORD": admin_password},
            )
            return
        raise ReconcileError("temporary Keycloak admin credentials are required")

    def cleanup(self) -> None:
        try:
            self._docker(["rm", "-f", _CONFIG_PATH])
        except ReconcileError:
            pass

    def read_state(self, manifest: dict[str, Any]) -> dict[str, Any]:
        realm = manifest["realm"]
        roles = self.kcadm(
            ["get", "roles", "-r", realm, "--fields", "name,description"]
        )
        groups = self.kcadm(["get", "groups", "-r", realm, "--fields", "id,name,path"])
        managed_paths = {item["path"] for item in manifest["groups"]}
        normalized_groups: list[dict[str, Any]] = []
        for group in groups or []:
            path = str(group.get("path", ""))
            if path not in managed_paths:
                continue
            group_id = str(group.get("id", ""))
            mappings = self.kcadm(
                ["get", f"groups/{group_id}/role-mappings/realm", "-r", realm]
            )
            members: list[str] = []
            first = 0
            while True:
                page = self.kcadm(
                    [
                        "get",
                        f"groups/{group_id}/members",
                        "-r",
                        realm,
                        "-q",
                        f"first={first}",
                        "-q",
                        "max=100",
                        "--fields",
                        "id",
                    ]
                )
                page = page or []
                members.extend(str(item["id"]) for item in page if item.get("id"))
                if len(page) < 100:
                    break
                first += len(page)
            normalized_groups.append(
                {
                    "id": group_id,
                    "path": path,
                    "roles": [item["name"] for item in mappings or []],
                    "members": members,
                }
            )
        forbidden_assignments: dict[str, int] = {}
        for role in manifest["forbidden_role_names"]:
            try:
                assignments = self.kcadm(
                    ["get", f"roles/{role}/users", "-r", realm, "--fields", "id"]
                )
            except ReconcileError:
                assignments = []
            forbidden_assignments[role] = len(assignments or [])
        return normalize_state(
            {
                "realm": realm,
                "roles": roles or [],
                "groups": normalized_groups,
                "forbidden_role_assignments": forbidden_assignments,
            },
            realm=realm,
        )

    def apply(self, manifest: dict[str, Any], reconciliation: Reconciliation) -> None:
        if reconciliation.apply_blocked:
            raise ReconcileError(
                "apply blocked by forbidden assignments or incompatible memberships"
            )
        realm = manifest["realm"]
        groups_by_path: dict[str, str] = {}
        for operation in reconciliation.operations:
            action = operation["action"]
            if action == "create_role":
                self.kcadm(
                    [
                        "create",
                        "roles",
                        "-r",
                        realm,
                        "-s",
                        f"name={operation['role']}",
                        "-s",
                        f"description={operation['description']}",
                    ]
                )
            elif action == "update_role_description":
                self.kcadm(
                    [
                        "update",
                        f"roles/{operation['role']}",
                        "-r",
                        realm,
                        "-s",
                        f"description={operation['description']}",
                    ]
                )
            elif action == "create_group":
                path = operation["path"]
                group_id = self._create_group(realm=realm, path=path)
                groups_by_path[path] = group_id

        state = self.read_state(manifest)
        groups_by_path.update(
            {
                path: group["id"]
                for path, group in state["groups"].items()
                if group["id"]
            }
        )
        for operation in reconciliation.operations:
            action = operation["action"]
            if action not in {"add_group_role", "remove_group_role"}:
                continue
            group_id = groups_by_path.get(operation["path"])
            if not group_id:
                raise ReconcileError(
                    "managed group could not be resolved after creation"
                )
            role = self.kcadm(["get", f"roles/{operation['role']}", "-r", realm])
            role_payload = json.dumps([role], ensure_ascii=True, separators=(",", ":"))
            endpoint = f"groups/{group_id}/role-mappings/realm"
            if action == "add_group_role":
                self.kcadm(["create", endpoint, "-r", realm, "-b", role_payload])
            else:
                self.kcadm(["delete", endpoint, "-r", realm, "-b", role_payload])

    def _create_group(self, *, realm: str, path: str) -> str:
        name = path.removeprefix("/")
        output = self._docker(
            [
                "/opt/keycloak/bin/kcadm.sh",
                "create",
                "groups",
                "-r",
                realm,
                "-s",
                f"name={name}",
                "-i",
                "--config",
                _CONFIG_PATH,
            ]
        )
        group_id = output.strip()
        if not group_id:
            raise ReconcileError("Keycloak did not return a created group id")
        return group_id


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument(
        "--container", default=os.environ.get("KEYCLOAK_CONTAINER", "keycloak")
    )
    parser.add_argument(
        "--server", default=os.environ.get("KEYCLOAK_SERVER", "http://localhost:8080")
    )
    parser.add_argument(
        "--auth-realm", default=os.environ.get("KEYCLOAK_AUTH_REALM", "master")
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        manifest_sha256 = _digest(manifest)
        if (
            args.expected_manifest_sha256
            and args.expected_manifest_sha256 != manifest_sha256
        ):
            raise ReconcileError(
                "manifest hash does not match the expected release contract"
            )
        if args.apply and not args.expected_manifest_sha256:
            raise ReconcileError("--apply requires --expected-manifest-sha256")
        if args.state_file:
            if args.apply:
                raise ReconcileError(
                    "--apply cannot be used with an offline state file"
                )
            raw_state = json.loads(args.state_file.read_text(encoding="utf-8"))
            state = normalize_state(raw_state, realm=manifest["realm"])
            reconciliation = compute_reconciliation(manifest, state)
            print(
                json.dumps(
                    build_receipt(manifest, state, reconciliation, mode="dry-run"),
                    sort_keys=True,
                )
            )
            return 2 if reconciliation.apply_blocked else 0

        client = KcadmClient(
            container=args.container, server=args.server, auth_realm=args.auth_realm
        )
        try:
            client.authenticate()
            state = client.read_state(manifest)
            reconciliation = compute_reconciliation(manifest, state)
            if args.apply:
                client.apply(manifest, reconciliation)
                final_state = client.read_state(manifest)
                final_reconciliation = compute_reconciliation(manifest, final_state)
                if final_reconciliation.operations:
                    raise ReconcileError(
                        "post-apply read-back still contains managed drift"
                    )
                receipt = build_receipt(
                    manifest, final_state, final_reconciliation, mode="apply"
                )
            else:
                receipt = build_receipt(manifest, state, reconciliation, mode="dry-run")
            print(json.dumps(receipt, sort_keys=True))
            return 2 if receipt["apply_blocked"] else 0
        finally:
            client.cleanup()
    except (OSError, json.JSONDecodeError, ReconcileError) as exc:
        print(f"keycloak_governance_reconcile: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
