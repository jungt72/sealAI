# backend/app/services/langgraph/graph/sealai_consult_flow.py
from __future__ import annotations

import os
import logging

from .consult.io import invoke_consult as _invoke_consult_single

log = logging.getLogger(__name__)

_SUP_AVAILABLE = True
try:
    from .supervisor_graph import invoke_consult_supervisor as _invoke_consult_supervisor
except Exception as e:
    _SUP_AVAILABLE = False
    log.warning("Supervisor graph not available, falling back to single-agent: %s", e)

_MODE = os.getenv("CONSULT_MODE", "consult").strip().lower()

def invoke_consult(prompt: str, *, thread_id: str) -> str:
    use_supervisor = (_MODE == "supervisor" and _SUP_AVAILABLE)
    if use_supervisor:
        try:
            return _invoke_consult_supervisor(prompt, thread_id=thread_id)
        except Exception as e:
            log.exception("Supervisor failed, falling back to single-agent: %s", e)
    return _invoke_consult_single(prompt, thread_id=thread_id)
