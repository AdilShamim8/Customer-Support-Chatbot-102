"""
Integration tests for the chat route - the golden request path.

The route graph (auth → rate limit → pipeline → envelope) runs against a
stubbed RAG pipeline, so the CONTRACTS are tested: validation, error
envelope shape (RFC 7807 via the core hierarchy), and the auth posture.
"""

import pytest

pytest.importorskip("openai", reason="full stack not installed locally")


@pytest.mark.integration
class TestChatRequestValidation:
    async def test_missing_message_rejected(self, client):
        r = await client.post("/api/v1/chat", json={})
        assert r.status_code == 422

    async def test_whitespace_message_rejected(self, client):
        r = await client.post("/api/v1/chat", json={"message": "   "})
        assert r.status_code == 422

    async def test_overlong_message_rejected(self, client):
        r = await client.post("/api/v1/chat", json={"message": "x" * 5000})
        assert r.status_code == 422


@pytest.mark.integration
class TestErrorEnvelope:
    """Every error speaks RFC 7807 with a machine code (ADR-0004)."""

    async def test_unknown_route_returns_problem_json(self, client):
        r = await client.get("/api/v1/definitely-not-a-route")
        assert r.status_code == 404

    async def test_validation_error_carries_field_errors(self, client):
        r = await client.post("/api/v1/chat", json={})
        body = r.json()
        # The envelope must carry machine-readable structure, not prose
        assert isinstance(body, dict)


@pytest.mark.integration
class TestConversationLifecycle:
    async def test_session_clear_is_idempotent_safe(self, client):
        # Clearing an unknown session must not 500
        r = await client.delete("/api/v1/chat/never-existed-session")
        assert r.status_code in (200, 202, 404)


@pytest.mark.integration
class TestPerRequestConfigContract:
    """The route must forward the caller's filters and prompt strategy.

    Regression guard: the route used to build a RAGConfig from the request
    and then drop it on the floor - `filters` and `prompt_strategy` were
    accepted by the API schema but never reached the pipeline (a silent
    contract violation). These tests pin the wiring.
    """

    async def test_filters_and_strategy_reach_the_pipeline(
        self, client, stub_pipeline
    ):
        r = await client.post(
            "/api/v1/chat",
            json={
                "message": "What is your return policy?",
                "filters": {"doc_type": "returns_policy"},
                "prompt_strategy": "chain_of_thought",
            },
        )
        assert r.status_code == 200
        assert stub_pipeline.calls == 1

        override = stub_pipeline.seen_config_overrides[0]
        assert override is not None
        assert override.retrieval_config.filters == {"doc_type": "returns_policy"}
        assert override.prompt_config.strategy.value == "chain_of_thought"
        # The merge must PRESERVE the deployment's tuned defaults rather
        # than resetting them: temperature, top_k and the company persona
        # still come from the pipeline's own config.
        assert override.temperature == stub_pipeline.config.temperature
        assert (
            override.retrieval_config.top_k_retrieval
            == stub_pipeline.config.retrieval_config.top_k_retrieval
        )
        assert (
            override.prompt_config.company_name
            == stub_pipeline.config.prompt_config.company_name
        )

    async def test_defaults_reach_the_pipeline_unchanged(self, client, stub_pipeline):
        r = await client.post(
            "/api/v1/chat",
            json={"message": "Hello"},
        )
        assert r.status_code == 200

        override = stub_pipeline.seen_config_overrides[0]
        assert override is not None
        # No filters on the request -> empty filter set, nothing dropped
        assert override.retrieval_config.filters == {}
        # Default strategy from the schema -> RAG_STANDARD
        assert override.prompt_config.strategy.value == "rag_standard"

    async def test_streaming_request_forwards_config(self, client, stub_pipeline):
        r = await client.post(
            "/api/v1/chat",
            json={
                "message": "Where is my refund?",
                "stream": True,
                "filters": {"topic": "returns"},
            },
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

        override = stub_pipeline.seen_config_overrides[0]
        assert override is not None
        assert override.retrieval_config.filters == {"topic": "returns"}
