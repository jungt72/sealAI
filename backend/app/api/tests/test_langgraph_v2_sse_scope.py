from app.api.v1.endpoints import langgraph_v2 as endpoint


def test_sse_scope_id_includes_tenant_and_user() -> None:
    assert endpoint._sse_scope_id("tenant-1", "user-1") == "tenant-1:user-1"


def test_sse_scope_id_falls_back_to_user() -> None:
    assert endpoint._sse_scope_id("", "user-1") == "user-1"
