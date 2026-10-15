"""
Shared pytest fixtures.

Design: unit tests never touch the network or containers; integration
tests get real Redis; app-level tests build the FastAPI app with a
stubbed RAG pipeline so route logic is exercised without LLM calls.
"""

import os

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

    def get_pipeline_stats(self) -> dict:
        return {
            "llm_usage": {"request_count": 0, "total_tokens": 0, "total_cost_usd": 0.0},
            "hybrid_index": {"vector_store_count": 42},
            "conversation_manager": {"backend": "memory"},
        }


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
