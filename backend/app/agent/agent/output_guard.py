# Re-export shim — canonical location: app.agent.runtime.output_guard
# DO NOT add logic here. This file exists only for import compatibility.
from app.agent.runtime.output_guard import (  # noqa: F401
    FAST_PATH_GUARD_FALLBACK,
    check_fast_path_output,
)
