# Re-export shim — canonical location: app.agent.prompts
# DO NOT add logic here. This file exists only for import compatibility.
from app.agent.prompts import (  # noqa: F401
    REASONING_PROMPT_VERSION,
    REASONING_PROMPT_HASH,
    FAST_GUIDANCE_PROMPT_TEMPLATE,
    FAST_GUIDANCE_PROMPT_VERSION,
    FAST_GUIDANCE_PROMPT_HASH,
    build_fast_guidance_prompt,
    prompts,
    PromptRegistry,
)
