"""
Health check routes for monitoring and orchestration.
"""

import time

import structlog
from fastapi import APIRouter, Request

from src.api.schemas import HealthResponse

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Health"])

_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """
    Comprehensive health check.
    Checks all downstream components.
    """
    components = {}

    # Check RAG pipeline
    try:
        pipeline = request.app.state.rag_pipeline
        stats = pipeline.get_pipeline_stats()
        components["rag_pipeline"] = "healthy"
        components["vector_store"] = (
            f"healthy ({stats['hybrid_index'].get('vector_store_count', 0)} chunks)"
        )
    except Exception as e:
        components["rag_pipeline"] = f"unhealthy: {str(e)}"

    # Check Redis
    try:
        conv_manager = pipeline.conversation_manager
        if conv_manager._redis:
            conv_manager._redis.ping()
            components["redis"] = "healthy"
        else:
            components["redis"] = "using in-memory (redis unavailable)"
    except Exception as e:
        components["redis"] = f"unhealthy: {str(e)}"

    overall_status = (
        "healthy"
        if all("healthy" in v for v in components.values())
        else "degraded"
    )

    return HealthResponse(
        status=overall_status,
        version="1.0.0",
        components=components,
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@router.get("/ready")
async def readiness_check(request: Request) -> dict:
    """Kubernetes readiness probe endpoint."""
    try:
        pipeline = request.app.state.rag_pipeline
        _ = pipeline.get_pipeline_stats()
        return {"ready": True}
    except Exception:
        from fastapi import Response
        return Response(status_code=503, content="Not ready")


@router.get("/live")
async def liveness_check() -> dict:
    """Kubernetes liveness probe endpoint."""
    return {"alive": True, "uptime": round(time.time() - _start_time, 1)}