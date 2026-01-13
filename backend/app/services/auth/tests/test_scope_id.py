import pytest
from app.services.auth.scope import build_scope_id

def test_build_scope_id_standard():
    assert build_scope_id(tenant_id="t1", user_id="u1") == "t1:u1"

def test_build_scope_id_no_user():
    # If user_id is None, we expect just tenant_id
    assert build_scope_id(tenant_id="t1", user_id=None) == "t1"

def test_build_scope_id_missing_tenant():
    with pytest.raises(ValueError):
        build_scope_id(tenant_id="", user_id="u1")
    with pytest.raises(ValueError):
        build_scope_id(tenant_id=None, user_id="u1")
