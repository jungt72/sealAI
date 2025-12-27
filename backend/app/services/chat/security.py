from __future__ import annotations

import os
import re
from typing import Optional

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\d{3}[\s.-]?){2}\d{3,4}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def _pii_check(text: str) -> bool:
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text) or CARD_RE.search(text))


def validate_user_input(text: str) -> Optional[str]:
    if not text:
        return "input_empty"
    if _pii_check(text):
        return "possible_pii_detected"
    return None

