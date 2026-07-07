"""LangSmith observability seam for V2 — framework-agnostic, fail-open, SAFE BY DEFAULT.

V2 is a custom L1-L4 pipeline (not LangChain), so tracing is wired the framework-agnostic way:
``wrap_openai`` traces every LLM call (L1 / L3 verifier / helper / judge) with its prompt, answer,
tokens, latency and cost; ``@traceable`` makes the per-turn ``Pipeline.run`` the parent span so the
calls group into ONE trace per conversation turn (project ``LANGSMITH_PROJECT``).

SAFETY (this sits on the trust spine):
- OBSERVATION-ONLY: the wrappers record inputs/outputs but return them UNCHANGED — the pipeline
  output is byte-identical whether tracing is on or off, so the eval is unperturbed.
- FAIL-OPEN on tracing infrastructure errors: if ``langsmith`` is absent OR ``LANGSMITH_TRACING`` is
  unset, every helper degrades to a transparent no-op; any tracing error is swallowed (a LangSmith
  outage never blocks a user turn — the SDK submits in the background).
- FAIL CLOSED on content safety (Phase 0, audit finding): whenever tracing IS active, the LangSmith
  ``Client`` is constructed with ``hide_inputs``/``hide_outputs`` per ``obs.safe_trace``'s resolved
  policy — production can NEVER end up sending raw prompts/completions just because ``wrap_openai``
  was called with no arguments (that was the actual bug this phase fixes: the SDK's own redaction
  knobs were never invoked, so tracing captured full prompts/completions unredacted by default).
- The eval runs WITHOUT the LANG env (run_eval.sh unsets it) → tracing off → no eval noise, no drift.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from sealai_v2.obs.safe_trace import resolve_langsmith_client_policy

try:  # langsmith is optional — absent (e.g. the host venv) → full no-op
    from langsmith import Client as _LsClient
    from langsmith import traceable as _ls_traceable
    from langsmith.wrappers import wrap_openai as _ls_wrap_openai

    _AVAILABLE = True
except Exception:  # noqa: BLE001 — any import problem → tracing simply off
    _AVAILABLE = False


def tracing_enabled() -> bool:
    """True iff langsmith is importable AND tracing is switched on via env (LANGSMITH/LANGCHAIN)."""
    if not _AVAILABLE:
        return False
    v = (
        (os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2") or "")
        .strip()
        .lower()
    )
    return v in ("1", "true", "yes", "on")


def maybe_wrap_openai(client):
    """Trace every call of an AsyncOpenAI client — passthrough when tracing is off/absent.

    Phase 0: an explicit ``langsmith.Client`` is always constructed with the resolved
    ``hide_inputs``/``hide_outputs`` policy (default: both True — ``safe_metadata_only``) and
    passed via ``tracing_extra``, so raw prompts/completions are hidden from LangSmith UNLESS the
    resolved mode is ``full_synthetic_only`` (which ``obs.safe_trace`` itself refuses to grant in
    production). Observation-only: request + response are unchanged (the eval stays byte-identical).
    """
    if not tracing_enabled():
        return client
    try:
        policy = resolve_langsmith_client_policy()
        ls_client = _LsClient(
            hide_inputs=policy.hide_inputs, hide_outputs=policy.hide_outputs
        )
        return _ls_wrap_openai(client, tracing_extra={"client": ls_client})
    except Exception:  # noqa: BLE001 — never break client construction on a tracing hiccup
        return client


def traceable(*d_args, **d_kwargs) -> Callable[[Callable], Callable]:
    """``@traceable(...)`` that degrades to an identity decorator when langsmith is absent. When
    present but tracing is off, the langsmith decorator is itself a cheap passthrough (it checks
    ``LANGSMITH_TRACING`` at call time), so the wrapped function's BEHAVIOUR is unchanged either way."""

    def _decorator(fn: Callable) -> Callable:
        if not _AVAILABLE:
            return fn
        try:
            return _ls_traceable(*d_args, **d_kwargs)(fn)
        except Exception:  # noqa: BLE001 — fail-open to the undecorated function
            return fn

    return _decorator
