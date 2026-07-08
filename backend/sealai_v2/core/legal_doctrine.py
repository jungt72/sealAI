"""Legal/product-doctrine single source (Legal-by-Design, Phase A).

Sibling to ``core.framing`` (the existing per-answer safety-claim-boundary SSoT) — this module
covers the ADJACENT but distinct concern of what sealingAI legally/structurally IS, not what a
single answer's claim-boundary framing says. Both are consumed the same way: a versioned payload
served publicly via an API route, injected into L1/L3 prompts, and rendered in the UI/PDF.

Doctrine (owner-specified, verbatim intent): sealingAI is KI-gestützte Wissens-, Strukturierungs-
und Anfrageintelligenz für Dichtungstechnik — information extraction, case structuring, parameter
mapping, document/upload evaluation as a working basis, inquiry/RFQ preparation, general
explanation, marking uncertainties. It is explicitly NOT a technical-approval, design, expert-
opinion, or product-recommendation engine; final material/design decisions and approval always sit
with the manufacturer / responsible engineer (mirrors ``framing.CLAIM_BOUNDARY``, one level up at
the product-purpose level rather than the per-answer level).

Versioning: ``TERMS_VERSION`` / ``PRIVACY_VERSION`` / ``DPA_VERSION`` are plain date-stamped strings
(NOT content hashes like ``framing.framing_version()``) because the legal PAGE TEXT lives in the
Next.js marketing app (``frontend/src/app/(marketing)/...``), outside this backend's reach — a hash
would silently drift from the page the user actually saw. Bumping a version string here is a
deliberate, reviewed act (mirrors a lawyer-revision release), matching ``framing.py``'s "propagates
within minutes" doctrine for its own version field.
"""

from __future__ import annotations

PRODUCT_PURPOSE_DOCTRINE = (
    "sealingAI ist eine KI-gestützte Wissens-, Strukturierungs- und Anfrageintelligenz für "
    "Dichtungstechnik. sealingAI extrahiert und strukturiert technische Angaben, ordnet Parameter "
    "zu, bewertet hochgeladene Dokumente als Arbeitsgrundlage, bereitet Anfragen/RFQs auf, erklärt "
    "fachliche Zusammenhänge und macht Unsicherheiten sichtbar. sealingAI ist KEINE technische "
    "Freigabe-, Auslegungs-, Gutachter- oder Produktempfehlungs-KI: Es erteilt keine technische "
    "Freigabe, keine verbindliche Auslegung, keine Werkstoff- oder Eignungsfreigabe, keine "
    "Normkonformitäts- oder Sicherheitsbewertung, keine Herstellerfreigabe, kein Prüfgutachten und "
    "keine verbindliche 'geeignet'-Empfehlung. Jede Ausgabe ist ein Arbeitsentwurf; finale "
    "Werkstoff- und Auslegungsentscheidungen sowie jede Freigabe trifft ausschließlich der "
    "Hersteller bzw. die verantwortliche Fachperson."
)

# Plain date-stamped versions (see module docstring for why NOT a content hash). Bump on every
# reviewed text change to the corresponding page; a bump forces re-acceptance (Phase B gate).
TERMS_VERSION = "2026-07-07-v1"
PRIVACY_VERSION = "2026-07-07-v1"
DPA_VERSION = "2026-07-07-v1"

# Legal-Gate onboarding (Goal 3): businessEmail must NOT be a consumer freemail domain — sealingAI
# is a B2B product and the onboarding record (companyName, vatId, ...) presumes a business
# identity. Validated server-side at acceptance-submission time (Phase B), never at the Keycloak
# layer (registration/auth stays untouched — see ``api/routes/legal.py``).
FREEMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "gmx.de",
        "web.de",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
        "t-online.de",
        "aol.com",
        "mail.com",
    }
)


def is_business_email(email: str) -> bool:
    """True unless the domain is a known consumer-freemail domain. Fails permissive-safe on a
    malformed address (no '@') — that case is already rejected by the request's own email format
    validation upstream; this function's only job is the freemail-domain check."""
    domain = email.strip().lower().rsplit("@", 1)[-1]
    return domain not in FREEMAIL_DOMAINS


# Goal 8 UI-vocabulary discipline: terms that imply a technical approval/guarantee this product
# must never claim, mapped to the safe replacement this doctrine actually supports. Reused by (a)
# the L3 forbidden-term check (Goal 7), (b) a terminology-lint test over UI strings/prompts (Goal
# 10), (c) documentation (Goal 11) — one list, three consumers, never drifts apart.
FORBIDDEN_STATUS_TERMS: dict[str, str] = {
    "geeignet": "mögliche Option",
    "freigegeben": "vom Nutzer bestätigt",
    "bestanden": "technische Prüfung erforderlich",
    "approved": "source_detected",
    "validiert": "nicht verifiziert",
    "sicher": "technische Prüfung erforderlich",
    "empfehlung": "Anfrageentwurf",
    "prüfbericht": "technisches Arbeitsblatt",
}

# Goal 6 risk-flag trigger vocabulary (regulated/safety-critical application domains). A hit does
# NOT hard-block — it marks the turn for restriction/review per ``safety/risk_flags.py``, which is
# this list's sole reader in production code (see that module for the full doctrine).
RISK_TRIGGER_TERMS: tuple[str, ...] = (
    "ATEX",
    "Ex-Schutz",
    "Explosionsschutz",
    "Sauerstoff",
    "Oxygen",
    "BAM",
    "FDA",
    "Lebensmittelkontakt",
    "Food contact",
    "Pharma",
    "Medizintechnik",
    "Druckgerät",
    "Pressure Equipment",
    "PED",
    "Maschinenrichtlinie",
    "Maschinenverordnung",
    "CE",
    "Sicherheitsbauteil",
    "Safety component",
    "Wasserstoff",
    "Hydrogen",
    "toxisch",
    "giftig",
    "explosiv",
    "nuklear",
    "Kernkraft",
    "Luftfahrt",
    "Aerospace",
    "Dampf",
    "Heißdampf",
    "Chemieanlage",
    "Gefahrstoff",
    "kritische Infrastruktur",
)


def doctrine_payload() -> dict[str, str]:
    """Public payload for GET /api/v2/legal/doctrine — versions the Legal-Gate frontend compares
    its locally-cached ``acceptedTermsVersion`` etc. against to decide whether re-acceptance is due."""
    return {
        "terms_version": TERMS_VERSION,
        "privacy_version": PRIVACY_VERSION,
        "dpa_version": DPA_VERSION,
        "product_purpose_doctrine": PRODUCT_PURPOSE_DOCTRINE,
    }
