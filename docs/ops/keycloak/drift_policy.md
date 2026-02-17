# Keycloak Drift Policy

## Overview
We enforce a **GitOps workflow** for Keycloak configuration. The source of truth for the `sealAI` realm is `docs/ops/keycloak/realm-export/sealAI-realm.sanitized.json`.

## Rules
1. **No UI Changes without Commit**: If you change settings in the Keycloak Admin UI, you MUST export the realm and commit the changes immediately.
2. **Drift Checks**: Continuous Integration (or manual ops checks) run `scripts/keycloak/check_realm_drift.sh` to ensure the live environment matches Git.

## Workflow
1. Make changes in Keycloak Admin UI (Dev/Staging).
2. Run export script:
   ```bash
   bash scripts/keycloak/export_realm.sh
   ```
3. Commit the updated `sealAI-realm.sanitized.json`.
4. Deploy to Production (Import not yet automated, manual for now or via startup import).

## Drift Detection
Run the check script to verify zero drift:
```bash
bash scripts/keycloak/check_realm_drift.sh
```
