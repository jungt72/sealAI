# backend/app/agent/hardening/__init__.py
"""
Hardening primitives for the SealAI agent pipeline.

Provides:
- ExtractionCertainty / EngineStatus enums
- EngineResult[T] generic wrapper
- classify_certainty / is_calculable extraction logic
- claim_whitelist_check + invariant guards
- Physical plausibility checks
"""
