"""
Unit tests for the exception hierarchy (src/core/exceptions.py).

Contract under test: every application error carries a stable machine
code, an HTTP status mapping, and explicit retryability - the properties
the API envelope, alerting rules, and retry logic all depend on.
"""

import pytest

from src.core.exceptions import (
    AuthenticationError,
    ChatbotError,
    IndexNotReadyError,
    LLMProviderError,
    RateLimitExceededError,
    RetrievalError,
)


class TestChatbotErrorBase:
    def test_default_code_and_status(self):
        err = ChatbotError("boom")
        assert err.code == "internal_error"
        assert err.http_status == 500
        assert err.transient is False

    def test_str_includes_machine_code(self):
        # Log greppability: [code] message
        err = LLMProviderError("upstream 503")
        assert "[llm_provider_error]" in str(err)
        assert "upstream 503" in str(err)

    def test_to_dict_is_serializable_contract(self):
        err = IndexNotReadyError("warming up", details={"index": "support_docs"})
        payload = err.to_dict()
        assert payload["code"] == "index_not_ready"
        assert payload["transient"] is True
        assert payload["details"]["index"] == "support_docs"


class TestRetryabilityContract:
    """The circuit breaker and client retry logic branch on `transient`.

    A wrong flag means either needless retries (non-transient) or a
    missing retry (transient) - both user-visible.
    """

    @pytest.mark.parametrize(
        "exc_class,expected_transient",
        [
            (LLMProviderError, True),      # provider 5xx: retry helps
            (IndexNotReadyError, True),    # warming: retry after backoff
            (AuthenticationError, False),  # bad key: retry is pointless
        ],
    )
    def test_transient_flags(self, exc_class, expected_transient):
        assert exc_class("x").transient is expected_transient


class TestHTTPStatusMapping:
    @pytest.mark.parametrize(
        "exc_class,expected_status",
        [
            (AuthenticationError, 401),
            (RateLimitExceededError, 429),
            (IndexNotReadyError, 503),
            (LLMProviderError, 502),
            (RetrievalError, 502),
        ],
    )
    def test_status_codes(self, exc_class, expected_status):
        assert exc_class("x").http_status == expected_status


class TestRateLimitDetails:
    def test_retry_after_carried_in_details(self):
        err = RateLimitExceededError("slow down", retry_after=120)
        assert err.details["retry_after"] == 120
        assert err.to_dict()["details"]["retry_after"] == 120
