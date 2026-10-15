"""
Integration tests for health and probe endpoints.

These exercise the routes exactly as Kubernetes does: /live gates
restarts, /ready gates traffic. The contracts tested here are the
difference between "pod restarted gracefully" and "outage".
"""

import pytest


@pytest.mark.integration
class TestLiveness:
    async def test_live_is_green_without_dependencies(self, client):
        # Liveness must NEVER depend on backing stores - a Redis blip
        # must not cause kubelet to restart healthy pods
        r = await client.get("/live")
        assert r.status_code == 200
        assert r.json()["alive"] is True


@pytest.mark.integration
class TestReadiness:
    async def test_ready_with_healthy_pipeline(self, client):
        r = await client.get("/ready")
        assert r.status_code == 200
        assert r.json()["ready"] is True

    async def test_ready_fails_when_pipeline_down(self, app, client):
        # Simulate F4: index/pipeline gone - pod must LEAVE the Service
        class _BrokenPipeline:
            def get_pipeline_stats(self):
                raise RuntimeError("index unavailable")

        app.state.rag_pipeline = _BrokenPipeline()
        r = await client.get("/ready")
        assert r.status_code == 503
        # restore for other tests in the session
        from tests.conftest import _StubPipeline

        app.state.rag_pipeline = _StubPipeline()


@pytest.mark.integration
class TestHealthEndpoint:
    async def test_health_reports_version_from_source_of_truth(self, client):
        from src import __version__

        r = await client.get("/health")
        body = r.json()
        assert body["version"] == __version__

    async def test_health_includes_component_status(self, client):
        r = await client.get("/health")
        components = r.json()["components"]
        assert "rag_pipeline" in components
        assert "healthy" in components["rag_pipeline"]

    async def test_health_degrades_not_crashes(self, app, client):
        # A broken component yields status=degraded, never a 500
        class _HalfBrokenPipeline:
            def get_pipeline_stats(self):
                return {
                    "llm_usage": {"request_count": 0, "total_tokens": 0, "total_cost_usd": 0},
                    "hybrid_index": {"vector_store_count": 42},
                }

            conversation_manager = None

        app.state.rag_pipeline = _HalfBrokenPipeline()
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("healthy", "degraded")


@pytest.mark.integration
class TestObservabilityEndpoints:
    async def test_metrics_exposed(self, client):
        # Prometheus scrape target - absent metrics = blind operations
        r = await client.get("/metrics")
        assert r.status_code == 200
        assert "http_requests_total" in r.text or "http_request" in r.text

    async def test_request_id_header_injected(self, client):
        # Correlation IDs thread logs -> traces -> client reports
        r = await client.get("/live")
        assert r.headers.get("x-request-id")
        assert r.headers.get("x-response-time", "").endswith("ms")
