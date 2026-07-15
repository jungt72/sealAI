"""Plan, build, and verify isolated Qdrant candidates from canonical Postgres state.

There is intentionally no alias, cutover, delete, rename, or production-collection mutation
operation in this module.  Execution requires an imported threshold-signed Gate-08 approval bound
to the exact plan and snapshot.  A second read-only snapshot must still match before candidates can
be reported as verified.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, NoReturn

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from sealai_v2.db.memory_store import memory_row_projection_payload
from sealai_v2.db.models import (
    V2KnowledgeAuthorityEpoch,
    V2KnowledgeClaim,
    V2KnowledgeDocument,
    V2MemoryItem,
)
from sealai_v2.knowledge.authority import AUTHORITY_SCOPE
from sealai_v2.knowledge.ledger import claim_projection_payload
from sealai_v2.knowledge.outbox_worker import build_knowledge_projection_point
from sealai_v2.memory.outbox_worker import build_memory_projection_point


SCHEMA_VERSION = 1
MAX_POINTS = 5_000_000
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024
MAX_PLAN_BYTES = 512 * 1024
MAX_BATCH_SIZE = 256
LOCAL_FAKE_MODEL_ID_SHA256 = hashlib.sha256(
    b"sealai-local-fake-embedder-v1"
).hexdigest()
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
COLLECTION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SNAPSHOT_KEYS = {
    "schema_version",
    "snapshot_kind",
    "captured_at",
    "database_identity_sha256",
    "transaction_snapshot_sha256",
    "authority_sequence",
    "knowledge",
    "memory",
}
RECORD_KEYS = {"id", "tenant_id", "payload"}
PLAN_KEYS = {
    "schema_version",
    "status",
    "run_id",
    "created_at",
    "snapshot_sha256",
    "source_fingerprint_sha256",
    "production_collections_sha256",
    "embedder",
    "index_schema",
    "collections",
}
COLLECTION_PLAN_KEYS = {
    "logical_id",
    "candidate_collection",
    "points_count",
    "ids_sha256",
    "payloads_sha256",
    "tenant_counts_sha256",
}
EMBEDDER_KEYS = {"kind", "model_id_sha256", "vector_size", "passage_prefix"}
INDEX_SCHEMA_KEYS = {"knowledge_vectors", "memory_vectors"}
MEMORY_SNAPSHOT_PAYLOAD_KEYS = {
    "id",
    "tenant_id",
    "owner_subject",
    "scope",
    "scope_id",
    "status",
    "version",
    "type",
    "semantic_key",
    "content",
}


class RebuildError(RuntimeError):
    def __init__(self, reason: str) -> None:
        safe = (
            reason if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason) else "rebuild_error"
        )
        super().__init__(safe)
        self.reason = safe


def _fail(reason: str) -> NoReturn:
    raise RebuildError(reason)


def _canonical_json(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RebuildError("noncanonical_json_value") from exc
    return (rendered + "\n").encode("ascii")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_object(value: Any, keys: set[str], *, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(reason)
    return value


def _require_sha(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(reason)
    return value


def _timestamp(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or RFC3339_RE.fullmatch(value) is None:
        _fail(reason)
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise RebuildError(reason) from exc
    return value


def _positive(value: Any, *, maximum: int, reason: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        or value > maximum
    ):
        _fail(reason)
    return value


def _receipt_module():
    name = "sealai_qdrant_rebuild_dr_receipts"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    candidates = (
        Path(__file__).resolve().parents[3] / "ops" / "dr_receipts.py",
        Path("/opt/dr/dr_receipts.py"),
        Path("/usr/local/libexec/sealai/dr_receipts.py"),
    )
    helper = next((path for path in candidates if path.is_file()), None)
    if helper is None:
        _fail("receipt_verifier_unavailable")
    try:
        metadata = helper.lstat()
    except OSError as exc:
        raise RebuildError("receipt_verifier_unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _fail("receipt_verifier_unsafe")
    spec = importlib.util.spec_from_file_location(name, helper)
    if spec is None or spec.loader is None:
        _fail("receipt_verifier_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except (OSError, ImportError) as exc:
        raise RebuildError("receipt_verifier_unavailable") from exc
    return module


def _read_json(path: Path, *, maximum_bytes: int, reason: str) -> Any:
    receipts = _receipt_module()
    try:
        raw = receipts._read_bound_file(
            path, private=True, maximum_bytes=maximum_bytes, reason=reason
        )
        value = receipts._parse_json(raw, reason=reason)
    except receipts.ReceiptError as exc:
        raise RebuildError(reason) from exc
    if _canonical_json(value) != raw:
        _fail("noncanonical_rebuild_artifact")
    return value


def _exclusive_json(path: Path, value: Any) -> None:
    receipts = _receipt_module()
    try:
        directory_fd = receipts._open_directory(path.parent, private_leaf=True)
    except receipts.ReceiptError as exc:
        raise RebuildError("artifact_directory_unsafe") from exc
    try:
        receipts._exclusive_write(directory_fd, path.name, _canonical_json(value))
    except receipts.ReceiptError as exc:
        raise RebuildError("artifact_already_exists") from exc
    finally:
        os.close(directory_fd)


def _projected_payload(logical_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if logical_id == "knowledge":
        return payload
    if logical_id == "memory":
        from sealai_v2.memory.outbox_worker import memory_qdrant_payload

        return memory_qdrant_payload(payload)
    _fail("invalid_logical_collection")


def _validate_records(value: Any, *, logical_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_POINTS:
        _fail("invalid_snapshot_records")
    records: list[dict[str, Any]] = []
    previous: tuple[str, str] | None = None
    seen: set[str] = set()
    for raw in value:
        record = _require_object(raw, RECORD_KEYS, reason="invalid_snapshot_record")
        identifier = record["id"]
        tenant_id = record["tenant_id"]
        payload = record["payload"]
        if (
            not isinstance(identifier, str)
            or not identifier
            or len(identifier) > 128
            or not isinstance(tenant_id, str)
            or not tenant_id
            or len(tenant_id) > 255
            or not isinstance(payload, dict)
        ):
            _fail("invalid_snapshot_record")
        if identifier in seen:
            _fail("duplicate_snapshot_id")
        seen.add(identifier)
        order = (tenant_id, identifier)
        if previous is not None and order <= previous:
            _fail("snapshot_order_invalid")
        previous = order
        if payload.get("tenant_id") != tenant_id:
            _fail("snapshot_tenant_mismatch")
        if logical_id == "knowledge":
            if payload.get("claim_id") != identifier or not isinstance(
                payload.get("claim_text"), str
            ):
                _fail("invalid_knowledge_projection")
        elif (
            set(payload) != MEMORY_SNAPSHOT_PAYLOAD_KEYS
            or payload.get("id") != identifier
        ):
            _fail("invalid_memory_projection")
        records.append(record)
    return records


def validate_snapshot(value: Any) -> dict[str, Any]:
    snapshot = _require_object(value, SNAPSHOT_KEYS, reason="invalid_snapshot_schema")
    if snapshot["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_snapshot_version")
    if snapshot["snapshot_kind"] != "postgres_repeatable_read_read_only":
        _fail("invalid_snapshot_kind")
    _timestamp(snapshot["captured_at"], reason="invalid_snapshot_time")
    _require_sha(
        snapshot["database_identity_sha256"], reason="invalid_database_identity"
    )
    _require_sha(
        snapshot["transaction_snapshot_sha256"], reason="invalid_transaction_snapshot"
    )
    _positive(
        snapshot["authority_sequence"],
        maximum=2**63 - 1,
        reason="invalid_authority_sequence",
    )
    _validate_records(snapshot["knowledge"], logical_id="knowledge")
    _validate_records(snapshot["memory"], logical_id="memory")
    return snapshot


def source_fingerprint(snapshot: dict[str, Any]) -> str:
    validate_snapshot(snapshot)
    return _sha(
        {
            "authority_sequence": snapshot["authority_sequence"],
            "knowledge": snapshot["knowledge"],
            "memory": snapshot["memory"],
        }
    )


def _collection_contract(
    logical_id: str, records: list[dict[str, Any]], candidate: str
) -> dict[str, Any]:
    projected = sorted(
        (
            [record["id"], _projected_payload(logical_id, record["payload"])]
            for record in records
        ),
        key=lambda item: item[0],
    )
    ids = [identifier for identifier, _ in projected]
    tenant_counts: dict[str, int] = {}
    for record in records:
        tenant_hash = hashlib.sha256(record["tenant_id"].encode("utf-8")).hexdigest()
        tenant_counts[tenant_hash] = tenant_counts.get(tenant_hash, 0) + 1
    return {
        "logical_id": logical_id,
        "candidate_collection": candidate,
        "points_count": len(records),
        "ids_sha256": _sha(ids),
        "payloads_sha256": _sha(projected),
        "tenant_counts_sha256": _sha(tenant_counts),
    }


def build_plan(
    snapshot: dict[str, Any],
    *,
    run_id: str,
    created_at: str,
    embedder_kind: str,
    model_id_sha256: str,
    vector_size: int,
    passage_prefix: str,
    production_collections: tuple[str, ...],
) -> dict[str, Any]:
    snapshot = validate_snapshot(snapshot)
    if RUN_ID_RE.fullmatch(run_id) is None:
        _fail("invalid_run_id")
    _timestamp(created_at, reason="invalid_plan_time")
    if embedder_kind not in {"local_fake", "runtime_external"}:
        _fail("invalid_embedder_kind")
    _require_sha(model_id_sha256, reason="invalid_model_id")
    if embedder_kind == "local_fake" and model_id_sha256 != LOCAL_FAKE_MODEL_ID_SHA256:
        _fail("invalid_local_fake_model_id")
    _positive(vector_size, maximum=65536, reason="invalid_vector_size")
    if not isinstance(passage_prefix, str) or len(passage_prefix) > 64:
        _fail("invalid_passage_prefix")
    if (
        not production_collections
        or len(production_collections) != len(set(production_collections))
        or any(COLLECTION_RE.fullmatch(name) is None for name in production_collections)
    ):
        _fail("invalid_production_collections")
    collections = []
    for logical_id in ("knowledge", "memory"):
        candidate = f"sealai-dr-{run_id}-{logical_id}"
        if (
            COLLECTION_RE.fullmatch(candidate) is None
            or candidate in production_collections
            or not candidate.startswith(f"sealai-dr-{run_id}-")
        ):
            _fail("unsafe_candidate_collection")
        collections.append(
            _collection_contract(logical_id, snapshot[logical_id], candidate)
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PLAN_ONLY",
        "run_id": run_id,
        "created_at": created_at,
        "snapshot_sha256": _sha(snapshot),
        "source_fingerprint_sha256": source_fingerprint(snapshot),
        "production_collections_sha256": _sha(sorted(production_collections)),
        "embedder": {
            "kind": embedder_kind,
            "model_id_sha256": model_id_sha256,
            "vector_size": vector_size,
            "passage_prefix": passage_prefix,
        },
        "index_schema": {
            "knowledge_vectors": ["dense"],
            "memory_vectors": ["dense"],
        },
        "collections": collections,
    }


def validate_plan(value: Any) -> dict[str, Any]:
    plan = _require_object(value, PLAN_KEYS, reason="invalid_rebuild_plan_schema")
    if plan["schema_version"] != SCHEMA_VERSION or plan["status"] != "PLAN_ONLY":
        _fail("invalid_rebuild_plan_version")
    run_id = plan["run_id"]
    if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
        _fail("invalid_run_id")
    _timestamp(plan["created_at"], reason="invalid_plan_time")
    for name in (
        "snapshot_sha256",
        "source_fingerprint_sha256",
        "production_collections_sha256",
    ):
        _require_sha(plan[name], reason="invalid_rebuild_plan_digest")
    embedder = _require_object(
        plan["embedder"], EMBEDDER_KEYS, reason="invalid_embedder_contract"
    )
    if embedder["kind"] not in {"local_fake", "runtime_external"}:
        _fail("invalid_embedder_kind")
    _require_sha(embedder["model_id_sha256"], reason="invalid_model_id")
    if (
        embedder["kind"] == "local_fake"
        and embedder["model_id_sha256"] != LOCAL_FAKE_MODEL_ID_SHA256
    ):
        _fail("invalid_local_fake_model_id")
    _positive(embedder["vector_size"], maximum=65536, reason="invalid_vector_size")
    if (
        not isinstance(embedder["passage_prefix"], str)
        or len(embedder["passage_prefix"]) > 64
    ):
        _fail("invalid_passage_prefix")
    index_schema = _require_object(
        plan["index_schema"], INDEX_SCHEMA_KEYS, reason="invalid_index_schema"
    )
    if index_schema != {
        "knowledge_vectors": ["dense"],
        "memory_vectors": ["dense"],
    }:
        _fail("unsupported_index_schema")
    collections = plan["collections"]
    if not isinstance(collections, list) or len(collections) != 2:
        _fail("invalid_collection_plan")
    if [item.get("logical_id") for item in collections if isinstance(item, dict)] != [
        "knowledge",
        "memory",
    ]:
        _fail("invalid_collection_plan")
    for item in collections:
        collection = _require_object(
            item, COLLECTION_PLAN_KEYS, reason="invalid_collection_plan"
        )
        candidate = collection["candidate_collection"]
        if (
            not isinstance(candidate, str)
            or COLLECTION_RE.fullmatch(candidate) is None
            or not candidate.startswith(f"sealai-dr-{run_id}-")
        ):
            _fail("unsafe_candidate_collection")
        if (
            not isinstance(collection["points_count"], int)
            or isinstance(collection["points_count"], bool)
            or collection["points_count"] < 0
            or collection["points_count"] > MAX_POINTS
        ):
            _fail("invalid_points_count")
        for name in ("ids_sha256", "payloads_sha256", "tenant_counts_sha256"):
            _require_sha(collection[name], reason="invalid_collection_digest")
    return plan


def bind_plan_snapshot(
    plan: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    production_collections: tuple[str, ...],
) -> None:
    validate_plan(plan)
    validate_snapshot(snapshot)
    if plan["snapshot_sha256"] != _sha(snapshot):
        _fail("snapshot_digest_mismatch")
    if plan["source_fingerprint_sha256"] != source_fingerprint(snapshot):
        _fail("source_fingerprint_mismatch")
    if plan["production_collections_sha256"] != _sha(sorted(production_collections)):
        _fail("production_collection_contract_mismatch")
    production = set(production_collections)
    for expected, collection in zip(("knowledge", "memory"), plan["collections"]):
        if collection != _collection_contract(
            expected, snapshot[expected], collection["candidate_collection"]
        ):
            _fail("collection_plan_mismatch")
        if collection["candidate_collection"] in production:
            _fail("candidate_is_production_collection")


def candidate_collections_sha256(plan: dict[str, Any]) -> str:
    validate_plan(plan)
    return _sha([item["candidate_collection"] for item in plan["collections"]])


def verify_execute_approval(
    plan: dict[str, Any],
    approval_path: Path,
    trust_policy_path: Path,
    *,
    now: dt.datetime | None = None,
) -> None:
    receipts = _receipt_module()
    try:
        verified = receipts.verify_imported_receipt(
            approval_path,
            trust_policy_path,
            expected_kind="qdrant_rebuild_approval",
            now=now,
        )
    except receipts.ReceiptError as exc:
        raise RebuildError("rebuild_approval_invalid") from exc
    subject = verified.payload["subject"]
    if subject != {
        "gate_id": "GATE-08",
        "plan_sha256": _sha(plan),
        "snapshot_sha256": plan["snapshot_sha256"],
        "candidate_collections_sha256": candidate_collections_sha256(plan),
    }:
        _fail("rebuild_approval_mismatch")


class LocalFakeEmbedder:
    """Deterministic offline test embedder; never accepted without explicit local permission."""

    is_local_fake = True
    model_id_sha256 = LOCAL_FAKE_MODEL_ID_SHA256

    def __init__(self, vector_size: int) -> None:
        self.vector_size = _positive(
            vector_size, maximum=65536, reason="invalid_vector_size"
        )

    class _Vector:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def tolist(self) -> list[float]:
            return list(self._values)

    def embed(self, texts: list[str] | tuple[str, ...]):
        for value in texts:
            if not isinstance(value, str):
                _fail("invalid_embedding_input")
            seed = hashlib.sha256(value.encode("utf-8")).digest()
            values = [
                ((seed[index % len(seed)] / 255.0) * 2.0) - 1.0
                for index in range(self.vector_size)
            ]
            yield self._Vector(values)


class RebuildJournal:
    def __init__(self, root: Path, run_id: str, *, create: bool) -> None:
        if RUN_ID_RE.fullmatch(run_id) is None:
            _fail("invalid_run_id")
        receipts = _receipt_module()
        try:
            root_fd = receipts._open_directory(root, private_leaf=True)
        except receipts.ReceiptError as exc:
            raise RebuildError("journal_unavailable") from exc
        try:
            if create:
                try:
                    os.mkdir(run_id, 0o700, dir_fd=root_fd)
                    os.fsync(root_fd)
                except FileExistsError as exc:
                    raise RebuildError("rebuild_run_replay") from exc
                except OSError as exc:
                    raise RebuildError("journal_unavailable") from exc
        finally:
            os.close(root_fd)
        self.path = root / run_id
        try:
            self._directory_fd = receipts._open_directory(self.path, private_leaf=True)
        except receipts.ReceiptError as exc:
            raise RebuildError("journal_unavailable") from exc

    def close(self) -> None:
        if self._directory_fd >= 0:
            os.close(self._directory_fd)
            self._directory_fd = -1

    def append(self, sequence: int, event: str, payload: dict[str, Any]) -> None:
        if self._directory_fd < 0 or not 1 <= sequence <= 9999:
            _fail("journal_state_invalid")
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", event) is None:
            _fail("journal_event_invalid")
        record = {
            "schema_version": SCHEMA_VERSION,
            "sequence": sequence,
            "event": event,
            "payload": payload,
        }
        receipts = _receipt_module()
        try:
            receipts._exclusive_write(
                self._directory_fd,
                f"{sequence:04d}-{event}.json",
                _canonical_json(record),
            )
        except receipts.ReceiptError as exc:
            raise RebuildError("journal_replay") from exc

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


def _embed_records(
    records: list[dict[str, Any]],
    *,
    logical_id: str,
    embedder,
    vector_size: int,
    passage_prefix: str,
    batch_size: int,
):
    for offset in range(0, len(records), batch_size):
        batch = records[offset : offset + batch_size]
        texts = [
            (
                f"{passage_prefix}{record['payload']['claim_text']}"
                if logical_id == "knowledge"
                else record["payload"]["content"]
            )
            for record in batch
        ]
        vectors = list(embedder.embed(texts))
        if len(vectors) != len(batch):
            _fail("embedding_batch_incomplete")
        points = []
        for record, vector in zip(batch, vectors):
            values = vector.tolist()
            if len(values) != vector_size or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                for value in values
            ):
                _fail("embedding_vector_invalid")
            if logical_id == "knowledge":
                points.append(
                    build_knowledge_projection_point(
                        claim_id=record["id"],
                        payload=record["payload"],
                        dense_vector=values,
                    )
                )
            else:
                points.append(
                    build_memory_projection_point(
                        point_id=record["id"],
                        payload=record["payload"],
                        dense_vector=values,
                    )
                )
        yield points


def _create_candidate_collection(client, collection: str, vector_size: int) -> None:
    """Create this run's dense candidate, refusing idempotent/racy adoption."""

    from qdrant_client.models import Distance, VectorParams

    if client.collection_exists(collection):
        _fail("candidate_collection_not_empty_new")
    try:
        client.create_collection(
            collection,
            vectors_config={
                "dense": VectorParams(size=vector_size, distance=Distance.COSINE)
            },
            sparse_vectors_config=None,
        )
    except Exception as exc:  # noqa: BLE001 - any create ambiguity must fail closed
        raise RebuildError("candidate_collection_create_failed") from exc
    if not client.collection_exists(collection):
        _fail("candidate_collection_create_failed")


def execute_rebuild(
    plan: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    approval_path: Path,
    trust_policy_path: Path,
    qdrant_client,
    embedder,
    production_collections: tuple[str, ...],
    journal_root: Path,
    batch_size: int = 64,
    allow_local_fake: bool = False,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    bind_plan_snapshot(plan, snapshot, production_collections=production_collections)
    verify_execute_approval(plan, approval_path, trust_policy_path, now=now)
    _positive(batch_size, maximum=MAX_BATCH_SIZE, reason="invalid_batch_size")
    fake = bool(getattr(embedder, "is_local_fake", False))
    if fake != (plan["embedder"]["kind"] == "local_fake"):
        _fail("embedder_contract_mismatch")
    if fake and not allow_local_fake:
        _fail("local_fake_embedder_not_authorized")
    if (
        not fake
        and getattr(embedder, "dr_rebuild_admission_verified", False) is not True
    ):
        _fail("external_embedder_not_admitted")
    if (
        getattr(embedder, "model_id_sha256", None)
        != plan["embedder"]["model_id_sha256"]
    ):
        _fail("embedder_model_mismatch")
    vector_size = plan["embedder"]["vector_size"]
    production = set(production_collections)
    with RebuildJournal(journal_root, plan["run_id"], create=True) as journal:
        journal.append(
            1,
            "execution_started",
            {
                "plan_sha256": _sha(plan),
                "snapshot_sha256": _sha(snapshot),
                "candidate_collections_sha256": candidate_collections_sha256(plan),
            },
        )
        sequence = 2
        built: dict[str, int] = {}
        for contract in plan["collections"]:
            logical_id = contract["logical_id"]
            candidate = contract["candidate_collection"]
            if candidate in production or qdrant_client.collection_exists(candidate):
                _fail("candidate_collection_not_empty_new")
            _create_candidate_collection(qdrant_client, candidate, vector_size)
            info = qdrant_client.get_collection(candidate)
            existing_points = int(getattr(info, "points_count", 0) or 0)
            if existing_points != 0:
                _fail("candidate_collection_not_empty_new")
            written = 0
            for points in _embed_records(
                snapshot[logical_id],
                logical_id=logical_id,
                embedder=embedder,
                vector_size=vector_size,
                passage_prefix=plan["embedder"]["passage_prefix"],
                batch_size=batch_size,
            ):
                qdrant_client.upsert(candidate, points=points, wait=True)
                written += len(points)
            if written != contract["points_count"]:
                _fail("candidate_write_count_mismatch")
            built[logical_id] = written
            journal.append(
                sequence,
                "candidate_built",
                {
                    "logical_id": logical_id,
                    "candidate_collection_sha256": hashlib.sha256(
                        candidate.encode("ascii")
                    ).hexdigest(),
                    "points_count": written,
                },
            )
            sequence += 1
        journal.append(
            sequence,
            "execution_completed",
            {"status": "CANDIDATES_BUILT_NOT_CUTOVER", "points": built},
        )
    return {"status": "CANDIDATES_BUILT_NOT_CUTOVER", "points": built}


def _all_points(client, collection: str) -> list[Any]:
    points: list[Any] = []
    offset = None
    while True:
        page, next_offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        points.extend(page)
        if len(points) > MAX_POINTS:
            _fail("candidate_points_unbounded")
        if next_offset is None:
            return points
        if next_offset == offset:
            _fail("candidate_scroll_stalled")
        offset = next_offset


def _validate_dense_vector(point: Any, *, vector_size: int) -> None:
    vectors = getattr(point, "vector", None)
    if not isinstance(vectors, dict) or set(vectors) != {"dense"}:
        _fail("candidate_vector_contract_mismatch")
    dense = vectors["dense"]
    if (
        not isinstance(dense, list)
        or len(dense) != vector_size
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in dense
        )
    ):
        _fail("candidate_vector_contract_mismatch")


def _require_execution_journal(
    plan: dict[str, Any], snapshot: dict[str, Any], journal_root: Path
) -> None:
    run_directory = journal_root / plan["run_id"]
    receipts = _receipt_module()
    try:
        directory_fd = receipts._open_directory(run_directory, private_leaf=True)
    except receipts.ReceiptError as exc:
        raise RebuildError("journal_unavailable") from exc
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        raise RebuildError("journal_unavailable") from exc
    finally:
        os.close(directory_fd)
    expected_names = [
        "0001-execution_started.json",
        "0002-candidate_built.json",
        "0003-candidate_built.json",
        "0004-execution_completed.json",
    ]
    if names != expected_names:
        _fail("execution_journal_incomplete")
    records = [
        _read_json(
            run_directory / name,
            maximum_bytes=MAX_PLAN_BYTES,
            reason="invalid_journal_record",
        )
        for name in names
    ]
    for sequence, event, record in zip(
        range(1, 5),
        (
            "execution_started",
            "candidate_built",
            "candidate_built",
            "execution_completed",
        ),
        records,
    ):
        _require_object(
            record,
            {"schema_version", "sequence", "event", "payload"},
            reason="invalid_journal_record",
        )
        if (
            record["schema_version"] != SCHEMA_VERSION
            or record["sequence"] != sequence
            or record["event"] != event
            or not isinstance(record["payload"], dict)
        ):
            _fail("invalid_journal_record")
    if records[0]["payload"] != {
        "plan_sha256": _sha(plan),
        "snapshot_sha256": _sha(snapshot),
        "candidate_collections_sha256": candidate_collections_sha256(plan),
    }:
        _fail("execution_journal_mismatch")
    built: dict[str, int] = {}
    for contract, record in zip(plan["collections"], records[1:3]):
        logical_id = contract["logical_id"]
        points_count = contract["points_count"]
        if record["payload"] != {
            "logical_id": logical_id,
            "candidate_collection_sha256": hashlib.sha256(
                contract["candidate_collection"].encode("ascii")
            ).hexdigest(),
            "points_count": points_count,
        }:
            _fail("execution_journal_mismatch")
        built[logical_id] = points_count
    if records[3]["payload"] != {
        "status": "CANDIDATES_BUILT_NOT_CUTOVER",
        "points": built,
    }:
        _fail("execution_journal_mismatch")


def verify_candidates(
    plan: dict[str, Any],
    snapshot: dict[str, Any],
    current_snapshot: dict[str, Any],
    *,
    qdrant_client,
    production_collections: tuple[str, ...],
    journal_root: Path,
) -> dict[str, Any]:
    bind_plan_snapshot(plan, snapshot, production_collections=production_collections)
    validate_snapshot(current_snapshot)
    if (
        current_snapshot["database_identity_sha256"]
        != snapshot["database_identity_sha256"]
    ):
        _fail("postgres_database_identity_mismatch")
    if (
        current_snapshot["captured_at"] <= snapshot["captured_at"]
        or current_snapshot["transaction_snapshot_sha256"]
        == snapshot["transaction_snapshot_sha256"]
    ):
        _fail("current_snapshot_not_fresh")
    if source_fingerprint(current_snapshot) != plan["source_fingerprint_sha256"]:
        _fail("postgres_source_drift")
    _require_execution_journal(plan, snapshot, journal_root)
    production = set(production_collections)
    verified_counts: dict[str, int] = {}
    for contract in plan["collections"]:
        logical_id = contract["logical_id"]
        candidate = contract["candidate_collection"]
        if candidate in production or not qdrant_client.collection_exists(candidate):
            _fail("candidate_collection_missing")
        points = _all_points(qdrant_client, candidate)
        for point in points:
            _validate_dense_vector(point, vector_size=plan["embedder"]["vector_size"])
        material = sorted(
            ((str(point.id), dict(point.payload or {})) for point in points),
            key=lambda item: item[0],
        )
        ids = [identifier for identifier, _ in material]
        tenant_counts: dict[str, int] = {}
        for _, payload in material:
            tenant_id = payload.get("tenant_id")
            if not isinstance(tenant_id, str) or not tenant_id:
                _fail("candidate_tenant_missing")
            tenant_hash = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()
            tenant_counts[tenant_hash] = tenant_counts.get(tenant_hash, 0) + 1
        if (
            len(material) != contract["points_count"]
            or _sha(ids) != contract["ids_sha256"]
            or _sha([[identifier, payload] for identifier, payload in material])
            != contract["payloads_sha256"]
            or _sha(tenant_counts) != contract["tenant_counts_sha256"]
        ):
            _fail("candidate_verification_mismatch")
        verified_counts[logical_id] = len(material)
    with RebuildJournal(journal_root, plan["run_id"], create=False) as journal:
        journal.append(
            5,
            "candidates_verified",
            {
                "status": "CANDIDATES_VERIFIED_NO_CUTOVER",
                "source_fingerprint_sha256": source_fingerprint(current_snapshot),
                "points": verified_counts,
            },
        )
    return {"status": "CANDIDATES_VERIFIED_NO_CUTOVER", "points": verified_counts}


def capture_postgres_snapshot(engine, *, captured_at: str) -> dict[str, Any]:
    """Capture both projections inside one PostgreSQL read-only repeatable-read transaction."""

    _timestamp(captured_at, reason="invalid_snapshot_time")
    if engine.dialect.name != "postgresql":
        _fail("postgres_required")
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY DEFERRABLE"
            )
            database_name, database_user = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
            transaction_snapshot = connection.execute(
                text("SELECT txid_current_snapshot()::text")
            ).scalar_one()
            session = Session(bind=connection, autoflush=False, expire_on_commit=False)
            try:
                authority = session.get(V2KnowledgeAuthorityEpoch, AUTHORITY_SCOPE)
                if authority is None or authority.sequence <= 0:
                    _fail("authority_epoch_unavailable")
                knowledge_rows = session.execute(
                    select(V2KnowledgeClaim, V2KnowledgeDocument)
                    .join(
                        V2KnowledgeDocument,
                        V2KnowledgeDocument.id == V2KnowledgeClaim.document_id,
                    )
                    .where(V2KnowledgeClaim.active.is_(True))
                    .order_by(V2KnowledgeClaim.tenant_id, V2KnowledgeClaim.id)
                ).all()
                memory_rows = session.scalars(
                    select(V2MemoryItem).order_by(
                        V2MemoryItem.tenant_id, V2MemoryItem.id
                    )
                ).all()
                snapshot = {
                    "schema_version": SCHEMA_VERSION,
                    "snapshot_kind": "postgres_repeatable_read_read_only",
                    "captured_at": captured_at,
                    "database_identity_sha256": _sha(
                        {"database": database_name, "user": database_user}
                    ),
                    "transaction_snapshot_sha256": hashlib.sha256(
                        str(transaction_snapshot).encode("ascii")
                    ).hexdigest(),
                    "authority_sequence": authority.sequence,
                    "knowledge": [
                        {
                            "id": claim.id,
                            "tenant_id": claim.tenant_id,
                            "payload": claim_projection_payload(claim, document),
                        }
                        for claim, document in knowledge_rows
                    ],
                    "memory": [
                        {
                            "id": row.id,
                            "tenant_id": row.tenant_id,
                            "payload": memory_row_projection_payload(row),
                        }
                        for row in memory_rows
                    ],
                }
                return validate_snapshot(snapshot)
            finally:
                session.close()
        finally:
            transaction.rollback()


def _path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("absolute path required")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("capture-snapshot")
    snapshot.add_argument("--database-url-env", default="SEALAI_V2_DATABASE_URL")
    snapshot.add_argument("--snapshot", required=True, type=_path)
    snapshot.add_argument("--captured-at", required=True)

    capture = commands.add_parser("capture-plan")
    capture.add_argument("--database-url-env", default="SEALAI_V2_DATABASE_URL")
    capture.add_argument("--snapshot", required=True, type=_path)
    capture.add_argument("--plan", required=True, type=_path)
    capture.add_argument("--run-id", required=True)
    capture.add_argument("--created-at", required=True)
    capture.add_argument(
        "--embedder-kind", choices=("local_fake", "runtime_external"), required=True
    )
    capture.add_argument("--model-id-sha256", required=True)
    capture.add_argument("--vector-size", required=True, type=int)
    capture.add_argument("--passage-prefix", default="")
    capture.add_argument("--production-collection", action="append", required=True)

    execute = commands.add_parser("execute-local-fake")
    execute.add_argument("--plan", required=True, type=_path)
    execute.add_argument("--snapshot", required=True, type=_path)
    execute.add_argument("--approval", required=True, type=_path)
    execute.add_argument("--trust-policy", required=True, type=_path)
    execute.add_argument("--journal-root", required=True, type=_path)
    execute.add_argument("--qdrant-url", required=True)
    execute.add_argument("--production-collection", action="append", required=True)
    execute.add_argument("--ephemeral-only", action="store_true")

    verify = commands.add_parser("verify")
    verify.add_argument("--plan", required=True, type=_path)
    verify.add_argument("--snapshot", required=True, type=_path)
    verify.add_argument("--current-snapshot", required=True, type=_path)
    verify.add_argument("--journal-root", required=True, type=_path)
    verify.add_argument("--qdrant-url", required=True)
    verify.add_argument("--production-collection", action="append", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"capture-plan", "capture-snapshot"}:
            from sealai_v2.db.engine import make_engine

            if ENV_NAME_RE.fullmatch(args.database_url_env) is None:
                _fail("invalid_database_url_env")
            database_url = os.environ.get(args.database_url_env, "")
            if not database_url:
                _fail("database_url_unavailable")
            snapshot = capture_postgres_snapshot(
                make_engine(database_url),
                captured_at=(
                    args.created_at
                    if args.command == "capture-plan"
                    else args.captured_at
                ),
            )
            if args.command == "capture-plan":
                plan = build_plan(
                    snapshot,
                    run_id=args.run_id,
                    created_at=args.created_at,
                    embedder_kind=args.embedder_kind,
                    model_id_sha256=args.model_id_sha256,
                    vector_size=args.vector_size,
                    passage_prefix=args.passage_prefix,
                    production_collections=tuple(args.production_collection),
                )
                _exclusive_json(args.snapshot, snapshot)
                _exclusive_json(args.plan, plan)
                result = {"status": "PLAN_ONLY", "plan_sha256": _sha(plan)}
            else:
                _exclusive_json(args.snapshot, snapshot)
                result = {
                    "status": "SNAPSHOT_CAPTURED_READ_ONLY",
                    "snapshot_sha256": _sha(snapshot),
                }
        else:
            from qdrant_client import QdrantClient

            if not re.fullmatch(
                r"https?://(127\.0\.0\.1|localhost)(:\d+)?", args.qdrant_url
            ):
                _fail("qdrant_endpoint_not_ephemeral_local")
            client = QdrantClient(url=args.qdrant_url)
            plan = validate_plan(
                _read_json(
                    args.plan, maximum_bytes=MAX_PLAN_BYTES, reason="invalid_plan_file"
                )
            )
            snapshot = validate_snapshot(
                _read_json(
                    args.snapshot,
                    maximum_bytes=MAX_SNAPSHOT_BYTES,
                    reason="invalid_snapshot_file",
                )
            )
            if args.command == "execute-local-fake":
                if not args.ephemeral_only:
                    _fail("ephemeral_confirmation_required")
                result = execute_rebuild(
                    plan,
                    snapshot,
                    approval_path=args.approval,
                    trust_policy_path=args.trust_policy,
                    qdrant_client=client,
                    embedder=LocalFakeEmbedder(plan["embedder"]["vector_size"]),
                    production_collections=tuple(args.production_collection),
                    journal_root=args.journal_root,
                    allow_local_fake=True,
                )
            else:
                current = validate_snapshot(
                    _read_json(
                        args.current_snapshot,
                        maximum_bytes=MAX_SNAPSHOT_BYTES,
                        reason="invalid_current_snapshot_file",
                    )
                )
                result = verify_candidates(
                    plan,
                    snapshot,
                    current,
                    qdrant_client=client,
                    production_collections=tuple(args.production_collection),
                    journal_root=args.journal_root,
                )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except RebuildError as exc:
        print(
            json.dumps(
                {"reason": exc.reason, "status": "blocked"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
