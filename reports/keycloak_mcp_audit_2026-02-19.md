# Keycloak MCP Audit Report
Date: 2026-02-19
Realm: sealAI

## 1) User Audit: `jungt`
- User exists in realm `sealAI`: Yes
- Required realm roles:
  - `mcp:pim:read`: Present (applied during this run)
  - `mcp:knowledge:read`: Present (applied during this run)

Final realm role mapping for `jungt`:
- `default-roles-sealai`
- `mcp:pim:read`
- `mcp:knowledge:read`

Comparison with `superadmin` (realm roles relevant to MCP):
- `superadmin` has `mcp:pim:read` and `mcp:knowledge:read`
- `jungt` now has both roles as well
- MCP capability parity status: Match

## 2) Client Scope Audit: `nextauth`
Default client scopes now include:
- `mcp:pim:read`
- `mcp:knowledge:read`

Status:
- Both required MCP scopes are configured as default client scopes for `nextauth`.

## 3) Automation Check: Realm Default Roles
Realm default role: `default-roles-sealai`

Composites now include:
- `mcp:pim:read`
- `mcp:knowledge:read`

Status:
- Both required MCP roles were added to realm default roles.
- New users in realm `sealAI` will inherit these roles automatically.

## 4) Execution Summary
Applied changes:
- Added realm role `mcp:pim:read` to user `jungt`
- Added realm role `mcp:knowledge:read` to user `jungt`
- Ensured `nextauth` default client scopes include `mcp:pim:read` and `mcp:knowledge:read`
- Added `mcp:pim:read` and `mcp:knowledge:read` to `default-roles-sealai`

Verification result: PASS
