"""Immutable build identity baked into every production backend-v2 image."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_PATH = Path("/etc/sealai/release-identity.json")


def create_identity(*, tree_hash: str, git_sha: str, requirements_file: Path) -> dict:
    requirements_sha = hashlib.sha256(requirements_file.read_bytes()).hexdigest()
    if not _HEX40.fullmatch(tree_hash):
        raise ValueError("tree_hash must be a 40-character lowercase Git object hash")
    if not _HEX40.fullmatch(git_sha):
        raise ValueError("git_sha must be a full 40-character lowercase commit hash")
    return {
        "schema_version": 1,
        "git_sha": git_sha,
        "requirements_sha256": requirements_sha,
        "tree_hash": tree_hash,
    }


def load_identity(path: Path = DEFAULT_PATH) -> dict:
    identity = json.loads(path.read_text(encoding="utf-8"))
    if identity.get("schema_version") != 1:
        raise ValueError("unsupported release identity schema")
    if not _HEX40.fullmatch(str(identity.get("tree_hash", ""))):
        raise ValueError("invalid release identity tree_hash")
    if not _HEX40.fullmatch(str(identity.get("git_sha", ""))):
        raise ValueError("invalid release identity git_sha")
    if not _HEX64.fullmatch(str(identity.get("requirements_sha256", ""))):
        raise ValueError("invalid release identity requirements hash")
    return identity


def verify_identity(*, identity_path: Path, tree_marker: Path) -> dict:
    identity = load_identity(identity_path)
    marker = tree_marker.read_text(encoding="utf-8").strip()
    if marker != identity["tree_hash"]:
        raise ValueError("gate tree marker does not match release identity")
    return identity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sealai_v2.config.build_identity")
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write")
    write.add_argument("--tree-hash", required=True)
    write.add_argument("--git-sha", required=True)
    write.add_argument("--requirements-file", type=Path, required=True)
    write.add_argument("--output", type=Path, default=DEFAULT_PATH)
    verify = sub.add_parser("verify")
    verify.add_argument("--identity", type=Path, default=DEFAULT_PATH)
    verify.add_argument(
        "--tree-marker", type=Path, default=Path("/etc/sealai/gate-tree-hash")
    )
    args = parser.parse_args(argv)
    if args.command == "write":
        identity = create_identity(
            tree_hash=args.tree_hash,
            git_sha=args.git_sha,
            requirements_file=args.requirements_file,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(identity, separators=(",", ":"), sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        identity = verify_identity(
            identity_path=args.identity, tree_marker=args.tree_marker
        )
        print(json.dumps(identity, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
