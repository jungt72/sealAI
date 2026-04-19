import sys
import types
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
STUB_PATH = ROOT.parent / "langchain_core_stub"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if STUB_PATH.exists() and str(STUB_PATH) not in sys.path:
    sys.path.insert(0, str(STUB_PATH))

if "prometheus_client" not in sys.modules:
    class _MetricValue:
        def __init__(self) -> None:
            self._current = 0.0

        def get(self) -> float:
            return self._current

    def _make_prom_metric(*_args, **_kwargs):
        class _Stub:
            def __init__(self) -> None:
                self._value = _MetricValue()
                self._children = {}

            def inc(self, amount=1, *args, **kwargs):
                try:
                    self._value._current += float(amount)
                except Exception:
                    self._value._current += 1.0
                return None

            def observe(self, *_args, **_kwargs):
                return None

            def set(self, value=0, *args, **kwargs):
                try:
                    self._value._current = float(value)
                except Exception:
                    self._value._current = 0.0
                return None

            def labels(self, *args, **kwargs):
                key = (args, tuple(sorted(kwargs.items())))
                child = self._children.get(key)
                if child is None:
                    child = _Stub()
                    self._children[key] = child
                return child

        return _Stub()

    prometheus_stub = types.ModuleType("prometheus_client")
    prometheus_stub.Counter = _make_prom_metric
    prometheus_stub.Histogram = _make_prom_metric
    prometheus_stub.Gauge = _make_prom_metric
    prometheus_stub.REGISTRY = object()
    prometheus_stub.CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    prometheus_stub.generate_latest = lambda *_a, **_kw: b""
    sys.modules["prometheus_client"] = prometheus_stub


@pytest.fixture
def test_database_name() -> str:
    return f"sealai_test_patch_1_1_{uuid.uuid4().hex[:12]}"


@pytest.fixture
def postgres_container_host() -> str:
    import subprocess

    return subprocess.check_output(
        ["docker", "exec", "postgres", "hostname", "-i"],
        text=True,
    ).strip()


@pytest.fixture
def test_database_url(test_database_name: str, postgres_container_host: str) -> str:
    return (
        f"postgresql+psycopg2://sealai:sealAI_dev_2025@{postgres_container_host}:5432/"
        f"{test_database_name}"
    )


@pytest.fixture
def _created_test_database(test_database_name: str):
    import subprocess

    subprocess.run(
        ["docker", "exec", "postgres", "createdb", "-U", "sealai", test_database_name],
        check=True,
    )
    try:
        yield
    finally:
        subprocess.run(
            [
                "docker",
                "exec",
                "postgres",
                "dropdb",
                "-U",
                "sealai",
                "--if-exists",
                test_database_name,
            ],
            check=True,
        )


@pytest.fixture
def alembic_config(_created_test_database, monkeypatch, test_database_url: str) -> Config:
    monkeypatch.setenv("POSTGRES_SYNC_URL", test_database_url)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("version_locations", str(ROOT / "alembic" / "versions"))
    config.set_main_option("prepend_sys_path", str(ROOT))
    config.set_main_option("sqlalchemy.url", test_database_url)
    return config


@pytest.fixture
def test_db_engine(_created_test_database, test_database_url: str):
    engine = create_engine(test_database_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def test_db_engine_at_head(alembic_config: Config, test_db_engine):
    from alembic import command

    command.upgrade(alembic_config, "head")
    yield test_db_engine
