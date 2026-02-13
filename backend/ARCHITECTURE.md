# SealAI Architecture v2.2 (Platinum Standard)

## Prompt Engineering (Managed Registry)
All prompts are now managed via the `PromptRegistry` class, enforcing version control and traceability. 
- **Location**: `app/prompts/` (or `SEALAI_PROMPT_DIR`)
- **Structure**: Prompts are Jinja2 templates (`.j2`) organized by domain (e.g., `extraction/`, `safety/`, `greeting/`).
- **Contexts**: Each prompt has a corresponding Pydantic context model in `app/prompts/contexts.py` to ensure type-safe data injection.
- **Rendering**: 
  ```python
  from app.prompts.registry import PromptRegistry
  registry = PromptRegistry()
  content, fingerprint, version = registry.render("extraction/request_v1", context_dict)
  ```

## Traceability
To ensure auditability of AI decisions, the system logs the exact prompt version and content fingerprint used for every generation.
- **State Fields**:
  - `prompt_id_used`: The registry ID of the prompt (e.g., `extraction/request`).
  - `prompt_version_used`: The Git SHA or version tag of the template file.
  - `prompt_fingerprint`: A SHA-256 hash of the *rendered* content sent to the LLM.
- **Logs**: These fields are included in the `state` return dictionary of nodes and logged via `structlog`.

## Nodes Architecture
- **Frontdoor**: Use `GreetingContext` and separates System/User prompts.
- **Discovery**: Uses `CollaborativeExtractionContext` for missing parameter requests.
- **Guardrail**: Uses `EmpathicConcernContext` for safety escalations.
