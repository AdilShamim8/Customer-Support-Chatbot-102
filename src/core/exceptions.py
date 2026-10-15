"""
Core domain exceptions - a single, typed hierarchy.

Design rules (see docs/architecture/adr/0004):
1. Every layer raises a subclass of ChatbotError, never bare Exception.
2. Each exception carries a machine-readable `code` used by the API error
   envelope and by alerting rules - humans get messages, machines get codes.
3. Retryability is explicit (`transient` flag) so the client layer and the
   circuit breaker can act without string matching.
"""

from typing import Any


class ChatbotError(Exception):
    """Base class for all application errors."""

    code: str = "internal_error"
    http_status: int = 500
    transient: bool = False

    def __init__(
        self,
        message: str = "",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serializable form for the API error envelope."""
        return {
            "code": self.code,
            "message": self.message,
            "transient": self.transient,
            "details": self.details,
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ── Configuration ────────────────────────────────────────────────────────────


class ConfigurationError(ChatbotError):
    """Invalid or missing configuration at startup."""

    code = "configuration_error"
    http_status = 500


# ── Retrieval layer ──────────────────────────────────────────────────────────


class RetrievalError(ChatbotError):
    """Base class for retrieval-stage failures."""

    code = "retrieval_error"
    http_status = 502
    transient = True


class IndexNotReadyError(RetrievalError):
    """Vector/keyword index is empty or still warming up."""

    code = "index_not_ready"
    http_status = 503
    transient = True


class IndexCorruptionError(RetrievalError):
    """Index state diverged from source-of-truth store."""

    code = "index_corruption"
    http_status = 503
    transient = False


class EmbeddingError(RetrievalError):
    """Embedding backend failed (quota, timeout, model error)."""

    code = "embedding_error"
    http_status = 502
    transient = True


# ── Generation layer ────────────────────────────────────────────────────────


class GenerationError(ChatbotError):
    """Base class for generation-stage failures."""

    code = "generation_error"
    http_status = 502
    transient = True


class LLMProviderError(GenerationError):
    """Upstream LLM API error (5xx from provider, overload)."""

    code = "llm_provider_error"
    http_status = 502
    transient = True


class LLMSafetyTriggeredError(GenerationError):
    """Provider content filter rejected the request."""

    code = "llm_safety_triggered"
    http_status = 422
    transient = False


class ContextLengthExceededError(GenerationError):
    """Assembled prompt exceeded the model context window."""

    code = "context_length_exceeded"
    http_status = 413
    transient = False


# ── Conversation / state ────────────────────────────────────────────────────


class ConversationError(ChatbotError):
    """Base class for conversation-state failures."""

    code = "conversation_error"
    http_status = 500


class ConversationNotFoundError(ConversationError):
    """Session ID expired or never existed (TTL miss)."""

    code = "conversation_not_found"
    http_status = 404
    transient = True


class ConversationRateLimitedError(ConversationError):
    """Per-conversation throughput guard tripped."""

    code = "conversation_rate_limited"
    http_status = 429
    transient = True


# ── Infrastructure ──────────────────────────────────────────────────────────


class StorageError(ChatbotError):
    """Postgres/Redis connectivity or consistency failure."""

    code = "storage_error"
    http_status = 503
    transient = True


class VectorStoreError(StorageError):
    """Vector database (Chroma/FAISS/Pinecone) failure."""

    code = "vector_store_error"
    http_status = 503
    transient = True


class CacheUnavailableError(StorageError):
    """Redis cache miss on connectivity - degrade, do not crash."""

    code = "cache_unavailable"
    http_status = 200  # service continues in degraded mode
    transient = True


# ── API layer ───────────────────────────────────────────────────────────────


class AuthenticationError(ChatbotError):
    """Invalid or missing API credentials."""

    code = "authentication_error"
    http_status = 401


class RateLimitExceededError(ChatbotError):
    """Client exceeded quota - Retry-After provided in details."""

    code = "rate_limit_exceeded"
    http_status = 429
    transient = True

    def __init__(self, message: str = "", *, retry_after: int = 60, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.details["retry_after"] = retry_after
