from app.api.v1.endpoints.ai import _beratung_thread_id


def test_beratung_thread_id_scopes_by_user() -> None:
    key_a = _beratung_thread_id("userA", "same")
    key_b = _beratung_thread_id("userB", "same")
    assert key_a != key_b
    assert "userA" in key_a
