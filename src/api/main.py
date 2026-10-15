"""
FastAPI Application Entry Point.
Initializes all components and configures the API server.
"""

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from configs.logging_config import setup_logging
from configs.settings import settings
from src.api.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from src.api.routes import chat, admin, health
from src.generation.llm_client import LLMClientFactory
from src.generation.prompt_engine import PromptConfig, PromptStrategy
from src.indexing.embeddings import EmbeddingModelFactory
from src.indexing.hybrid_index import HybridIndex
from src.pipeline.conversation import ConversationManager
from src.pipeline.rag_pipeline import RAGConfig, RAGPipeline
from src.retrieval.retriever import Retriever, RetrievalConfig
from src.retrieval.reranker import RerankerFactory

# Setup logging first
setup_logging()
logger = structlog.get_logger(__name__)


# ─── Application Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application startup and shutdown lifecycle.
    Initializes all shared components.
    """
    logger.info(
        "Starting Customer Support Chatbot",
        env=settings.app_env.value,
        version="1.0.0",
    )

    startup_start = time.time()

    try:
        # ── Initialize Embedding Model ─────────────────────────────────────
        logger.info("Initializing embedding model...")
        embedding_model = EmbeddingModelFactory.create_default()

        # ── Initialize Index ───────────────────────────────────────────────
        logger.info("Initializing hybrid index...")
        hybrid_index = HybridIndex(embedding_model=embedding_model)

        # ── Initialize Reranker ────────────────────────────────────────────
        logger.info("Initializing reranker...")
        reranker = RerankerFactory.create_best_available()

        # ── Initialize Retriever ───────────────────────────────────────────
        retriever = Retriever(
            hybrid_index=hybrid_index,
            reranker=reranker,
        )

        # ── Initialize LLM Client ──────────────────────────────────────────
        logger.info("Initializing LLM client...")
        llm_client = LLMClientFactory.create_default()

        # ── Initialize Conversation Manager ───────────────────────────────
        conversation_manager = ConversationManager(use_redis=True)

        # ── Initialize RAG Pipeline ───────────────────────────────────────
        rag_config = RAGConfig(
            retrieval_config=RetrievalConfig(
                top_k_retrieval=settings.top_k_retrieval,
                top_k_rerank=settings.top_k_rerank,
                similarity_threshold=settings.similarity_threshold,
            ),
            prompt_config=PromptConfig(
                strategy=PromptStrategy.RAG_STANDARD,
                company_name="AcmeCorp",
                include_few_shot=True,
                num_few_shot_examples=2,
            ),
            temperature=0.1,
            max_tokens=settings.max_response_tokens,
            check_hallucination=False,     # Enable in production
            enable_citations=True,
        )

        rag_pipeline = RAGPipeline(
            retriever=retriever,
            llm_client=llm_client,
            conversation_manager=conversation_manager,
            config=rag_config,
        )

        # Store in app state for dependency injection
        app.state.rag_pipeline = rag_pipeline
        app.state.embedding_model = embedding_model

        startup_time = time.time() - startup_start
        logger.info(
            "Application startup complete",
            startup_time_seconds=round(startup_time, 2),
        )

        yield   # Application runs here

    except Exception as e:
        logger.error(
            "Startup failed",
            error=str(e),
            exc_info=True,
        )
        raise

    finally:
        # ── Graceful Shutdown ──────────────────────────────────────────────
        logger.info("Shutting down application...")

        if hasattr(app.state, "rag_pipeline"):
            stats = app.state.rag_pipeline.get_pipeline_stats()
            logger.info(
                "Final usage statistics",
                llm_requests=stats["llm_usage"]["request_count"],
                total_tokens=stats["llm_usage"]["total_tokens"],
                total_cost=f"${stats['llm_usage']['total_cost_usd']:.4f}",
            )

        logger.info("Shutdown complete")


# ─── Application Factory ──────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Customer Support Chatbot API",
        description=(
            "Production RAG-based customer support chatbot. "
            "Uses retrieval-augmented generation with hybrid search, "
            "reranking, and prompt engineering."
        ),
        version="1.0.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters - applied in reverse) ────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else ["https://yourdomain.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.api_rate_limit,
    )

    # ── Prometheus Metrics ─────────────────────────────────────────────────────
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/ready", "/live", "/metrics"],
    ).instrument(app).expose(app)

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    # ── Global Exception Handler ───────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal error occurred",
                "error": str(exc) if settings.is_development else "Internal Server Error",
            },
        )

    return app


# ─── Application Instance ──────────────────────────────────────────────────────

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_config=None,    # Use our structlog config
        workers=1 if settings.is_development else 4,
    )