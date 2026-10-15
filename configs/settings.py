"""
Central application configuration using Pydantic Settings.
All environment variables are validated and typed here.
"""

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    TEST = "test"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class VectorStoreType(str, Enum):
    CHROMA = "chroma"
    PINECONE = "pinecone"
    FAISS = "faiss"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_env: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    secret_key: str = "dev-secret-key"
    api_rate_limit: int = 100

    # LLM Configuration
    llm_provider: LLMProvider = LLMProvider.OPENAI
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    cohere_api_key: Optional[str] = None

    # Model Names
    chat_model: str = "gpt-4-turbo-preview"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    reranker_model: str = "rerank-english-v3.0"

    # Vector Store
    vector_store_type: VectorStoreType = VectorStoreType.CHROMA
    pinecone_api_key: Optional[str] = None
    pinecone_environment: str = "us-east-1-aws"
    pinecone_index_name: str = "customer-support"
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_collection: str = "support_docs"

    # Search
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_user: str = "elastic"
    elasticsearch_password: str = "password"
    elasticsearch_index: str = "support_docs"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/chatbot_db"

    # Document Processing
    chunk_size: int = 512
    chunk_overlap: int = 64
    min_chunk_size: int = 100

    # RAG Parameters
    top_k_retrieval: int = 10
    top_k_rerank: int = 5
    similarity_threshold: float = 0.7
    max_context_tokens: int = 4096
    max_response_tokens: int = 1024

    # Conversation
    max_conversation_turns: int = 20
    conversation_ttl_seconds: int = 3600  # 1 hour

    # ── Production hardening (added 2026-10-15) ─────────────────────────────
    # Observability
    sentry_dsn: Optional[str] = None
    tracing_enabled: bool = True
    metrics_enabled: bool = True

    # Serving
    request_timeout_seconds: float = 30.0
    stream_first_token_timeout_seconds: float = 10.0
    max_request_body_bytes: int = 262144  # 256 KiB

    # CORS (comma-separated; "*" only permitted in development)
    cors_origins: str = ""

    # Resilience
    llm_max_retries: int = 3
    llm_timeout_seconds: float = 60.0
    retrieval_timeout_seconds: float = 5.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_seconds: int = 30

    # Caching
    semantic_cache_enabled: bool = False
    semantic_cache_ttl_seconds: int = 21600  # 6 hours
    semantic_cache_similarity_threshold: float = 0.95

    # Degradation switches (kill-switch pattern)
    enable_citations: bool = True
    enable_reranking: bool = True
    fallback_message: str = (
        "I'm having trouble connecting to my knowledge systems right now. "
        "A human agent will follow up shortly - or try rephrasing in a moment."
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Parsed CORS origins; empty list means 'default policy'."""
        if self.cors_origins:
            return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        return ["https://ragchatbot1.space-z.ai"] if self.is_production else ["*"]

    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_key(cls, v, values):
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env in (Environment.DEVELOPMENT, Environment.TEST)


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance - call once, reuse everywhere."""
    return Settings()


# Global settings object
settings = get_settings()