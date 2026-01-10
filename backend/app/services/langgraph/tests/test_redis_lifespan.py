from app.services.langgraph.redis_lifespan import redact_redis_url


def test_redact_redis_url_does_not_leak_password() -> None:
    url = "redis://:supersecret@redis:6379/0"
    redacted = redact_redis_url(url)
    assert "supersecret" not in redacted
    assert redacted.startswith("redis://")
