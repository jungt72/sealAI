"""Quick check for RFQ regex coverage in node_router."""

from __future__ import annotations

import re

_RFQ_PATTERNS = re.compile(
    r"\b("
    r"angebot(?:e|s)?\s+(?:einholen|anfordern|senden|erstellen)"
    r"|angebot\s+f(?:u|ue|ü)r"
    r"|ich\s+(?:brauche|ben[oö]tige|m[oö]chte)\s+ein\s+angebot"
    r"|preisanfrage"
    r"|preis\s+f(?:u|ue|ü)r"
    r"|quote\s+for"
    r"|bitte\s+um\s+(?:ein\s+)?angebot"
    r"|rfq\s+(?:senden|erstellen|generieren)"
    r"|anfrage\s+(?:senden|versenden)"
    r"|request\s+for\s+quotation"
    r"|send\s+rfq"
    r"|beschaffung\s+starten"
    r"|einkauf\s+starten"
    r")\b",
    re.IGNORECASE,
)


def main() -> int:
    test_cases = [
        ("Bitte ein Angebot einholen", True),
        ("Send RFQ", True),
        ("Angebot für 100 Dichtungen", True),
        ("Ich brauche ein Angebot für PTFE-Dichtungen", True),
        ("Preisanfrage: 50 Stück FFKM", True),
        ("Preis für Radial-Wellendichtring 50x70x10", True),
        ("Quote for 200 seals", True),
        ("Bitte um Angebot", True),
        ("Was kostet das ungefaehr?", False),
        ("Kann ich ein Angebot bekommen?", False),
    ]

    print("=== RFQ Pattern Test ===")
    passed = 0
    for query, expected in test_cases:
        actual = bool(_RFQ_PATTERNS.search(query))
        ok = actual == expected
        print(f"{'PASS' if ok else 'FAIL'} '{query}' -> Match: {actual} (Expected: {expected})")
        if ok:
            passed += 1
    print(f"Results: {passed}/{len(test_cases)} passed, {len(test_cases) - passed} failed")
    return 0 if passed == len(test_cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
