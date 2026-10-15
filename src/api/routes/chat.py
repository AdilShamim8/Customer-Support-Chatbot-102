"""
Chat API routes - main customer support interaction endpoints.
"""

import uuid
from typing import AsyncIterator

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    SourceReference,
)
from src.generation.prompt_engine import PromptConfig, PromptStrategy
from src.pipeline.rag_pipeline import RAGConfig, RAGPipeline
from src.retrieval.retriever import RetrievalConfig

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


def get_pipeline(request: Request) -> RAGPipeline:
    """Dependency: get the shared RAG pipeline from app state."""
    return request.app.state.rag_pipeline


@router.post(
    "/",
    response_model=ChatResponse,
    summary="Send a message to the customer support chatbot",
    description=(
        "Main chat endpoint. Supports single-turn and multi-turn conversations. "
        "Uses RAG to retrieve relevant documentation before generating responses."
    ),
)
async def chat(
    request_body: ChatRequest,
    background_tasks: BackgroundTasks,
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> ChatResponse:
    """Process a customer support message."""

    # Generate conversation ID if not provided
    conversation_id = request_body.conversation_id or str(uuid.uuid4())

    # Build pipeline config from request
    rag_config = RAGConfig(
        retrieval_config=RetrievalConfig(
            filters=request_body.filters,
        ),
        prompt_config=PromptConfig(
            strategy=PromptStrategy(request_body.prompt_strategy.value),
            include_few_shot=True,
            user_metadata=(
                request_body.user_context.model_dump()
                if request_body.user_context
                else {}
            ),
        ),
    )

    # Convert user_context to dict
    user_context = (
        request_body.user_context.model_dump()
        if request_body.user_context
        else None
    )

    try:
        if request_body.stream:
            # Return streaming response
            async def generate_stream() -> AsyncIterator[str]:
                try:
                    for token in pipeline.stream_query(
                        user_query=request_body.message,
                        conversation_id=conversation_id,
                        user_context=user_context,
                    ):
                        yield f"data: {token}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    logger.error("Streaming failed", error=str(e))
                    yield f"data: [ERROR] {str(e)}\n\n"

            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "X-Conversation-ID": conversation_id,
                    "Cache-Control": "no-cache",
                },
            )

        # Non-streaming response
        rag_response = await pipeline.aquery(
            user_query=request_body.message,
            conversation_id=conversation_id,
            user_context=user_context,
        )

        # Compute confidence from retrieval scores
        confidence = 0.0
        if rag_response.retrieval_result.chunks:
            confidence = float(
                sum(c.score for c in rag_response.retrieval_result.chunks)
                / len(rag_response.retrieval_result.chunks)
            )

        return ChatResponse(
            answer=rag_response.answer,
            conversation_id=conversation_id,
            sources=[
                SourceReference(
                    doc_id=s["doc_id"],
                    title=s.get("title", "Unknown"),
                    source=s.get("source", ""),
                    doc_type=s.get("doc_type", ""),
                )
                for s in rag_response.sources
            ],
            confidence=round(confidence, 4),
            reformulated_query=rag_response.reformulated_query,
            metadata={
                "latency_ms": round(rag_response.total_latency_ms, 1),
                "tokens_used": rag_response.llm_response.total_tokens,
                "cost_usd": rag_response.llm_response.cost_usd,
                "retrieval_count": len(rag_response.retrieval_result.chunks),
            },
        )

    except Exception as e:
        logger.error(
            "Chat request failed",
            conversation_id=conversation_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing your request: {str(e)}",
        )


@router.post(
    "/feedback",
    summary="Submit feedback for a chatbot response",
)
async def submit_feedback(
    feedback: FeedbackRequest,
    background_tasks: BackgroundTasks,
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> dict:
    """Record customer feedback for a conversation turn."""

    def _save_feedback():
        logger.info(
            "Feedback received",
            conversation_id=feedback.conversation_id,
            rating=feedback.rating,
            was_helpful=feedback.was_helpful,
            category=feedback.issue_category,
        )
        # In production: save to database for analysis and fine-tuning

    background_tasks.add_task(_save_feedback)

    return {
        "status": "accepted",
        "message": "Thank you for your feedback!",
        "conversation_id": feedback.conversation_id,
    }


@router.delete(
    "/{conversation_id}",
    summary="Clear a conversation session",
)
async def clear_conversation(
    conversation_id: str,
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> dict:
    """Clear conversation history for a given session ID."""
    pipeline.conversation_manager.delete(conversation_id)
    return {
        "status": "cleared",
        "conversation_id": conversation_id,
    }