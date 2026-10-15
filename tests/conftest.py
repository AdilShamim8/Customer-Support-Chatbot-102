"""
Shared pytest fixtures.

Design: unit tests never touch the network or containers; integration
tests get real Redis; app-level tests build the FastAPI app with a
stubbed RAG pipeline so route logic is exercised without LLM calls.
"""

import os
from functools import cached_property
from types import SimpleNamespace

import pytest

# Test environment must be set BEFORE importing app/config modules.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


class _StubPipeline:
    """Deterministic stand-in for the RAG pipeline in route tests."""

    def __init__(self) -> None:
        self.calls = 0
        self.seen_config_overrides: list = []
        # The session-clear route calls pipeline.conversation_manager.delete()
        self.conversation_manager = SimpleNamespace(delete=lambda cid: None)

    @cached_property
    def config(self):
        # Imported lazily: the route merges per-request choices onto
        # pipeline.config with dataclasses.replace, so the stub must expose
        # a real RAGConfig. Lazy import keeps the skip-based local design
        # intact (route tests only run where the full stack exists).
        from src.pipeline.rag_pipeline import RAGConfig

        return RAGConfig()

    def get_pipeline_stats(self) -> dict:
        return {
            "llm_usage": {"request_count": 0, "total_tokens": 0, "total_cost_usd": 0.0},
            "hybrid_index": {"vector_store_count": 42},
            "conversation_manager": {"backend": "memory"},
        }

    async def aquery(
        self,
        user_query: str,
        conversation_id: str | None = None,
        user_context: dict | None = None,
        config_override=None,
    ):
        """Record the call and return a minimal well-shaped response."""
        self.calls += 1
        self.seen_config_overrides.append(config_override)
        return SimpleNamespace(
            answer="Stubbed answer.",
            sources=[],
            retrieval_result=SimpleNamespace(chunks=[], sources=[]),
            llm_response=SimpleNamespace(total_tokens=0, cost_usd=0.0),
            reformulated_query=None,
            total_latency_ms=0.0,
        )

    def stream_query(
        self,
        user_query: str,
        conversation_id: str | None = None,
        user_context: dict | None = None,
        config_override=None,
    ):
        """Record the call and yield one token."""
        self.calls += 1
        self.seen_config_overrides.append(config_override)
        yield "stub "
        yield "token"


@pytest.fixture
def stub_pipeline():
    return _StubPipeline()


@pytest.fixture
async def app(stub_pipeline):
    """FastAPI app with stubbed pipeline state - no LLM, no stores.

    Building the app imports the full ML stack (torch, chromadb, faiss,
    elasticsearch...). Where those are not installed, these tests skip
    locally and run in CI (which installs requirements.txt in full).
    """
    pytest.importorskip("openai", reason="full stack not installed locally")
    pytest.importorskip("chromadb", reason="full stack not installed locally")
    from src.api.main import create_app

    application = create_app()
    # The lifespan did not run (no TestClient context) - inject stubs.
    application.state.rag_pipeline = stub_pipeline
    yield application


@pytest.fixture
async def client(app):
    """httpx async client bound to the stubbed app."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def settings_test():
    """Fresh Settings instance for config-mutation tests (bypasses cache)."""
    from configs.settings import Settings

    return Settings(_env_file=None, app_env="test")
