# Keycloak Operations

## Realm Export (GitOps)

The realm configuration is exported and sanitized to prevent drift and allow version control.

- **File**: `realm-export/sealAI-realm.sanitized.json`
- **Users**: Skipped (users are state, not config).
- **Secrets**: Sanitized (secrets, clientSecrets, privateKeys removed).

### How to reproduce
Run the export script from the root:
```bash
bash scripts/keycloak/export_realm.sh
```
