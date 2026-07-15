---
evidence_class: HISTORICAL_SNAPSHOT
authoritative_current_state: false
captured_at: "2026-07-14T11:35:38Z"
source_repository_commit: dcb19015adacdc790dd1b25cc430333691c43626
production_commit_at_capture: ab91faf4f3d3ed8fe61dbc9aedab02e966f40856
superseded: true
---

# Evidence handling for REM-2026-07-14

This directory contains only superseded, sanitized historical documentation.
Raw host inventories, command output, and scan reports remain local under the
ignored `.ai-remediation/runtime/` tree. Historical evidence must never contain
credentials, private-key data, authorization material, production environment
values, Redis values, or personal data.

The versioned `../evidence-manifest.json` records historical hashes and the
classification boundary. Local-only runtime artifacts now belong under
`.ai-remediation/runtime/`, which is ignored in full. The manifest records only artifact names, record
counts, modes, checksums, and unresolved classification counts. It does not
make the ignored raw metadata suitable for publication or commit.
