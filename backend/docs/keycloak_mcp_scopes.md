# Keycloak MCP Scope Configuration

Backend MCP tool visibility is now scope-gated. A user sees/calls `search_technical_docs` only when at least one of these scopes is present in the access token:

- `mcp:pim:read`
- `mcp:knowledge:read`

## Required Keycloak setup

1. Create client scopes:
   - `mcp:pim:read`
   - `mcp:knowledge:read`
2. Assign one or both scopes to users (directly or via group/role mapping).
3. Ensure scopes are emitted in the access token `scope` (or `scp`) claim.
4. For role-based deployments, roles prefixed with `mcp:` are also treated as effective scopes by the backend.

## Forced token refresh (critical)

After changing scope assignments, existing JWTs keep old claims until re-issued.

1. User `jungt` must log out completely.
2. User `jungt` must log in again.
3. Verify the new access token now contains `mcp:knowledge:read` (or `mcp:pim:read`) before testing MCP/RAG calls.

## Backend enforcement points

- MCP API: `backend/app/api/v1/endpoints/mcp.py`
- Scope extraction: `backend/app/services/auth/dependencies.py`
- Graph tool discovery/context visibility: `backend/app/langgraph_v2/sealai_graph_v2.py`
- Tool contract: `backend/app/mcp/knowledge_tool.py`
