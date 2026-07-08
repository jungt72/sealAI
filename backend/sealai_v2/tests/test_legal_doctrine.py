"""core/legal_doctrine.py — the Legal-by-Design doctrine SSoT (Phase A)."""

from __future__ import annotations

from sealai_v2.core.legal_doctrine import (
    DPA_VERSION,
    FORBIDDEN_STATUS_TERMS,
    FREEMAIL_DOMAINS,
    PRIVACY_VERSION,
    PRODUCT_PURPOSE_DOCTRINE,
    RISK_TRIGGER_TERMS,
    TERMS_VERSION,
    doctrine_payload,
    is_business_email,
)


def test_doctrine_payload_carries_all_three_versions_and_the_text():
    p = doctrine_payload()
    assert p["terms_version"] == TERMS_VERSION
    assert p["privacy_version"] == PRIVACY_VERSION
    assert p["dpa_version"] == DPA_VERSION
    assert p["product_purpose_doctrine"] == PRODUCT_PURPOSE_DOCTRINE


def test_doctrine_text_names_the_allowed_and_forbidden_purposes():
    # Loose substring checks — proves the doctrine text actually encodes the owner's stated
    # boundary, not just that SOME string exists.
    d = PRODUCT_PURPOSE_DOCTRINE
    for allowed in ("Wissens-", "Strukturierungs-", "Anfrageintelligenz"):
        assert allowed in d
    for forbidden in ("KEINE technische", "Freigabe", "Prüfgutachten", "geeignet"):
        assert forbidden in d


def test_is_business_email_rejects_every_listed_freemail_domain():
    for domain in FREEMAIL_DOMAINS:
        assert is_business_email(f"user@{domain}") is False


def test_is_business_email_accepts_a_company_domain():
    assert is_business_email("einkauf@acme-dichtungen.example") is True


def test_is_business_email_is_case_insensitive():
    assert is_business_email("USER@GMAIL.COM") is False


def test_is_business_email_uses_the_last_at_segment_as_domain():
    # a display-name-in-local-part edge case must not confuse the domain split
    assert is_business_email("a@b@gmail.com") is False


def test_forbidden_status_terms_map_is_non_empty_and_lowercase_keyed():
    assert len(FORBIDDEN_STATUS_TERMS) > 0
    assert all(k == k.lower() for k in FORBIDDEN_STATUS_TERMS)


def test_risk_trigger_terms_cover_the_owner_specified_list():
    for must_have in ("ATEX", "Sauerstoff", "FDA", "Maschinenrichtlinie", "Wasserstoff", "CE"):
        assert must_have in RISK_TRIGGER_TERMS
