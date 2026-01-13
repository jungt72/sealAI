import pytest
from fastapi import HTTPException
from app.services.auth.dependencies import validate_tenant_id, canonical_tenant_id, RequestUser

def test_validate_tenant_id_success():
    assert validate_tenant_id("tenant-123") == "tenant-123"
    assert validate_tenant_id("valid_tenant") == "valid_tenant"
    assert validate_tenant_id("123") == "123"

def test_validate_tenant_id_fail():
    invalid_cases = [
        "ab", # too short
        "tenant!", # invalid char
        "tenant:123", # invalid char
        "../tenant", # traversal
        "a" * 65 # too long
    ]
    for invalid in invalid_cases:
        with pytest.raises(HTTPException) as exc:
            validate_tenant_id(invalid)
        assert exc.value.status_code == 403

def test_canonical_tenant_id_strictness():
    user = RequestUser(
        user_id="u1",
        username="u1",
        sub="u1",
        roles=[],
        tenant_id="invalid!"
    )
    with pytest.raises(HTTPException):
        canonical_tenant_id(user)

    user_valid = RequestUser(
        user_id="u1",
        username="u1",
        sub="u1",
        roles=[],
        tenant_id="tenant-ok"
    )
    assert canonical_tenant_id(user_valid) == "tenant-ok"
