from app.services.chat import security


def test_security_detects_pii_email():
    assert security.validate_user_input("Kontakt: alice@example.com") == "possible_pii_detected"


def test_security_allows_regular_text():
    assert security.validate_user_input("Bitte empfehle ein Material für 200°C") is None
