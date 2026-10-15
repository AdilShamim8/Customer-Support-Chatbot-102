"""
Unit tests for API schemas (src/api/schemas.py).

Schemas are the wire contract: validation behavior here is what clients
experience. These tests pin the guards (length limits, enum handling,
defaults) that keep malformed input out of the pipeline.
"""

import pytest
from pydantic import ValidationError

from src.api.schemas import ChatRequest, UserContext


class TestChatRequest:
    def test_minimal_valid_request(self):
        req = ChatRequest(message="What is your return policy?")
        assert req.message
        # Session creation is the route's job; the schema stays permissive
        assert req.conversation_id is None
        assert req.stream is False
        assert req.prompt_strategy.value == "rag_standard"

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_whitespace_message_rejected(self):
        # "   " passes min_length=1 - the validator must catch it
        with pytest.raises(ValidationError):
            ChatRequest(message="   ")

    def test_overlong_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="x" * 2001)

    def test_explicit_conversation_id_preserved(self):
        req = ChatRequest(message="hi", conversation_id="sess-123")
        assert req.conversation_id == "sess-123"


class TestUserContext:
    def test_defaults_are_safe(self):
        ctx = UserContext()
        # Defaults must never assert privileges the caller didn't state
        assert ctx.account_tier == "standard"
        assert ctx.open_tickets == 0
        assert ctx.preferred_language == "en"

    def test_tier_accepts_known_values(self):
        ctx = UserContext(account_tier="premium")
        assert ctx.account_tier == "premium"

    def test_unknown_tier_rejected(self):
        with pytest.raises(ValidationError):
            UserContext(account_tier="ultra-vip-infinite")


class TestWireCompatibility:
    def test_request_roundtrip_dict(self):
        payload = {
            "message": "Where is my order?",
            "conversation_id": "sess-42",
            "user_context": {"account_tier": "premium", "open_tickets": 2},
        }
        req = ChatRequest(**payload)
        assert req.user_context.open_tickets == 2
