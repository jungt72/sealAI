# Interoperability Charter

Status: target contract for H2-H5. It does not claim current integration.

## Principle

sealingAI owns its canonical domain model but must not become another closed
industrial data silo. External adapters map to versioned domain contracts;
vendor-specific payloads never become the canonical model.

## Required mappings

- Reliability, failure, and maintenance events: map to the applicable concepts
  of ISO 14224 where the industry and license permit it.
- Asset identity and submodels: remain exportable to Asset Administration Shell
  identifiers and semantic references.
- Process-plant context: preserve stable references that can be mapped to DEXPI
  equipment and process objects.
- CMMS/ERP: use idempotent import/export contracts with external IDs, source
  system, source version, observed time, and synchronization state.

## Data rules

- Postgres remains the sealingAI system of record for claims, cases, decisions,
  capabilities, and audit events.
- External systems remain authoritative for fields explicitly marked as their
  ownership domain.
- Every imported value carries source, timestamp, version, tenant, and conflict
  state.
- Export never implies permission to reuse tenant or manufacturer data.
- PDF is an artifact, not an interoperability contract.

## Activation gate

An integration needs a contract test, tenant-isolation test, idempotency proof,
data-rights review, recovery path, and maturity label before production use.
