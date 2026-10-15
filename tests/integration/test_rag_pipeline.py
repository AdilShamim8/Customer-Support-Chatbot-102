"""
Integration tests for the full RAG pipeline.
Uses mocked LLM and in-memory stores.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.pipeline.rag_pipeline import RAGPipeline, RAGConfig
from src.pipeline.conversation import ConversationManager
from src.retrieval.retriever import Retriever, RetrievalResult
from src.indexing.vector_store import SearchResult
from src.generation.llm_client import LLMResponse


@pytest.fixture
def mock_retrieval_result():
    """Mock retrieval result with sample chunks."""
    chunks = [
        SearchResult(
            chunk_id="chunk_001",
            doc_id="doc_001",
            content="To reset your password, go to Settings > Account > Reset Password.",
            score=0.95,
            metadata={"title": "Account Guide", "doc_type": "pdf"},
            rank=0,
        )
    ]
    return RetrievalResult(
        query="how to reset password",
        chunks=chunks,
        config=MagicMock(),
        retrieval_metadata={},
    )


@pytest.fixture
def mock_llm_response():
    return LLMResponse(
        content="To reset your password, go to Settings > Account > Reset Password.",
        model="gpt-4-turbo-preview",
        prompt_tokens=500,
        completion_tokens=50,
        total_tokens=550,
        cost_usd=0.0065,
        latency_ms=1200.0,
    )


@pytest.fixture
def rag_pipeline(mock_retrieval_result, mock_llm_response):
    """Create RAG pipeline with mocked components."""
    mock_retriever = MagicMock(spec=Retriever)
    mock_retriever.retrieve.return_value = mock_retrieval_result

    mock_llm = MagicMock()
    mock_llm.complete.return_value = mock_llm_response

    import asyncio
    async def async_complete(*args, **kwargs):
        return mock_llm_response
    mock_llm.acomplete = async_complete

    conversation_manager = ConversationManager(use_redis=False)

    return RAGPipeline(
        retriever=mock_retriever,
        llm_client=mock_llm,
        conversation_manager=conversation_manager,
        config=RAGConfig(),
    )


class TestRAGPipelineIntegration:

    @pytest.mark.asyncio
    async def test_basic_query(self, rag_pipeline):
        response = await rag_pipeline.aquery(
            user_query="How do I reset my password?"
        )
        assert response.answer
        assert isinstance(response.sources, list)
        assert response.total_latency_ms > 0

    @pytest.mark.asyncio
    async def test_conversation_history_maintained(self, rag_pipeline):
        conv_id = "test_conv_001"

        # First turn
        response1 = await rag_pipeline.aquery(
            user_query="How do I reset my password?",
            conversation_id=conv_id,
        )
        assert response1.answer

        # Second turn - should have history
        response2 = await rag_pipeline.aquery(
            user_query="What if I don't receive the email?",
            conversation_id=conv_id,
        )
        assert response2.answer

        # Verify conversation saved
        conv = rag_pipeline.conversation_manager.get(conv_id)
        assert conv is not None
        assert conv.turn_count == 2

    @pytest.mark.asyncio
    async def test_user_context_passed_through(self, rag_pipeline):
        user_context = {
            "customer_name": "Alice Johnson",
            "account_tier": "premium",
            "technical_level": "advanced",
        }

        response = await rag_pipeline.aquery(
            user_query="How do I use the API?",
            user_context=user_context,
        )
        assert response.answer is not None

    @pytest.mark.asyncio
    async def test_response_has_sources(self, rag_pipeline):
        response = await rag_pipeline.aquery(
            user_query="What is the return policy?"
        )
        assert len(response.sources) > 0
        assert response.sources[0]["title"] == "Account Guide"

    def test_pipeline_stats(self, rag_pipeline):
        stats = rag_pipeline.get_pipeline_stats()
        assert "retriever" in stats
        assert "llm_usage" in stats