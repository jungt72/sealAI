from __future__ import annotations

import json
import logging
import re
from typing import Any, Tuple

logger = logging.getLogger(__name__)

_META_PREAMBLE_RE = re.compile(
    r"^\s*(?:"
    r"(?:hallo|hi|hey|servus|moin)\b[!,.:\s]+"
    r"|(?:guten\s+(?:morgen|tag|abend))\b[!,.:\s]+"
    r"|(?:verstanden|übernommen|gern|natürlich)\b[!,.:\s]+"
    r")",
    re.IGNORECASE,
)


def strip_meta_preamble(text: str) -> str:
    if not text:
        return ""
    stripped = text.lstrip()
    for _ in range(4):
        updated = _META_PREAMBLE_RE.sub("", stripped, count=1).lstrip()
        if updated == stripped:
            break
        stripped = updated
    return stripped


def extract_json_obj(text: str, default: Any = None) -> Tuple[Any, bool]:
    """
    Robustly extract a JSON object from a string.
    Handles markdown code blocks and raw JSON.
    """
    if not text:
        return default, False

    clean_text = text.strip()
    
    # Try to find JSON code block
    match = re.search(r"```(?:json)?(.*?)```", clean_text, re.DOTALL)
    if match:
        clean_text = match.group(1).strip()
    
    try:
        data = json.loads(clean_text)
        return data, True
    except json.JSONDecodeError:
        # Fallback: sometimes LLMs output partial JSON or trailing garbage
        # Simple heuristic: find first { and last }
        start = clean_text.find("{")
        end = clean_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(clean_text[start : end + 1])
                return data, True
            except json.JSONDecodeError:
                pass
        
        logger.warning("json_extraction_failed", text=text[:200])
        return default, False

__all__ = ["strip_meta_preamble", "extract_json_obj"]
