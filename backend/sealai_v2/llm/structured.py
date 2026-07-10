"""Provider-native JSON Schema output with strict local Pydantic validation."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from sealai_v2.core.contracts import LlmClient, LlmResult, ModelConfig

T = TypeVar("T", bound=BaseModel)


class StructuredOutputError(ValueError):
    """The provider output could not satisfy the declared schema after one repair."""


def _safe_error_summary(exc: Exception | None) -> str:
    """Describe validation shape without including model output or user content."""
    if exc is None:
        return "unknown"
    if isinstance(exc, ValidationError):
        items = []
        for error in exc.errors(include_url=False, include_input=False)[:8]:
            location = ".".join(str(part) for part in error.get("loc", ())) or "root"
            items.append(f"{error.get('type', 'validation')}@{location}")
        return ",".join(items) or "validation_error"
    return type(exc).__name__


def extract_json_object(raw: str) -> str:
    """Legacy eval compatibility: isolate one object from fenced model output.

    Online structured paths must not use this tolerance; they call
    :func:`generate_structured` and validate the complete response.
    """
    value = raw.strip()
    if value.startswith("```"):
        value = value.strip("`")
        if "\n" in value:
            value = value.split("\n", 1)[1]
    start, end = value.find("{"), value.rfind("}")
    return value[start : end + 1] if start != -1 and end > start else value


async def generate_structured(
    client: LlmClient,
    *,
    output_type: type[T],
    schema_name: str,
    system: str,
    user: str,
    model_config: ModelConfig,
    max_repairs: int = 1,
) -> tuple[T, LlmResult]:
    """Generate and validate one object; allow at most one same-model schema repair."""
    schema = output_type.model_json_schema()
    native = getattr(client, "generate_structured", None)

    async def call(current_system: str, current_user: str) -> LlmResult:
        if native is not None:
            return await native(
                system=current_system,
                user=current_user,
                model_config=model_config,
                schema_name=schema_name,
                json_schema=schema,
            )
        return await client.generate(
            system=current_system, user=current_user, model_config=model_config
        )

    last_error: Exception | None = None
    current_system = system
    current_user = user
    for attempt in range(max_repairs + 1):
        try:
            result = await call(current_system, current_user)
            parsed = output_type.model_validate_json(result.text)
            return parsed, result
        except (ValidationError, ValueError, TypeError) as exc:
            last_error = exc
            if attempt >= max_repairs:
                break
            current_system = (
                system + "\n\nThe previous output violated the required JSON schema. "
                "Return exactly one schema-valid JSON object and no surrounding text."
            )
            current_user = user
        except Exception as exc:
            if attempt == 0:
                raise
            last_error = exc
            break
    raise StructuredOutputError(
        f"{schema_name} failed schema validation after {max_repairs + 1} attempt(s): "
        f"{_safe_error_summary(last_error)}"
    ) from last_error
