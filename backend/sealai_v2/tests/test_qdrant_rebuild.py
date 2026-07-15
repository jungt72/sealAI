from __future__ import annotations

import base64
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from types import ModuleType
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sealai_v2.knowledge import qdrant_rebuild as rebuild


@pytest.fixture(autouse=True)
def _qdrant_models(monkeypatch):
    """Exercise the production point builders without requiring a live client package."""

    package = ModuleType("qdrant_client")
    package.__path__ = []
    models = ModuleType("qdrant_client.models")

    class Distance:
        COSINE = "cosine"

    class Modifier:
        IDF = "idf"

    class VectorParams:
        def __init__(self, *, size, distance):
            self.size = size
            self.distance = distance

    class SparseVectorParams:
        def __init__(self, *, modifier):
            self.modifier = modifier

    class PointStruct:
        def __init__(self, *, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    models.Distance = Distance
    models.Modifier = Modifier
    models.VectorParams = VectorParams
    models.SparseVectorParams = SparseVectorParams
    models.PointStruct = PointStruct
    package.models = models
    monkeypatch.setitem(sys.modules, "qdrant_client", package)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", models)


def _record_id(index: int) -> str:
    return str(uuid.UUID(int=index + 1))


def _snapshot() -> dict:
    knowledge_id = _record_id(1)
    memory_id = _record_id(2)
    return {
        "schema_version": 1,
        "snapshot_kind": "postgres_repeatable_read_read_only",
        "captured_at": "2026-07-15T12:00:00Z",
        "database_identity_sha256": "1" * 64,
        "transaction_snapshot_sha256": "2" * 64,
        "authority_sequence": 7,
        "knowledge": [
            {
                "id": knowledge_id,
                "tenant_id": "sealai",
                "payload": {
                    "claim_id": knowledge_id,
                    "tenant_id": "sealai",
                    "claim_text": "PTFE is a technical test claim.",
                    "review_status": "approved",
                    "version": 3,
                },
            }
        ],
        "memory": [
            {
                "id": memory_id,
                "tenant_id": "tenant-a",
                "payload": {
                    "id": memory_id,
                    "tenant_id": "tenant-a",
                    "owner_subject": "subject-a",
                    "scope": "case",
                    "scope_id": "case-a",
                    "status": "confirmed",
                    "version": 2,
                    "type": "preference",
                    "semantic_key": "preferred-material",
                    "content": "Use the tenant-approved material preference.",
                },
            }
        ],
    }


def _plan(snapshot: dict, *, run_id: str = "drtest-001") -> dict:
    return rebuild.build_plan(
        snapshot,
        run_id=run_id,
        created_at="2026-07-15T12:00:00Z",
        embedder_kind="local_fake",
        model_id_sha256=rebuild.LOCAL_FAKE_MODEL_ID_SHA256,
        vector_size=8,
        passage_prefix="passage: ",
        production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
    )


class FakeQdrant:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, object]] = {}
        self.forbidden_calls: list[str] = []

    def collection_exists(self, name: str) -> bool:
        return name in self.collections

    def create_collection(
        self, name: str, *, vectors_config, sparse_vectors_config=None
    ) -> None:
        if name in self.collections:
            raise RuntimeError("collection already exists")
        self.collections[name] = {
            "size": vectors_config["dense"].size,
            "points": {},
            "sparse": sparse_vectors_config or {},
        }

    def get_collection(self, name: str):
        collection = self.collections[name]
        return SimpleNamespace(
            points_count=len(collection["points"]),
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={"dense": SimpleNamespace(size=collection["size"])},
                    sparse_vectors=collection["sparse"],
                )
            ),
        )

    def upsert(self, name: str, *, points, wait: bool) -> None:
        assert wait is True
        target = self.collections[name]["points"]
        for point in points:
            target[str(point.id)] = SimpleNamespace(
                id=str(point.id),
                payload=dict(point.payload or {}),
                vector=dict(point.vector or {}),
            )

    def scroll(
        self,
        *,
        collection_name: str,
        limit: int,
        offset,
        with_payload: bool,
        with_vectors: bool,
    ):
        assert limit == 256
        assert with_payload is True and with_vectors is True
        values = sorted(
            self.collections[collection_name]["points"].values(),
            key=lambda point: point.id,
        )
        start = int(offset or 0)
        page = values[start : start + limit]
        next_offset = start + len(page) if start + len(page) < len(values) else None
        return page, next_offset

    def delete(self, *_args, **_kwargs):
        self.forbidden_calls.append("delete")
        raise AssertionError("rebuild must never delete")

    def update_collection_aliases(self, *_args, **_kwargs):
        self.forbidden_calls.append("aliases")
        raise AssertionError("rebuild must never mutate aliases")


def _approval(plan: dict, directory: Path):
    receipts = rebuild._receipt_module()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    signers = []
    keys = []
    for _ in range(2):
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        keyid = hashlib.sha256(public).hexdigest()
        signers.append((keyid, private))
        keys.append(
            {
                "keyid": keyid,
                "algorithm": "ed25519",
                "public_key_base64": base64.b64encode(public).decode("ascii"),
                "not_before": (now - dt.timedelta(days=1)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "not_after": (now + dt.timedelta(days=30)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            }
        )
    keyids = [item["keyid"] for item in keys]
    policy = {
        "schema_version": 1,
        "policy_id": hashlib.sha256(b"rebuild-test-policy").hexdigest(),
        "valid_from": (now - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "max_receipt_age_seconds": 86400,
        "max_receipt_validity_seconds": 3600,
        "keys": keys,
        "roles": {"rebuild_approver": {"threshold": 2, "keyids": keyids}},
    }
    subject = {
        "gate_id": "GATE-08",
        "plan_sha256": rebuild._sha(plan),
        "snapshot_sha256": plan["snapshot_sha256"],
        "candidate_collections_sha256": rebuild.candidate_collections_sha256(plan),
    }
    payload = {
        "schema_version": 1,
        "kind": "qdrant_rebuild_approval",
        "role": "rebuild_approver",
        "status": "REBUILD_APPROVED",
        "issued_at": (now - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + dt.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subject": subject,
    }
    payload["receipt_id"] = hashlib.sha256(
        receipts._canonical_json(payload)
    ).hexdigest()
    raw = receipts._canonical_json(payload)
    pae = receipts._pae(receipts.PAYLOAD_TYPE.encode("ascii"), raw)
    envelope = {
        "payloadType": receipts.PAYLOAD_TYPE,
        "payload": base64.b64encode(raw).decode("ascii"),
        "signatures": [
            {
                "keyid": keyid,
                "sig": base64.b64encode(private.sign(pae)).decode("ascii"),
            }
            for keyid, private in signers
        ],
    }
    policy_path = directory / "trust-policy.json"
    envelope_path = directory / "approval.dsse.json"
    policy_path.write_bytes(receipts._canonical_json(policy))
    envelope_path.write_bytes(receipts._canonical_json(envelope))
    os.chmod(policy_path, 0o600)
    os.chmod(envelope_path, 0o600)
    store = directory / "approvals"
    approval = receipts.import_receipt(
        envelope_path,
        policy_path,
        store,
        expected_kind="qdrant_rebuild_approval",
        now=now,
    )
    return approval, policy_path, now


def _execute(tmp_path: Path, *, run_id: str = "drtest-001"):
    snapshot = _snapshot()
    plan = _plan(snapshot, run_id=run_id)
    approval, policy, now = _approval(plan, tmp_path)
    journal = tmp_path / "journal"
    journal.mkdir(mode=0o700)
    client = FakeQdrant()
    result = rebuild.execute_rebuild(
        plan,
        snapshot,
        approval_path=approval,
        trust_policy_path=policy,
        qdrant_client=client,
        embedder=rebuild.LocalFakeEmbedder(8),
        production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
        journal_root=journal,
        allow_local_fake=True,
        now=now,
    )
    return snapshot, plan, journal, client, result


def test_plan_is_deterministic_bound_and_candidate_only() -> None:
    snapshot = _snapshot()
    first = _plan(snapshot)
    second = _plan(copy.deepcopy(snapshot))
    assert first == second
    assert first["status"] == "PLAN_ONLY"
    assert first["index_schema"] == {
        "knowledge_vectors": ["dense"],
        "memory_vectors": ["dense"],
    }
    assert [item["candidate_collection"] for item in first["collections"]] == [
        "sealai-dr-drtest-001-knowledge",
        "sealai-dr-drtest-001-memory",
    ]
    assert first["snapshot_sha256"] == rebuild._sha(snapshot)
    assert all(
        "sealai_v2" not in item["candidate_collection"] for item in first["collections"]
    )

    tampered = copy.deepcopy(snapshot)
    tampered["memory"][0]["payload"]["content"] = "drift"
    with pytest.raises(rebuild.RebuildError, match="snapshot_digest_mismatch"):
        rebuild.bind_plan_snapshot(
            first,
            tampered,
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
        )


def test_execute_builds_only_empty_run_candidates_and_journals(tmp_path: Path) -> None:
    snapshot, plan, journal, client, result = _execute(tmp_path)
    assert result == {
        "status": "CANDIDATES_BUILT_NOT_CUTOVER",
        "points": {"knowledge": 1, "memory": 1},
    }
    assert set(client.collections) == {
        item["candidate_collection"] for item in plan["collections"]
    }
    assert client.forbidden_calls == []
    knowledge = client.collections["sealai-dr-drtest-001-knowledge"]["points"]
    memory = client.collections["sealai-dr-drtest-001-memory"]["points"]
    assert next(iter(knowledge.values())).payload == snapshot["knowledge"][0]["payload"]
    memory_payload = next(iter(memory.values())).payload
    assert memory_payload["tenant_id"] == "tenant-a"
    assert memory_payload["owner_subject"] == "subject-a"
    assert "content" not in memory_payload
    events = sorted((journal / plan["run_id"]).glob("*.json"))
    assert [path.name for path in events] == [
        "0001-execution_started.json",
        "0002-candidate_built.json",
        "0003-candidate_built.json",
        "0004-execution_completed.json",
    ]


def test_execute_replay_and_unapproved_fake_are_blocked(tmp_path: Path) -> None:
    snapshot, plan, journal, client, _ = _execute(tmp_path)
    approval_store = tmp_path / "new-approval-context"
    approval_store.mkdir(mode=0o700)
    approval, policy, now = _approval(plan, approval_store)
    with pytest.raises(
        rebuild.RebuildError, match="local_fake_embedder_not_authorized"
    ):
        rebuild.execute_rebuild(
            plan,
            snapshot,
            approval_path=approval,
            trust_policy_path=policy,
            qdrant_client=FakeQdrant(),
            embedder=rebuild.LocalFakeEmbedder(8),
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=tmp_path / "unused-journal",
            allow_local_fake=False,
            now=now,
        )

    class WrongModel(rebuild.LocalFakeEmbedder):
        model_id_sha256 = "f" * 64

    other_context = tmp_path / "wrong-model-context"
    other_context.mkdir(mode=0o700)
    other_approval, other_policy, other_now = _approval(plan, other_context)
    other_journal = tmp_path / "wrong-model-journal"
    other_journal.mkdir(mode=0o700)
    with pytest.raises(rebuild.RebuildError, match="embedder_model_mismatch"):
        rebuild.execute_rebuild(
            plan,
            snapshot,
            approval_path=other_approval,
            trust_policy_path=other_policy,
            qdrant_client=FakeQdrant(),
            embedder=WrongModel(8),
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=other_journal,
            allow_local_fake=True,
            now=other_now,
        )
    with pytest.raises(rebuild.RebuildError, match="rebuild_run_replay"):
        rebuild.execute_rebuild(
            plan,
            snapshot,
            approval_path=approval,
            trust_policy_path=policy,
            qdrant_client=client,
            embedder=rebuild.LocalFakeEmbedder(8),
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=journal,
            allow_local_fake=True,
            now=now,
        )


def test_runtime_embedder_requires_explicit_admission_wrapper(tmp_path: Path) -> None:
    snapshot = _snapshot()
    model_id = "f" * 64
    plan = rebuild.build_plan(
        snapshot,
        run_id="external-001",
        created_at="2026-07-15T12:00:00Z",
        embedder_kind="runtime_external",
        model_id_sha256=model_id,
        vector_size=8,
        passage_prefix="",
        production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
    )
    authority = tmp_path / "authority"
    authority.mkdir(mode=0o700)
    approval, policy, now = _approval(plan, authority)

    class UnadmittedEmbedder:
        model_id_sha256 = model_id

        def embed(self, _texts):
            raise AssertionError("admission must fail before provider access")

    with pytest.raises(rebuild.RebuildError, match="external_embedder_not_admitted"):
        rebuild.execute_rebuild(
            plan,
            snapshot,
            approval_path=approval,
            trust_policy_path=policy,
            qdrant_client=FakeQdrant(),
            embedder=UnadmittedEmbedder(),
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=tmp_path / "unused-journal",
            now=now,
        )


def test_verify_checks_source_ids_payloads_tenants_and_never_cuts_over(
    tmp_path: Path,
) -> None:
    snapshot, plan, journal, client, _ = _execute(tmp_path)
    drifted = copy.deepcopy(snapshot)
    drifted["captured_at"] = "2026-07-15T12:05:00Z"
    drifted["transaction_snapshot_sha256"] = "3" * 64
    drifted["authority_sequence"] += 1
    with pytest.raises(rebuild.RebuildError, match="postgres_source_drift"):
        rebuild.verify_candidates(
            plan,
            snapshot,
            drifted,
            qdrant_client=client,
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=journal,
        )

    with pytest.raises(rebuild.RebuildError, match="current_snapshot_not_fresh"):
        rebuild.verify_candidates(
            plan,
            snapshot,
            copy.deepcopy(snapshot),
            qdrant_client=client,
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=journal,
        )

    memory_name = "sealai-dr-drtest-001-memory"
    point = next(iter(client.collections[memory_name]["points"].values()))
    current = {
        **copy.deepcopy(snapshot),
        "captured_at": "2026-07-15T12:05:00Z",
        "transaction_snapshot_sha256": "3" * 64,
    }
    original = dict(point.payload)
    point.payload["tenant_id"] = "tenant-b"
    with pytest.raises(rebuild.RebuildError, match="candidate_verification_mismatch"):
        rebuild.verify_candidates(
            plan,
            snapshot,
            current,
            qdrant_client=client,
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=journal,
        )
    point.payload = original
    original_vector = dict(point.vector)
    point.vector = {"dense": [float("nan")] * 8}
    with pytest.raises(
        rebuild.RebuildError, match="candidate_vector_contract_mismatch"
    ):
        rebuild.verify_candidates(
            plan,
            snapshot,
            current,
            qdrant_client=client,
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=journal,
        )
    point.vector = original_vector
    result = rebuild.verify_candidates(
        plan,
        snapshot,
        current,
        qdrant_client=client,
        production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
        journal_root=journal,
    )
    assert result["status"] == "CANDIDATES_VERIFIED_NO_CUTOVER"
    assert client.forbidden_calls == []
    assert (journal / plan["run_id"] / "0005-candidates_verified.json").is_file()


def test_verify_requires_the_exact_completed_execution_journal(tmp_path: Path) -> None:
    snapshot, plan, journal, client, _ = _execute(tmp_path)
    record_path = journal / plan["run_id"] / "0004-execution_completed.json"
    record = json.loads(record_path.read_text(encoding="ascii"))
    record["payload"]["points"]["memory"] = 99
    record_path.write_bytes(rebuild._canonical_json(record))
    current = {
        **copy.deepcopy(snapshot),
        "captured_at": "2026-07-15T12:05:00Z",
        "transaction_snapshot_sha256": "3" * 64,
    }
    with pytest.raises(rebuild.RebuildError, match="execution_journal_mismatch"):
        rebuild.verify_candidates(
            plan,
            snapshot,
            current,
            qdrant_client=client,
            production_collections=("sealai_v2_knowledge_v1", "sealai_v2_memory"),
            journal_root=journal,
        )


def test_plan_refuses_a_candidate_collision_with_production() -> None:
    snapshot = _snapshot()
    with pytest.raises(rebuild.RebuildError, match="unsafe_candidate_collection"):
        rebuild.build_plan(
            snapshot,
            run_id="drtest-001",
            created_at="2026-07-15T12:00:00Z",
            embedder_kind="local_fake",
            model_id_sha256=rebuild.LOCAL_FAKE_MODEL_ID_SHA256,
            vector_size=8,
            passage_prefix="",
            production_collections=(
                "sealai-dr-drtest-001-knowledge",
                "sealai_v2_memory",
            ),
        )


def test_real_postgres_capture_is_explicit_ephemeral_only() -> None:
    dsn = os.environ.get("SEALAI_TEST_EPHEMERAL_POSTGRES_DSN")
    if not dsn or os.environ.get("EPHEMERAL_ONLY") != "yes":
        pytest.skip("no explicitly authorized ephemeral PostgreSQL DSN")
    from sealai_v2.db.engine import make_engine

    snapshot = rebuild.capture_postgres_snapshot(
        make_engine(dsn), captured_at="2026-07-15T12:00:00Z"
    )
    assert rebuild.validate_snapshot(snapshot) == snapshot
