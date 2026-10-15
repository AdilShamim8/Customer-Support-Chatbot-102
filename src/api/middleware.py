"""
FastAPI middleware for request logging, rate limiting, and error handling.
"""

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing and correlation ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Bind request context to all log messages in this request
        structlog.contextvars.bind_contextvars(request_id=request_id)

        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )

        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            logger.info(
                "Request complete",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 1),
            )

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"
            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=round(duration_ms, 1),
                exc_info=True,
            )
            raise
        finally:
            structlog.contextvars.unbind_contextvars("request_id")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiter.
    In production, use Redis-based sliding window rate limiting.
    """

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._request_counts: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/ready", "/live"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - 60.0

        # Clean old entries
        if client_ip in self._request_counts:
            self._request_counts[client_ip] = [
                t for t in self._request_counts[client_ip]
                if t > window_start
            ]
        else:
            self._request_counts[client_ip] = []

        # Check limit
        if len(self._request_counts[client_ip]) >= self.requests_per_minute:
            logger.warning("Rate limit exceeded", client_ip=client_ip)
            return Response(
                content='{"detail": "Rate limit exceeded. Try again in 60 seconds."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        self._request_counts[client_ip].append(now)
        return await call_next(request)