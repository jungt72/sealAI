from __future__ import annotations

import re

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
