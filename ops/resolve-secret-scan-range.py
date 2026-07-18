#!/usr/bin/env python3
"""Resolve one authoritative Git revision range or fail closed."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


OID_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
ZERO_OID_RE = re.compile(r"^0+$")


class RangeError(RuntimeError):
    pass


def _git(repo: Path, *args: str, allow_failure: bool = False) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        if allow_failure:
            return None
        raise RangeError("required Git revision operation failed")
    return result.stdout.strip()


def _verify(repo: Path, revision: str) -> None:
    if (
        not revision
        or _git(
            repo, "rev-parse", "--verify", f"{revision}^{{commit}}", allow_failure=True
        )
        is None
    ):
        raise RangeError("required Git revision is unavailable")


def resolve_range(
    repo: Path,
    *,
    event: str,
    before: str = "",
    after: str = "",
    base: str = "",
    head: str = "",
    default_ref: str = "",
    ref_name: str = "",
    default_branch: str = "",
) -> str:
    if event == "pull_request":
        _verify(repo, base)
        _verify(repo, head)
        if _git(repo, "merge-base", base, head, allow_failure=True) is None:
            raise RangeError("pull-request base is unreachable from head")
        return f"{base}..{head}"
    if event != "push":
        raise RangeError("unsupported scan event")

    _verify(repo, after)
    if not before:
        raise RangeError("push before revision is missing")
    if OID_RE.fullmatch(before) is None:
        raise RangeError("push before revision is malformed")
    new_branch = ZERO_OID_RE.fullmatch(before) is not None
    if not new_branch:
        before_available = (
            _git(
                repo,
                "rev-parse",
                "--verify",
                f"{before}^{{commit}}",
                allow_failure=True,
            )
            is not None
        )
        if before_available:
            if (
                _git(
                    repo,
                    "merge-base",
                    "--is-ancestor",
                    before,
                    after,
                    allow_failure=True,
                )
                is not None
            ):
                return f"{before}..{after}"
            if ref_name == default_branch:
                raise RangeError("non-fast-forward default-branch push is forbidden")
        elif ref_name == default_branch:
            raise RangeError("non-fast-forward default-branch push is forbidden")

    if not default_ref or not ref_name or not default_branch:
        raise RangeError("authoritative default-branch context is missing")
    _verify(repo, default_ref)
    merge_base = _git(repo, "merge-base", after, default_ref, allow_failure=True)
    if not merge_base:
        raise RangeError("authoritative default branch is unreachable")
    return f"{merge_base}..{after}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--event", required=True, choices=("push", "pull_request"))
    parser.add_argument("--before", default="")
    parser.add_argument("--after", default="")
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--default-ref", default="")
    parser.add_argument("--ref-name", default="")
    parser.add_argument("--default-branch", default="")
    args = parser.parse_args(argv)
    try:
        print(
            resolve_range(
                args.repo, **{k: v for k, v in vars(args).items() if k != "repo"}
            )
        )
    except (OSError, RangeError):
        print(
            "FATAL: secret scan range could not be resolved; failing closed.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
