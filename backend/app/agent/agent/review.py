# Re-export shim — canonical location: app.agent.domain.review
# DO NOT add logic here. This file exists only for import compatibility.
from app.agent.domain.review import (  # noqa: F401
    REASON_DEMO_DATA,
    REASON_MANUFACTURER_VALIDATION,
    _append_unique,
    evaluate_critical_review,
    evaluate_review_trigger,
)
