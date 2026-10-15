"""
Unit tests for the rate limiter (src/api/rate_limiter.py).

Rate limiting is the abuse-economics layer (ADR-0006): the contracts
tested here are what keep a flash crowd from becoming a bill, while
Redis loss must never become an outage (fail-open by design).
"""

import pytest


@pytest.fixture
def limiter():
    from src.api.rate_limiter import RedisRateLimiter

    return RedisRateLimiter(requests_per_window=3, window_seconds=60)


def _request(headers=None, client_ip="203.0.113.7"):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": (client_ip, 1234),
            "query_string": b"",
        }
    )


class TestClientIdentification:
    def test_api_key_takes_precedence_over_ip(self, limiter):
        client_id = limiter._get_client_id(
            _request({"X-API-Key": "sk-customer-abc123456789"})
        )
        # Key-based identity: fair limits follow the account, not the NAT IP
        assert client_id.startswith("apikey:")

    def test_forwarded_for_respected(self, limiter):
        client_id = limiter._get_client_id(
            _request({"X-Forwarded-For": "198.51.100.9, 10.0.0.1"})
        )
        assert "198.51.100.9" in client_id

    def test_falls_back_to_direct_ip(self, limiter):
        client_id = limiter._get_client_id(_request())
        assert "203.0.113.7" in client_id

    def test_unknown_client_never_crashes(self, limiter):
        client_id = limiter._get_client_id(_request(client_ip=None))
        assert isinstance(client_id, str)


class TestFailOpenDegradation:
    """Redis down must never take the API down with it (F2 family)."""

    async def test_redis_failure_fails_open(self, limiter, monkeypatch):
        def _explode():
            raise ConnectionError("redis unreachable")

        monkeypatch.setattr(limiter, "_get_redis", _explode)
        # Must not raise - the request passes, the alert path catches it
        await limiter.check_rate_limit(_request())

    async def test_health_endpoints_bypass_limiting(self, limiter, monkeypatch):
        # Probes must never be rate limited or LBs mark pods dead
        called = {"redis": False}

        def _mark():
            called["redis"] = True
            raise AssertionError("health path must not touch redis")

        monkeypatch.setattr(limiter, "_get_redis", _mark)
        for path in ("/health", "/ready", "/live", "/metrics"):
            from starlette.requests import Request

            probe = Request(
                {
                    "type": "http",
                    "method": "GET",
                    "path": path,
                    "headers": [],
                    "client": ("127.0.0.1", 1),
                    "query_string": b"",
                }
            )
            await limiter.check_rate_limit(probe)
        assert called["redis"] is False
