#!/usr/bin/python3 -I
"""Recover and verify Qdrant snapshots inside the isolated DR network."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


BASE_URL = "http://qdrant:6333"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_POINTS = 5_000_000
COLLECTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
TOKEN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SNAPSHOT_RE = re.compile(r"^qdrant/[A-Za-z0-9_.-]+\.snapshot$")


class DrillError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise DrillError("redirect_forbidden")


def _stable_fields(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DrillError("duplicate_json_key")
        result[key] = value
    return result


def _request(
    path: str,
    api_key: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    if not path.startswith("/") or ".." in path or "//" in path:
        raise DrillError("invalid_api_path")
    data = (
        None
        if payload is None
        else json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    )
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"api-key": api_key, "Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            if response.status != 200:
                raise DrillError("unexpected_http_status")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DrillError("qdrant_request_failed") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise DrillError("qdrant_response_too_large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DrillError("qdrant_response_invalid") from exc
    if not isinstance(value, dict) or value.get("status") != "ok":
        raise DrillError("qdrant_response_not_ok")
    return value


def _wait_ready(api_key: str) -> None:
    for _ in range(30):
        try:
            _request("/collections", api_key, timeout_seconds=2)
            return
        except DrillError:
            time.sleep(2)
    raise DrillError("qdrant_not_ready")


def _load_plan(path: Path) -> list[dict[str, Any]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise DrillError("plan_unreadable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > 256 * 1024
        ):
            raise DrillError("plan_unsafe")
        raw = b""
        while len(raw) < before.st_size:
            chunk = os.read(descriptor, before.st_size - len(raw))
            if not chunk:
                raise DrillError("plan_unsafe")
            raw += chunk
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        path_state = path.lstat()
    except OSError as exc:
        raise DrillError("plan_unsafe") from exc
    if (
        not path.is_absolute()
        or path.is_symlink()
        or _stable_fields(before) != _stable_fields(after)
        or _stable_fields(after) != _stable_fields(path_state)
    ):
        raise DrillError("plan_unsafe")
    try:
        plan = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DrillError("plan_invalid") from exc
    if not isinstance(plan, dict) or plan.get("mode") != "snapshot_and_rebuild":
        raise DrillError("snapshot_plan_required")
    collections = plan.get("collections")
    if not isinstance(collections, list) or not collections:
        raise DrillError("collections_invalid")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in collections:
        if not isinstance(item, dict):
            raise DrillError("collection_invalid")
        collection = item.get("collection_name")
        snapshot_path = item.get("snapshot_path")
        snapshot_sha = item.get("snapshot_sha256")
        expected = item.get("expected_points_count")
        tenant_key = item.get("tenant_payload_key")
        tenant_sha = item.get("tenant_counts_sha256")
        if (
            not isinstance(collection, str)
            or not COLLECTION_RE.fullmatch(collection)
            or collection in seen
            or not isinstance(snapshot_path, str)
            or not SNAPSHOT_RE.fullmatch(snapshot_path)
            or not isinstance(snapshot_sha, str)
            or not SHA256_RE.fullmatch(snapshot_sha)
            or not isinstance(expected, int)
            or isinstance(expected, bool)
            or expected < 0
            or expected > MAX_POINTS
            or not isinstance(tenant_key, str)
            or not TOKEN_RE.fullmatch(tenant_key)
            or not isinstance(tenant_sha, str)
            or not SHA256_RE.fullmatch(tenant_sha)
        ):
            raise DrillError("collection_invalid")
        seen.add(collection)
        validated.append(
            {
                "collection": collection,
                "snapshot_path": snapshot_path,
                "snapshot_sha256": snapshot_sha,
                "expected_points_count": expected,
                "tenant_payload_key": tenant_key,
                "tenant_counts_sha256": tenant_sha,
            }
        )
    return validated


def _recover(api_key: str, item: dict[str, Any]) -> None:
    collection = item["collection"]
    response = _request(
        f"/collections/{collection}/snapshots/recover?wait=true",
        api_key,
        method="PUT",
        payload={
            "location": f"file:///recovery/{item['snapshot_path']}",
            "checksum": item["snapshot_sha256"],
        },
    )
    if response.get("result") is not True:
        raise DrillError("snapshot_recovery_unconfirmed")


def _verify_collection(api_key: str, item: dict[str, Any]) -> None:
    collection = item["collection"]
    info = _request(f"/collections/{collection}", api_key)
    result = info.get("result")
    if (
        not isinstance(result, dict)
        or result.get("status") != "green"
        or result.get("points_count") != item["expected_points_count"]
    ):
        raise DrillError("collection_invariant_failed")

    counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    offset: str | int | None = None
    while True:
        payload: dict[str, Any] = {
            "limit": 256,
            "with_payload": [item["tenant_payload_key"]],
            "with_vector": False,
        }
        if offset is not None:
            payload["offset"] = offset
        page = _request(
            f"/collections/{collection}/points/scroll",
            api_key,
            method="POST",
            payload=payload,
        ).get("result")
        if not isinstance(page, dict) or not isinstance(page.get("points"), list):
            raise DrillError("scroll_response_invalid")
        for point in page["points"]:
            if not isinstance(point, dict):
                raise DrillError("scroll_point_invalid")
            point_id = point.get("id")
            point_key = json.dumps(point_id, sort_keys=True, separators=(",", ":"))
            if point_key in seen_ids:
                raise DrillError("duplicate_point_id")
            seen_ids.add(point_key)
            point_payload = point.get("payload")
            if not isinstance(point_payload, dict):
                raise DrillError("point_payload_invalid")
            tenant = point_payload.get(item["tenant_payload_key"], "__missing__")
            if not isinstance(tenant, str) or not 0 < len(tenant) <= 256:
                raise DrillError("tenant_payload_invalid")
            counts[tenant] += 1
            if len(seen_ids) > item["expected_points_count"]:
                raise DrillError("point_count_exceeded")
        next_offset = page.get("next_page_offset")
        if next_offset is None:
            break
        if next_offset == offset or not isinstance(next_offset, (str, int)):
            raise DrillError("scroll_offset_invalid")
        offset = next_offset
    if len(seen_ids) != item["expected_points_count"]:
        raise DrillError("point_count_mismatch")
    digest = hashlib.sha256(
        (
            json.dumps(
                dict(sorted(counts.items())), separators=(",", ":"), ensure_ascii=True
            )
            + "\n"
        ).encode("ascii")
    ).hexdigest()
    if digest != item["tenant_counts_sha256"]:
        raise DrillError("tenant_counts_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    api_key = os.environ.pop("QDRANT_API_KEY", "")
    if not 32 <= len(api_key) <= 256 or any(
        ord(char) < 33 or ord(char) > 126 for char in api_key
    ):
        print('{"component":"dr_qdrant","reason":"api_key_invalid","status":"blocked"}')
        return 2
    try:
        collections = _load_plan(args.plan)
        _wait_ready(api_key)
        for item in collections:
            _recover(api_key, item)
            _verify_collection(api_key, item)
    except DrillError as exc:
        reason = str(exc) if TOKEN_RE.fullmatch(str(exc)) else "qdrant_drill_failed"
        print(
            json.dumps(
                {"component": "dr_qdrant", "reason": reason, "status": "blocked"},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(
        json.dumps(
            {
                "component": "dr_qdrant",
                "reason": "collections_verified",
                "status": "ok",
                "metrics": {"collections": len(collections)},
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
