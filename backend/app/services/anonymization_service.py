from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_PERSON = "[REDACTED_PERSON]"
REDACTED_COMPANY = "[REDACTED_COMPANY]"
REDACTED_ADDRESS = "[REDACTED_ADDRESS]"
REDACTED_CONTACT = "[REDACTED_CONTACT]"
REDACTED_PROJECT_CODE = "[REDACTED_PROJECT_CODE]"
REDACTED_ARTICLE_NUMBER = "[REDACTED_CUSTOMER_ARTICLE_NUMBER]"
REDACTED_MEDIA = "[REDACTED_MEDIA_METADATA]"
REDACTED_INTERNAL = "[REDACTED_INTERNAL_METADATA]"


class RedactionCategory(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    PERSON_NAME = "person_name"
    COMPANY_IDENTIFIER = "company_identifier"
    ADDRESS = "address"
    CONTACT_IDENTIFIER = "contact_identifier"
    PROJECT_CODE = "project_code"
    CUSTOMER_ARTICLE_NUMBER = "customer_article_number"
    CUSTOMER_METADATA = "customer_metadata"
    INTERNAL_METADATA = "internal_metadata"
    MEDIA_METADATA = "media_metadata"


class RedactionAction(str, Enum):
    REPLACED = "replaced"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class RedactionEvent:
    path: str
    category: RedactionCategory
    action: RedactionAction


@dataclass(frozen=True, slots=True)
class AnonymizationResult:
    redacted_payload: Any
    redaction_count: int
    redaction_categories: tuple[RedactionCategory, ...]
    events: tuple[RedactionEvent, ...]
    warnings: tuple[str, ...] = (
        "Text redaction is pattern-based and does not perform general name recognition.",
    )


SENSITIVE_CONTAINER_KEYS: frozenset[str] = frozenset(
    {
        "attachments",
        "contact",
        "customer_metadata",
        "documents",
        "free_text_notes",
        "internal_metadata",
        "media",
        "messages",
        "photos",
        "raw_uploads",
        "user",
    }
)

MEDIA_KEYS: frozenset[str] = frozenset(
    {
        "attachments",
        "documents",
        "exif",
        "image_metadata",
        "media",
        "metadata_exif",
        "photo_metadata",
        "photos",
        "raw_uploads",
    }
)

CUSTOMER_ARTICLE_KEYS: frozenset[str] = frozenset(
    {
        "customer_article_number",
        "customer_internal_article_number",
        "customer_part_number",
        "internal_article_number",
        "internal_part_number",
    }
)

PUBLIC_REFERENCE_TYPES: frozenset[str] = frozenset(
    {
        "manufacturer_part_number",
        "public_datasheet_reference",
        "standard_designation",
        "drawing_reference",
    }
)

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s./-]?)?(?:\(?\d{2,5}\)?[\s./-]?){2,}\d{2,5}(?!\w)"
)
PROJECT_CODE_RE = re.compile(
    r"\b(?:project[_ -]?code|projekt[_ -]?code|project|projekt|proj)\s*[:#=]?\s*[A-Z0-9][A-Z0-9_.-]{2,}\b",
    re.IGNORECASE,
)
CUSTOMER_ARTICLE_RE = re.compile(
    r"\b(?:customer|kunde|kunden|internal|intern)[_ -]?"
    r"(?:article|artikel|part|teile?)[_ -]?"
    r"(?:number|nummer|nr)?\s*[:#=]?\s*[A-Z0-9][A-Z0-9_.-]{2,}\b",
    re.IGNORECASE,
)


def anonymize_payload(payload: Any) -> AnonymizationResult:
    return AnonymizationService().anonymize_payload(payload)


def anonymize_text(text: str) -> AnonymizationResult:
    return AnonymizationService().anonymize_text(text)


def redact_known_sensitive_fields(payload: Any) -> AnonymizationResult:
    return AnonymizationService().redact_known_sensitive_fields(payload)


def summarize_redactions(result: AnonymizationResult) -> dict[str, Any]:
    return {
        "redaction_count": result.redaction_count,
        "redaction_categories": tuple(category.value for category in result.redaction_categories),
        "warnings": result.warnings,
    }


class AnonymizationService:
    """Conservative deterministic redaction for structured content and text."""

    def anonymize_payload(self, payload: Any) -> AnonymizationResult:
        redacted, events = self._redact_value(payload, path="")
        return _result(redacted, events)

    def redact_known_sensitive_fields(self, payload: Any) -> AnonymizationResult:
        return self.anonymize_payload(payload)

    def anonymize_text(self, text: str) -> AnonymizationResult:
        redacted, events = self._redact_text(str(text), path="")
        return _result(redacted, events)

    def _redact_value(self, value: Any, *, path: str) -> tuple[Any, list[RedactionEvent]]:
        if isinstance(value, Mapping):
            return self._redact_mapping(value, path=path)
        if isinstance(value, list):
            return self._redact_sequence(value, path=path, constructor=list)
        if isinstance(value, tuple):
            return self._redact_sequence(value, path=path, constructor=tuple)
        if isinstance(value, str):
            return self._redact_text(value, path=path)
        return value, []

    def _redact_mapping(
        self,
        value: Mapping[Any, Any],
        *,
        path: str,
    ) -> tuple[dict[str, Any], list[RedactionEvent]]:
        redacted: dict[str, Any] = {}
        events: list[RedactionEvent] = []
        for raw_key, raw_item in value.items():
            key = str(raw_key)
            child_path = _join_path(path, key)
            if _normalize_key(key) == "contact" and isinstance(raw_item, Mapping):
                events.append(
                    RedactionEvent(
                        child_path,
                        RedactionCategory.CONTACT_IDENTIFIER,
                        RedactionAction.REMOVED,
                    )
                )
                continue
            if _is_customer_article_reference_value(value, key):
                redacted[key] = REDACTED_ARTICLE_NUMBER
                events.append(
                    RedactionEvent(
                        child_path,
                        RedactionCategory.CUSTOMER_ARTICLE_NUMBER,
                        RedactionAction.REPLACED,
                    )
                )
                continue
            key_category = _category_for_key(key, parent_path=path)
            if key_category is not None:
                replacement, action = _replacement_for_category(key_category)
                events.append(RedactionEvent(child_path, key_category, action))
                if action is RedactionAction.REPLACED:
                    redacted[key] = replacement
                continue

            if _is_public_article_reference(value, key):
                redacted[key] = raw_item
                continue

            item, item_events = self._redact_value(raw_item, path=child_path)
            events.extend(item_events)
            redacted[key] = item
        return redacted, events

    def _redact_sequence(
        self,
        value: Sequence[Any],
        *,
        path: str,
        constructor: type[list] | type[tuple],
    ) -> tuple[list[Any] | tuple[Any, ...], list[RedactionEvent]]:
        redacted: list[Any] = []
        events: list[RedactionEvent] = []
        for index, item in enumerate(value):
            item_path = _join_path(path, str(index))
            redacted_item, item_events = self._redact_value(item, path=item_path)
            redacted.append(redacted_item)
            events.extend(item_events)
        return (tuple(redacted) if constructor is tuple else redacted), events

    @staticmethod
    def _redact_text(text: str, *, path: str) -> tuple[str, list[RedactionEvent]]:
        redacted = text
        events: list[RedactionEvent] = []

        redacted, count = EMAIL_RE.subn(REDACTED_EMAIL, redacted)
        events.extend(
            RedactionEvent(path, RedactionCategory.EMAIL, RedactionAction.REPLACED)
            for _ in range(count)
        )

        redacted, count = PHONE_RE.subn(REDACTED_PHONE, redacted)
        events.extend(
            RedactionEvent(path, RedactionCategory.PHONE, RedactionAction.REPLACED)
            for _ in range(count)
        )

        redacted, count = PROJECT_CODE_RE.subn(
            lambda match: _preserve_marker(match.group(0), REDACTED_PROJECT_CODE),
            redacted,
        )
        events.extend(
            RedactionEvent(path, RedactionCategory.PROJECT_CODE, RedactionAction.REPLACED)
            for _ in range(count)
        )

        redacted, count = CUSTOMER_ARTICLE_RE.subn(
            lambda match: _preserve_marker(match.group(0), REDACTED_ARTICLE_NUMBER),
            redacted,
        )
        events.extend(
            RedactionEvent(
                path,
                RedactionCategory.CUSTOMER_ARTICLE_NUMBER,
                RedactionAction.REPLACED,
            )
            for _ in range(count)
        )

        return redacted, events


def _category_for_key(key: str, *, parent_path: str) -> RedactionCategory | None:
    normalized = _normalize_key(key)
    parent = _normalize_key(parent_path)

    if normalized in MEDIA_KEYS or "exif" in normalized:
        return RedactionCategory.MEDIA_METADATA
    if normalized in {"customer_metadata", "customer", "customer_data"}:
        return RedactionCategory.CUSTOMER_METADATA
    if normalized in {"internal_metadata", "internal_notes", "internal_data"}:
        return RedactionCategory.INTERNAL_METADATA
    if normalized in {"email", "contact_email", "user_email", "customer_email"}:
        return RedactionCategory.EMAIL
    if normalized in {"phone", "telephone", "contact_phone", "user_phone", "customer_phone"}:
        return RedactionCategory.PHONE
    if normalized in {"contact_identifier", "contact_id", "contact"}:
        return RedactionCategory.CONTACT_IDENTIFIER
    if normalized in {"address", "street_address", "billing_address", "shipping_address"}:
        return RedactionCategory.ADDRESS
    if normalized in {"first_name", "last_name", "person_name", "user_name", "customer_name", "name"}:
        return RedactionCategory.PERSON_NAME
    if normalized in {"company_name", "legal_name", "customer_company", "organization_name"} and (
        "customer" in parent or "internal" in parent or "contact" in parent
    ):
        return RedactionCategory.COMPANY_IDENTIFIER
    if normalized in {"project_code", "project_id", "customer_project_code", "internal_project_code"}:
        return RedactionCategory.PROJECT_CODE
    if normalized in CUSTOMER_ARTICLE_KEYS:
        return RedactionCategory.CUSTOMER_ARTICLE_NUMBER
    if normalized in SENSITIVE_CONTAINER_KEYS:
        return RedactionCategory.INTERNAL_METADATA
    return None


def _replacement_for_category(
    category: RedactionCategory,
) -> tuple[str | None, RedactionAction]:
    if category is RedactionCategory.MEDIA_METADATA:
        return None, RedactionAction.REMOVED
    if category is RedactionCategory.CUSTOMER_METADATA:
        return None, RedactionAction.REMOVED
    if category is RedactionCategory.INTERNAL_METADATA:
        return None, RedactionAction.REMOVED
    replacements = {
        RedactionCategory.EMAIL: REDACTED_EMAIL,
        RedactionCategory.PHONE: REDACTED_PHONE,
        RedactionCategory.PERSON_NAME: REDACTED_PERSON,
        RedactionCategory.COMPANY_IDENTIFIER: REDACTED_COMPANY,
        RedactionCategory.ADDRESS: REDACTED_ADDRESS,
        RedactionCategory.CONTACT_IDENTIFIER: REDACTED_CONTACT,
        RedactionCategory.PROJECT_CODE: REDACTED_PROJECT_CODE,
        RedactionCategory.CUSTOMER_ARTICLE_NUMBER: REDACTED_ARTICLE_NUMBER,
    }
    return replacements[category], RedactionAction.REPLACED


def _result(redacted_payload: Any, events: list[RedactionEvent]) -> AnonymizationResult:
    categories = tuple(dict.fromkeys(event.category for event in events))
    return AnonymizationResult(
        redacted_payload=redacted_payload,
        redaction_count=len(events),
        redaction_categories=categories,
        events=tuple(events),
    )


def _is_public_article_reference(container: Mapping[Any, Any], key: str) -> bool:
    normalized = _normalize_key(key)
    reference_type = str(container.get("reference_type") or "").strip().lower()
    manufacturer_visible = container.get("manufacturer_visible") is True
    return (
        normalized in {"value", "reference_type", "source", "manufacturer_visible"}
        and manufacturer_visible
        and reference_type in PUBLIC_REFERENCE_TYPES
    )


def _is_customer_article_reference_value(container: Mapping[Any, Any], key: str) -> bool:
    normalized = _normalize_key(key)
    reference_type = _normalize_key(str(container.get("reference_type") or ""))
    return normalized == "value" and reference_type in CUSTOMER_ARTICLE_KEYS


def _join_path(parent: str, key: str) -> str:
    return f"{parent}.{key}" if parent else key


def _normalize_key(value: str) -> str:
    return str(value or "").replace("-", "_").replace(" ", "_").lower()


def _preserve_marker(text: str, replacement: str) -> str:
    for separator in (":", "=", "#"):
        if separator in text:
            return text.split(separator, 1)[0].rstrip() + separator + " " + replacement
    parts = text.split()
    if len(parts) > 1:
        return " ".join(parts[:-1]) + " " + replacement
    return replacement
