"""Executable contract: V2 and marketing do not depend on the shared Redis service.

The production host still runs Redis for unrelated consumers.  That does not make it a V2
dependency: V2 uses Postgres as its system of record and durable outbox, while Qdrant is only a
derived retrieval index.  These tests fail closed if a Redis/Celery/Kombu package, import, Compose
wiring, or legacy environment setting is reintroduced.
"""

from __future__ import annotations

import ast
import builtins
import re
from pathlib import Path

from sqlalchemy import select

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import V2MemoryOutbox
from sealai_v2.memory.outbox_worker import drain_outbox
from sealai_v2.tests._apiutil import auth, make_client

REPO = Path(__file__).resolve().parents[3]
V2_ROOT = REPO / "backend" / "sealai_v2"
FORBIDDEN = ("redis", "celery", "kombu")


def _forbidden_name(name: str) -> bool:
    """Match direct packages and adapters such as hiredis or django_redis."""
    components = re.split(r"[._-]", name.casefold())
    return any(token in component for component in components for token in FORBIDDEN)


def _absolute_imports(path: Path) -> list[str]:
    imports: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            imports.append(node.module)
    return imports


def _requirement_names(path: Path) -> list[str]:
    names: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.partition("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~;\[\s@]", line, maxsplit=1)[0]
        if name:
            names.append(name.casefold().replace("_", "-"))
    return names


def _service_block(path: Path, service: str) -> str:
    """Return one top-level Compose service without requiring PyYAML in the V2 image."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header = f"  {service}:"
    try:
        start = lines.index(header)
    except ValueError as exc:
        raise AssertionError(f"missing Compose service {service!r} in {path}") from exc

    end = len(lines)
    next_service = re.compile(r"^  [A-Za-z0-9_.-]+:\s*(?:#.*)?$")
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line and not line[0].isspace() and not line.startswith("#"):
            end = index
            break
        if next_service.match(line):
            end = index
            break
    # Comments may explain the architectural prohibition itself; they are not
    # Compose wiring. Keep only effective configuration lines for the scan.
    return "\n".join(
        line for line in lines[start:end] if not line.lstrip().startswith("#")
    )


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def _deny_forbidden_imports(monkeypatch) -> None:
    """Trip on a lazy broker/cache import while exercising runtime paths below."""
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and _forbidden_name(name):
            raise AssertionError(f"forbidden V2 runtime import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def _poison_legacy_broker_environment(monkeypatch) -> None:
    # A former implicit dependency would now try an intentionally unreachable address.  Successful
    # API/outbox work below therefore proves these settings are ignored, not merely optional.
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/15")
    monkeypatch.setenv("SEALAI_V2_REDIS_URL", "redis://127.0.0.1:1/15")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://127.0.0.1:1/15")
    monkeypatch.setenv("KOMBU_BROKER_URL", "redis://127.0.0.1:1/15")


def test_v2_has_no_redis_celery_or_kombu_requirement() -> None:
    requirements = _requirement_names(REPO / "backend" / "requirements-v2.txt")
    violations = sorted(name for name in requirements if _forbidden_name(name))
    assert not violations, f"V2 broker/cache dependencies are forbidden: {violations}"


def test_v2_has_no_redis_celery_or_kombu_import() -> None:
    violations: list[str] = []
    for path in sorted(V2_ROOT.rglob("*.py")):
        for module in _absolute_imports(path):
            if _forbidden_name(module):
                violations.append(f"{path.relative_to(REPO)} imports {module}")
    assert not violations, "V2 must remain broker/cache independent:\n" + "\n".join(
        violations
    )


def test_v2_and_marketing_compose_services_have_no_broker_or_cache_wiring() -> None:
    checked = {
        "docker-compose.deploy.yml": ("frontend", "backend-v2", "backend-v2-worker"),
        "docker-compose.v2.yml": ("backend-v2",),
    }
    violations: list[str] = []
    for relative, services in checked.items():
        path = REPO / relative
        for service in services:
            block = _service_block(path, service)
            for token in FORBIDDEN:
                if token in block.casefold():
                    violations.append(f"{relative}:{service} contains {token!r}")
    assert not violations, (
        "service-level broker/cache wiring is forbidden:\n" + "\n".join(violations)
    )


def test_v2_production_env_example_has_no_legacy_redis_or_broker_settings() -> None:
    blocked_keys = {
        "REDIS_URL",
        "REDIS_CHECKPOINTER_URL",
        "LANGGRAPH_V2_REDIS_URL",
        "SEALAI_V2_REDIS_URL",
        "SEALAI_V2_REDIS_NAMESPACE",
        "SEALAI_LANGGRAPH_CHECKPOINTING",
    }
    violations: list[str] = []
    # The development templates remain a legacy-V1/rollback contract. Production V1 is retired,
    # so only its production template is within this V2 remediation boundary.
    for relative in (".env.prod.example",):
        keys = _env_keys(REPO / relative)
        bad = sorted(
            key
            for key in keys
            if key in blocked_keys or "CELERY" in key or "KOMBU" in key
        )
        if bad:
            violations.append(f"{relative}: {', '.join(bad)}")
    assert not violations, (
        "legacy V2/marketing environment settings remain:\n" + "\n".join(violations)
    )


def test_compose_does_not_enable_answer_cache_without_release_authority() -> None:
    backend = _service_block(REPO / "docker-compose.deploy.yml", "backend-v2")
    assert (
        "SEALAI_V2_EXACT_ANSWER_CACHE_ENABLED: "
        "${SEALAI_V2_EXACT_ANSWER_CACHE_ENABLED:-false}" in backend
    )
    assert (
        "SEALAI_V2_KNOWLEDGE_AUTHORITY_EPOCH: "
        "${SEALAI_V2_KNOWLEDGE_AUTHORITY_EPOCH:-}" in backend
    )
    assert "sha256:" not in backend, "Compose must not invent a default authority epoch"

    production_example = (REPO / ".env.prod.example").read_text(encoding="utf-8")
    assert (
        "SEALAI_V2_EXACT_ANSWER_CACHE_ENABLED=false" in production_example.splitlines()
    )
    effective_lines = {
        line.strip()
        for line in production_example.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert not any(
        line.startswith("SEALAI_V2_KNOWLEDGE_AUTHORITY_EPOCH=")
        for line in effective_lines
    ), "the template must not invent an authority epoch"


def test_api_chat_works_with_broker_imports_denied(monkeypatch) -> None:
    _poison_legacy_broker_environment(monkeypatch)
    _deny_forbidden_imports(monkeypatch)

    client, pipeline = make_client()
    response = client.post(
        "/api/v2/chat",
        json={"message": "FKM oder EPDM?"},
        headers=auth("tok-A"),
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Antwort."
    assert pipeline.memory.history(tenant_id="tenant-A", session_id="sess-A")


def test_postgres_outbox_drains_with_broker_imports_denied(
    tmp_path, monkeypatch
) -> None:
    _poison_legacy_broker_environment(monkeypatch)
    _deny_forbidden_imports(monkeypatch)
    engine = make_engine(f"sqlite:///{tmp_path / 'redis-independent-outbox.db'}")
    Base.metadata.create_all(engine)
    sessions = make_sessionmaker(engine)
    with sessions() as session:
        session.add(
            V2MemoryOutbox(
                memory_item_id="memory-deleted",
                tenant_id="tenant-a",
                event_type="delete",
                payload={"id": "memory-deleted", "tenant_id": "tenant-a"},
                created_at="2026-07-14T12:00:00Z",
            )
        )
        session.commit()

    class FakeQdrant:
        deleted: list[tuple[str, list[str]]] = []

        def delete(self, collection: str, points_selector: list[str]) -> None:
            self.deleted.append((collection, list(points_selector)))

    qdrant = FakeQdrant()
    result = drain_outbox(
        sessions,
        qdrant_client=qdrant,
        embedder=None,
        now="2026-07-14T12:00:01Z",
    )

    assert (result.claimed, result.synced, result.failed_permanently) == (1, 1, 0)
    assert qdrant.deleted == [("sealai_v2_memory", ["memory-deleted"])]
    with sessions() as session:
        assert session.scalar(select(V2MemoryOutbox)).status == "done"
    engine.dispose()


def test_contract_detectors_reject_synthetic_regressions(tmp_path) -> None:
    bad_source = tmp_path / "bad.py"
    bad_source.write_text(
        "import redis.asyncio\nfrom celery import Celery\nfrom kombu import Connection\n",
        encoding="utf-8",
    )
    assert all(_forbidden_name(module) for module in _absolute_imports(bad_source))

    bad_requirements = tmp_path / "requirements.txt"
    bad_requirements.write_text(
        "fastapi==1\nlanggraph-checkpoint-redis==0.4\nCelery[redis]==5\n",
        encoding="utf-8",
    )
    assert _requirement_names(bad_requirements) == [
        "fastapi",
        "langgraph-checkpoint-redis",
        "celery",
    ]
    assert [
        name for name in _requirement_names(bad_requirements) if _forbidden_name(name)
    ] == ["langgraph-checkpoint-redis", "celery"]
