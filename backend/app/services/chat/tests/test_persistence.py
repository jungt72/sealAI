import asyncio
import types

from app.services.chat import persistence as mod


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.committed = False

    async def execute(self, stmt):
        return _FakeResult(self.existing)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeTranscript:
    class _Field:
        def __eq__(self, other):
            return True

    chat_id = _Field()
    tenant_id = _Field()

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeSelect:
    def where(self, *args, **kwargs):
        return self


def _patch_persistence_deps(monkeypatch, fake_session):
    monkeypatch.setattr(mod, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(mod, "ChatTranscript", _FakeTranscript)
    monkeypatch.setattr(mod, "select", lambda *args, **kwargs: _FakeSelect())


def test_persist_skips_without_tenant(monkeypatch):
    fake = _FakeSession()
    _patch_persistence_deps(monkeypatch, fake)

    asyncio.run(
        mod.persist_chat_transcript(chat_id="c1", user_id="u1", tenant_id="", summary="s")
    )
    assert fake.added == []
    assert fake.committed is False


def test_persist_inserts_new(monkeypatch):
    fake = _FakeSession(existing=None)
    _patch_persistence_deps(monkeypatch, fake)

    asyncio.run(
        mod.persist_chat_transcript(
            chat_id="c1",
            user_id="u1",
            tenant_id="t1",
            summary="hello",
            metadata={"a": 1},
        )
    )
    assert len(fake.added) == 1
    assert fake.committed is True
    row = fake.added[0]
    assert row.chat_id == "c1"
    assert row.user_id == "u1"
    assert row.tenant_id == "t1"
    assert row.summary == "hello"


def test_persist_updates_existing(monkeypatch):
    existing = types.SimpleNamespace(
        chat_id="c1",
        user_id="uOld",
        tenant_id="t1",
        summary="old",
        metadata={},
    )
    fake = _FakeSession(existing=existing)
    _patch_persistence_deps(monkeypatch, fake)

    asyncio.run(
        mod.persist_chat_transcript(
            chat_id="c1",
            user_id="u1",
            tenant_id="t1",
            summary="new",
            metadata={"x": "y"},
        )
    )
    assert fake.committed is True
    assert existing.user_id == "u1"
    assert existing.summary == "new"
    assert existing.metadata["x"] == "y"
