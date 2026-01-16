# » backend/app/services/auth/tests/test_tenant_resolution_from_groups.py

import pytest
from app.services.auth.dependencies import resolve_tenant_id_from_claims, _resolve_tenant_id

def test_resolve_from_direct_claim():
    """Direct claim takes precedence."""
    claims = {"tenant_id": "t1", "groups": ["tenant-2"]}
    assert resolve_tenant_id_from_claims(claims) == "t1"
    
    claims = {"tenantID": "tX", "groups": ["tenant-Y"]}
    assert resolve_tenant_id_from_claims(claims) == "tX"

def test_resolve_from_groups_simple():
    """Standard 'tenant-X' format."""
    claims = {"sub": "u1", "groups": ["/tenant-1", "user-group"]}
    assert resolve_tenant_id_from_claims(claims) == "tenant-1"

    claims = {"groups": ["tenant-alpha"]}
    assert resolve_tenant_id_from_claims(claims) == "tenant-alpha"

def test_resolve_from_groups_colon():
    """Format 'tenant:X' should extract 'X'."""
    claims = {"groups": ["/tenant:123"]}
    assert resolve_tenant_id_from_claims(claims) == "123"

def test_resolve_ambiguous_groups_fail_closed():
    """Multiple suitable tenant groups -> return None."""
    claims = {"groups": ["tenant-1", "tenant-2"]}
    assert resolve_tenant_id_from_claims(claims) is None

def test_resolve_missing():
    """No tenant info at all."""
    claims = {"sub": "u1", "groups": ["some-other-group"]}
    assert resolve_tenant_id_from_claims(claims) is None

def test_integration_resolve_tenant_id():
    """Verify integration in _resolve_tenant_id wrapper."""
    payload = {"groups": ["tenant-main"]}
    assert _resolve_tenant_id(payload) == "tenant-main"
