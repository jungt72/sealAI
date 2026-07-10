"""Canonical, secret-free fingerprint of answer-affecting runtime configuration.

The served source tree alone is not a complete release identity: model routing,
trust-layer switches and retrieval settings are environment-driven.  This module
normalizes those settings into a stable profile that can be recorded by an eval
and compared by the deploy gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from sealai_v2.config.settings import Settings

PROFILE_SCHEMA_VERSION = 1

# These settings affect infrastructure, access control, telemetry or eval
# execution, but not the content-policy behavior being adjudicated.  Everything
# else is included by default so a newly added behavior flag cannot silently
# escape the release binding.
_NON_BEHAVIOR_FIELDS = frozenset(
    {
        "provider",
        "openai_api_key",
        "openai_base_url",
        "mistral_api_key",
        "mistral_base_url",
        "l1_provider",
        "verifier_provider",
        "helper_provider",
        "judge_provider",
        "judge_model",
        "judge_temperature",
        "auth_jwks_url",
        "auth_issuer",
        "auth_audience",
        "auth_tenant_claim",
        "auth_admin_role",
        "auth_manufacturer_role",
        "legal_ip_hash_pepper",
        "llm_telemetry_enabled",
        "metrics_enabled",
        "concurrency",
        "request_timeout_s",
        "max_retries",
        "openai_max_concurrency",
        "openai_min_interval_s",
        "mistral_max_concurrency",
        "mistral_min_interval_s",
        "exact_answer_cache_max_entries",
        "exact_answer_cache_ttl_s",
        "eval_subject_concurrency",
        "eval_subject_min_interval_s",
        "eval_judge_concurrency",
        "eval_judge_min_interval_s",
        "eval_judge_max_retries",
        "eval_judge_max_output_tokens",
        "eval_judge_reasoning_effort",
        "database_url",
        "qdrant_url",
        "qdrant_api_key",
        "outbox_poll_interval_s",
        "outbox_batch_size",
        "outbox_max_attempts",
        "outbox_claim_timeout_s",
        "embed_cache_dir",
    }
)


def _effective_provider(settings: Settings, role: str) -> str:
    override = getattr(settings, f"{role}_provider")
    return override or settings.provider


def runtime_profile(settings: Settings) -> dict[str, Any]:
    """Return the canonical answer-affecting profile without credentials or URLs."""
    values = settings.model_dump(mode="json")
    behavior = {
        name: value
        for name, value in values.items()
        if name not in _NON_BEHAVIOR_FIELDS
    }
    behavior["role_providers"] = {
        "helper": _effective_provider(settings, "helper"),
        "l1": _effective_provider(settings, "l1"),
        "verifier": _effective_provider(settings, "verifier"),
    }
    return {"schema_version": PROFILE_SCHEMA_VERSION, "behavior": behavior}


def canonical_profile_json(settings: Settings) -> str:
    return json.dumps(
        runtime_profile(settings),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def runtime_profile_hash(settings: Settings) -> str:
    return hashlib.sha256(canonical_profile_json(settings).encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sealai_v2.config.runtime_profile")
    parser.add_argument("--hash", action="store_true", dest="hash_only")
    args = parser.parse_args(argv)
    settings = Settings()
    if args.hash_only:
        print(runtime_profile_hash(settings))
    else:
        print(canonical_profile_json(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
