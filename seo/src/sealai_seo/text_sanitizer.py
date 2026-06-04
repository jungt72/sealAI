from __future__ import annotations

import re
import unicodedata

QUERY_TAINT = "untrusted_user_search_query"


def sanitize_text(value: str, max_length: int = 512) -> str:
    normalized = unicodedata.normalize("NFC", value)
    no_controls = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in normalized)
    collapsed = re.sub(r"\s+", " ", no_controls).strip()
    return collapsed[:max_length]


def escape_markdown(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for ch in "|`*_{}[]()#+-.!":
        escaped = escaped.replace(ch, f"\\{ch}")
    return escaped
