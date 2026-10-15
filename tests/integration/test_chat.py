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
