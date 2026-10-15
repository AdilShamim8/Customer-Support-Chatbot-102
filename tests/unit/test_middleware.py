"""
Unit tests for request middleware (src/api/middleware.py).

The contracts: every response carries a correlation ID, and the timing
header is populated - these are what tie a user complaint to its trace
and log lines in an incident.
"""

import pytest

pytest.importorskip("openai", reason="full stack not installed locally")


@pytest.fixture
def bare_app(stub_pipeline):
    from src.api.main import create_app

    app = create_app()
    app.state.rag_pipeline = stub_pipeline
    return app


class TestRequestLoggingMiddleware:
    async def test_request_id_header_on_every_response(self, bare_app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=bare_app), base_url="http://t") as c:
            for path in ("/live", "/ready", "/health"):
                r = await c.get(path)
                assert r.headers.get("x-request-id"), f"{path} missing request ID"

    async def test_request_ids_are_unique_per_request(self, bare_app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=bare_app), base_url="http://t") as c:
            ids = {(await c.get("/live")).headers["x-request-id"] for _ in range(20)}
        # Correlation IDs that repeat = logs that lie
        assert len(ids) == 20

    async def test_response_time_header_format(self, bare_app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=bare_app), base_url="http://t") as c:
            r = await c.get("/live")
            assert r.headers.get("x-response-time", "").endswith("ms")
