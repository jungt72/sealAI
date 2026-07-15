from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import sys

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
sys.path.insert(0, str(OPS))

import permission_manifest as permissions  # noqa: E402


def _certificate_fingerprint(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        return permissions._certificate_fingerprint(descriptor)
    finally:
        os.close(descriptor)


def _request(tmp_path: Path) -> tuple[Path, dict[str, object], dict[str, Path]]:
    public_cert = tmp_path / "cert1.pem"
    shutil.copyfile(ROOT / "keycloak/certs/cert.pem", public_cert)
    public_cert.chmod(0o644)
    private_key = tmp_path / "privkey1.pem"
    private_key.write_bytes(b"synthetic-private-key-bytes-must-not-be-read\n")
    private_key.chmod(0o600)
    renewal = tmp_path / "lineage.conf"
    renewal.write_text("version = synthetic-non-secret\n", encoding="utf-8")
    renewal.chmod(0o600)
    fingerprint = _certificate_fingerprint(public_cert)
    common = {
        "lineage": "auth.sealai.net",
        "certbot_managed": True,
        "renewal_config_path": str(renewal),
        "public_certificate_fingerprint": fingerprint,
        "target_uid": os.geteuid(),
        "target_gid": os.getegid(),
    }
    value: dict[str, object] = {
        "batch": "GATE-02E",
        "objects": [
            {
                **common,
                "path": str(public_cert),
                "material_kind": "public_certificate",
                "runtime_consumers": ["certbot", "nginx"],
                "nginx_referenced": True,
                "target_mode": "0644",
            },
            {
                **common,
                "path": str(private_key),
                "material_kind": "private_key",
                "runtime_consumers": ["certbot", "nginx"],
                "nginx_referenced": True,
                "target_mode": "0600",
            },
            {
                **common,
                "path": str(renewal),
                "material_kind": "renewal_config",
                "runtime_consumers": ["certbot"],
                "nginx_referenced": False,
                "target_mode": "0600",
            },
        ],
    }
    request = tmp_path / "request.json"
    request.write_text(json.dumps(value), encoding="utf-8")
    return (
        request,
        value,
        {
            "certificate": public_cert,
            "private_key": private_key,
            "renewal": renewal,
        },
    )


def test_gate02e_private_key_descriptor_is_never_read(monkeypatch, tmp_path: Path):
    request, _, paths = _request(tmp_path)
    private_identity = paths["private_key"].stat().st_ino
    real_read = permissions.os.read

    def guarded_read(descriptor: int, amount: int) -> bytes:
        if os.fstat(descriptor).st_ino == private_identity:
            raise AssertionError("private key bytes were read")
        return real_read(descriptor, amount)

    monkeypatch.setattr(permissions.os, "read", guarded_read)
    manifest = permissions.generate_manifest(request)
    private_object = next(
        item for item in manifest["objects"] if item["material_kind"] == "private_key"
    )
    assert "sha256" not in private_object
    opened = permissions.validate_manifest(manifest)
    for descriptor, _, _ in opened:
        os.close(descriptor)


def test_gate02e_manifest_validates_schema_and_exact_relationships(tmp_path: Path):
    request, _, _ = _request(tmp_path)
    manifest = permissions.generate_manifest(request)
    schema = json.loads((OPS / "schemas/permission-manifest.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(manifest)
    assert manifest["gate_id"] == "GATE-02E"
    assert {item["material_kind"] for item in manifest["objects"]} == {
        "public_certificate",
        "private_key",
        "renewal_config",
    }


@pytest.mark.parametrize("drift", ["inode", "owner", "mode", "path"])
def test_gate02e_rejects_object_identity_and_metadata_drift(tmp_path: Path, drift: str):
    request, _, paths = _request(tmp_path)
    manifest = permissions.generate_manifest(request)
    private = next(
        item for item in manifest["objects"] if item["material_kind"] == "private_key"
    )
    if drift == "inode":
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"replacement-private-key\n")
        replacement.chmod(0o600)
        replacement.replace(paths["private_key"])
    elif drift == "owner":
        private["uid"] = int(private["uid"]) + 1
    elif drift == "mode":
        paths["private_key"].chmod(0o640)
    else:
        private["path"] = str(tmp_path / "missing-private-key")
    with pytest.raises(permissions.PermissionManifestError):
        permissions.validate_manifest(manifest)


def test_gate02e_rejects_symlink_swap(tmp_path: Path):
    request, _, paths = _request(tmp_path)
    manifest = permissions.generate_manifest(request)
    original = paths["private_key"]
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"replacement\n")
    replacement.chmod(0o600)
    original.unlink()
    original.symlink_to(replacement)
    with pytest.raises(permissions.PermissionManifestError, match="symlink"):
        permissions.validate_manifest(manifest)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("consumer", "Certbot"),
        ("renewal", "incomplete"),
        ("mode", "target mode"),
    ],
)
def test_gate02e_rejects_missing_consumers_renewal_and_unsafe_mode(
    tmp_path: Path, mutation: str, message: str
):
    request, value, _ = _request(tmp_path)
    objects = value["objects"]
    if mutation == "consumer":
        objects[0]["runtime_consumers"] = ["nginx"]
    elif mutation == "renewal":
        value["objects"] = [
            item for item in objects if item["material_kind"] != "renewal_config"
        ]
    else:
        next(item for item in objects if item["material_kind"] == "private_key")[
            "target_mode"
        ] = "0644"
    request.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(permissions.PermissionManifestError, match=message):
        permissions.generate_manifest(request)


def test_gate02e_partial_apply_rolls_back_all_modes(monkeypatch, tmp_path: Path):
    request, _, paths = _request(tmp_path)
    paths["certificate"].chmod(0o600)
    value = json.loads(request.read_text(encoding="utf-8"))
    value["objects"][0]["target_mode"] = "0644"
    request.write_text(json.dumps(value), encoding="utf-8")
    manifest = permissions.generate_manifest(request)
    original_modes = {
        path: stat.S_IMODE(path.stat().st_mode) for path in paths.values()
    }
    real_fchmod = permissions.os.fchmod
    calls = 0

    def fail_once(descriptor: int, mode: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic partial apply failure")
        real_fchmod(descriptor, mode)

    monkeypatch.setattr(permissions.os, "fchmod", fail_once)
    with pytest.raises(permissions.PermissionManifestError, match="rolled back"):
        permissions.apply_manifest(
            manifest,
            tmp_path / "rollback.json",
            require_root=False,
        )
    assert {
        path: stat.S_IMODE(path.stat().st_mode) for path in paths.values()
    } == original_modes


def test_gate02d_shape_and_hashing_remain_unchanged(tmp_path: Path):
    target = tmp_path / "legacy-gate02d-object"
    target.write_text("synthetic\n", encoding="utf-8")
    target.chmod(0o600)
    request = tmp_path / "gate02d.json"
    request.write_text(
        json.dumps(
            {
                "batch": "GATE-02D",
                "objects": [
                    {
                        "path": str(target),
                        "runtime_consumers": ["nginx"],
                        "target_uid": os.geteuid(),
                        "target_gid": os.getegid(),
                        "target_mode": "0640",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = permissions.generate_manifest(request)
    assert manifest["gate_id"] == "GATE-02D"
    assert set(manifest["objects"][0]) == {
        "path",
        "type",
        "device",
        "inode",
        "uid",
        "gid",
        "mode",
        "sha256",
        "runtime_consumers",
        "target_uid",
        "target_gid",
        "target_mode",
    }


def test_gate02e_has_no_recursive_or_service_mutation_path():
    source = (OPS / "permission_manifest.py").read_text(encoding="utf-8")
    for forbidden in (
        "os.walk",
        ".rglob(",
        ".glob(",
        "chmod -R",
        "chown -R",
        "certbot renew",
        "nginx -s reload",
        "systemctl",
    ):
        assert forbidden not in source
