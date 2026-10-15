"""
src/api/rate_limiter.py — Redis-Backed Rate Limiter for the Customer Support Chatbot API
Current in-memory rate limiter breaks with multiple workers.
With 4 Uvicorn workers, each has its own counter → 4x the actual limit.
Need Redis-backed sliding window rate limiter.
"""

import time
from typing import Optional

import structlog
from fastapi import HTTPException, Request, status

logger = structlog.get_logger(__name__)


class RedisRateLimiter:
    """
    Redis-backed sliding window rate limiter.
    Works correctly with multiple API workers.
    """

    def __init__(
        self,
        requests_per_window: int = 60,
        window_seconds: int = 60,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            import redis
            from configs.settings import settings
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis

    def _get_client_id(self, request: Request) -> str:
        """Extract client identifier from request."""
        # Try API key first (more accurate than IP)
        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"apikey:{api_key[:16]}"

        # Fall back to IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"

        return f"ip:{ip}"

    async def check_rate_limit(self, request: Request) -> None:
        """
        Check rate limit using Redis sliding window.
        Raises HTTP 429 if limit exceeded.
        """
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/ready", "/live", "/metrics"]:
            return

        client_id = self._get_client_id(request)
        key = f"ratelimit:{client_id}"

        try:
            r = self._get_redis()
            now = time.time()
            window_start = now - self.window_seconds

            pipe = r.pipeline()
            # Remove old requests outside the window
            pipe.zremrangebyscore(key, 0, window_start)
            # Count requests in current window
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {str(now): now})
            # Set expiry
            pipe.expire(key, self.window_seconds * 2)
            results = pipe.execute()

            request_count = results[1]

            if request_count >= self.requests_per_window:
                logger.warning(
                    "Rate limit exceeded",
                    client_id=client_id,
                    count=request_count,
                    limit=self.requests_per_window,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Too many requests. "
                                   f"Limit: {self.requests_per_window} "
                                   f"per {self.window_seconds}s",
                        "retry_after": self.window_seconds,
                    },
                    headers={
                        "Retry-After": str(self.window_seconds),
                        "X-RateLimit-Limit": str(self.requests_per_window),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(
                            int(now + self.window_seconds)
                        ),
                    },
                )

        except HTTPException:
            raise
        except Exception as e:
            # If Redis fails, allow request (fail open)
            logger.error("Rate limiter Redis error", error=str(e))