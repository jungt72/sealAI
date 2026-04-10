# Re-export shim — canonical location: app.agent.runtime.boundaries
# DO NOT add logic here. This file exists only for import compatibility.
from app.agent.runtime.boundaries import (  # noqa: F401
    FAST_PATH_DISCLAIMER,
    REVIEW_PENDING_PREFIX,
    STRUCTURED_PATH_SUFFIX,
    _COVERAGE_NOTES,
    _DEMO_DATA_NOTE,
    _NO_EVIDENCE_NOTE,
    _build_review_pending_line,
    build_boundary_block,
)
