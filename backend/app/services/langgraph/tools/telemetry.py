from __future__ import annotations
import os
try:
    import redis
except Exception:
    redis = None

class Telemetry:
    def __init__(self) -> None:
        self.client = None
        url = os.getenv("REDIS_URL") or os.getenv("REDIS_HOST")
        if redis and url:
            try:
                self.client = redis.Redis.from_url(url) if "://" in url else redis.Redis(host=url, port=int(os.getenv("REDIS_PORT", "6379")))
            except Exception:
                self.client = None

    def incr(self, key: str, amount: int = 1) -> None:
        if self.client:
            try:
                self.client.incr(key, amount)
            except Exception:
                pass

    def set_gauge(self, key: str, value: float) -> None:
        if self.client:
            try:
                self.client.set(key, value)
            except Exception:
                pass

telemetry = Telemetry()
RFQ_GENERATED = "rfq_generated_count"
PARTNER_COVERAGE = "partner_coverage_rate"
MODEL_USAGE = "model_usage_distribution"
NO_MATCH_RATE = "no_match_rate"
