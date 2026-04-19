# MyPy Baseline — 2026-04-19

**Purpose:** Document the initial mypy state of the SeaLAI codebase.
**Config:** `mypy.ini` at repo root, committed in this patch.
**Strategy:** Permissive global config; strict config hooks on Sprint 1+ services.

## Summary

- MyPy version: mypy 1.11.2 (compiled: yes)
- Total errors on full run: 664
- Files with errors: 103
- Source files checked: 354
- Baseline date: 2026-04-19

## Strict-mode modules (zero-error gate for Sprint 1+)

The following modules have strict mypy enforcement. The Sprint 1+ service modules
mostly do not yet exist in code; when they are created, they MUST pass mypy
strict checks:

- backend/app/domain/*
- backend/app/services/case_service
- backend/app/services/pre_gate_classifier
- backend/app/services/output_classifier
- backend/app/services/inquiry_extract_service
- backend/app/services/anonymization_service
- backend/app/services/knowledge_service
- backend/app/services/terminology_service
- backend/app/services/risk_engine
- backend/app/services/fast_responder_service
- backend/app/services/medium_intelligence_service
- backend/app/services/application_pattern_service
- backend/app/services/advisory_engine
- backend/app/services/formula_library
- backend/app/services/outbox_worker
- backend/app/services/norm_modules
- backend/app/services/output_validator
- backend/app/services/projection_service
- backend/app/services/compatibility_service

## Legacy-mode coverage

Rest of backend/app/ is under permissive config. Findings are documented but
not blocking. See `/tmp/mypy_baseline.txt` for full output (not committed —
refreshed each time mypy runs).

## Top error categories in legacy baseline

- `arg-type`: 191
- `attr-defined`: 102
- `assignment`: 78
- `unused-ignore`: 71
- `call-overload`: 69
- `typeddict-item`: 44
- `annotation-unchecked`: 40
- `index`: 26
- `union-attr`: 22
- `call-arg`: 22

## Reproducibility

```bash
mypy backend/app/ 2>&1 | tail -5
```

Last baseline run:

```text
                    request=_DummyRawRequest(),
                            ^~~~~~~~~~~~~~~~~~
backend/app/api/tests/test_langgraph_v2_endpoint.py:848: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
backend/app/api/tests/test_langgraph_v2_endpoint.py:921: note: By default the bodies of untyped functions are not checked, consider using --check-untyped-defs  [annotation-unchecked]
Found 664 errors in 103 files (checked 354 source files)
```

## Next actions

- Sprint 1 Patch 1.4 onward: when new modules listed in "Strict-mode" section
  are created, they must pass `mypy backend/app/...` with zero errors before merge.
- Pre-commit hook or CI integration: out of scope for this patch; candidate for
  Sprint 5 cleanup.
- Legacy findings: addressed opportunistically as legacy code is refactored in
  Sprint 1-5.

## Document end.
