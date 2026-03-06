import asyncio
from types import SimpleNamespace

from app.langgraph_v2.nodes.profile_loader import profile_loader_node
from app.langgraph_v2.state import SealAIState


def test_profile_loader_uses_aget_when_available() -> None:
    class AsyncStore:
        def __init__(self) -> None:
            self.calls = []

        async def aget(self, namespace, key):
            self.calls.append((namespace, key))
            return SimpleNamespace(value={"preferred_medium": "water"})

    store = AsyncStore()
    result = asyncio.run(profile_loader_node(SealAIState(conversation={"user_id": "user-1"}), store))
    assert store.calls == [(("user_prefs", "user-1"), "technical_context")]
    assert result["conversation"]["user_context"] == {"preferred_medium": "water"}
    assert result["reasoning"]["working_memory"].design_notes["user_profile"] == {"preferred_medium": "water"}


def test_profile_loader_falls_back_to_sync_get_without_aget() -> None:
    class StoreWithoutAGet:
        def __init__(self) -> None:
            self.calls = []

        def get(self, namespace, key):
            self.calls.append((namespace, key))
            return SimpleNamespace(value={"preferred_medium": "oil"})

    store = StoreWithoutAGet()
    result = asyncio.run(profile_loader_node(SealAIState(conversation={"user_id": "user-2"}), store))
    assert store.calls == [(("user_prefs", "user-2"), "technical_context")]
    assert result["conversation"]["user_context"] == {"preferred_medium": "oil"}
    assert result["reasoning"]["working_memory"].design_notes["user_profile"] == {"preferred_medium": "oil"}


def test_profile_loader_preserves_auth_scopes_when_loading_profile() -> None:
    class AsyncStore:
        async def aget(self, namespace, key):
            return SimpleNamespace(value={"preferred_medium": "water"})

    state = SealAIState(
        conversation={
            "user_id": "user-3",
            "user_context": {"auth_scopes": ["openid", "mcp:knowledge:read"]},
        },
    )
    result = asyncio.run(profile_loader_node(state, AsyncStore()))
    assert result["conversation"]["user_context"]["preferred_medium"] == "water"
    assert result["conversation"]["user_context"]["auth_scopes"] == ["openid", "mcp:knowledge:read"]


def test_profile_loader_resolves_user_id_from_context_metadata() -> None:
    class AsyncStore:
        def __init__(self) -> None:
            self.calls = []

        async def aget(self, namespace, key):
            self.calls.append((namespace, key))
            return SimpleNamespace(value={"domains": ["hydrogen"], "preferred_standards": ["ISO"]})

    store = AsyncStore()
    state = SealAIState(
        conversation={"user_context": {"metadata": {"user_id": "ctx-user-7"}}},
    )
    result = asyncio.run(profile_loader_node(state, store))
    assert store.calls == [(("user_prefs", "ctx-user-7"), "technical_context")]
    assert result["reasoning"]["working_memory"].design_notes["user_domains"] == ["hydrogen"]
    assert result["reasoning"]["working_memory"].design_notes["preferred_standards"] == ["ISO"]
