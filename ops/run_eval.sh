#!/bin/bash
# Eval-REPLAY runner — sources ONLY the model keys + per-role model config from .env.prod (matching the
# served runtime for the L1 gate-bind), hermetic (no DATABASE_URL → in-process stores, no prod-DB write).
set -e
cd ~/sealai
set -a
. <(grep -E '^(OPENAI_API_KEY|MISTRAL_API_KEY|SEALAI_V2_PROVIDER|SEALAI_V2_(L1|VERIFIER|HELPER|JUDGE|STANDARD)_(MODEL|PROVIDER)|SEALAI_V2_(EXECUTION_POLICY|STRUCTURED_ANSWER)_ENABLED)=' .env.prod)
set +a
unset SEALAI_V2_DATABASE_URL DATABASE_URL 2>/dev/null || true
# Eval traces NOTHING: keep LangSmith off so the run stays byte-identical + creates no eval noise.
unset LANGSMITH_TRACING LANGCHAIN_TRACING_V2 LANGSMITH_API_KEY LANGCHAIN_API_KEY 2>/dev/null || true
PYTHONPATH=backend .venv/bin/python -m sealai_v2.eval "$@"
