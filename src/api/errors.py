"""
src/api/errors.py — RFC 7807 error envelope for the API layer.

Design (ADR-0004): the single exception hierarchy lives in
src/core/exceptions.py. This module is a pure TRANSLATOR:

    core raises ChatbotError subclass
      → FastAPI handler here
        → RFC 7807 problem+json envelope

The old version of this file defined its own parallel ChatbotError /
RetrievalError / GenerationError classes - duplicated names, drifted
semantics, imported by nothing. That duplication was removed 2026-10-15;
the envelope and the hierarchy are now one design, not two.
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.core.exceptions import ChatbotError

logger = structlog.get_logger(__name__)

ERROR_TYPE_BASE = "https://docs.ragchatbot.example/errors"

# Human titles for the machine-readable codes from core.exceptions.
# Keys are the `code` class attribute values - stable wire contract.
ERROR_TITLES: dict[str, str] = {
    "internal_error": "Internal Server Error",
    "configuration_error": "Configuration Error",
    "retrieval_error": "Retrieval Service Error",
    "index_not_ready": "Index Not Ready",
    "index_corruption": "Index Corrupted",
    "embedding_error": "Embedding Service Error",
    "generation_error": "Generation Service Error",
    "llm_provider_error": "LLM Provider Error",
    "llm_safety_triggered": "Content Filter Triggered",
    "context_length_exceeded": "Context Length Exceeded",
    "conversation_error": "Conversation Error",
    "conversation_not_found": "Conversation Not Found",
    "conversation_rate_limited": "Conversation Rate Limited",
    "storage_error": "Storage Error",
    "vector_store_error": "Vector Store Error",
    "cache_unavailable": "Cache Unavailable",
    "authentication_error": "Authentication Required",
    "rate_limit_exceeded": "Rate Limit Exceeded",
}


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details response - the wire error contract."""

    type: str           # URI reference identifying problem type
    title: str          # Short human-readable summary
    status: int         # HTTP status code
    detail: str         # Specific explanation for this occurrence
    instance: str       # URI reference identifying specific occurrence
    code: str           # Machine-readable application error code
    transient: bool     # Client retryability signal (ADR-0004)
    errors: list[dict[str, Any]] | None = None  # Field-level errors

    class Config:
        use_enum_values = True


def make_problem_response(
    request: Request,
    code: str,
    detail: str,
    status_code: int,
    transient: bool = False,
    errors: list | None = None,
) -> JSONResponse:
    """Create an RFC 7807 compliant error response."""
    problem: dict[str, Any] = {
        "type": f"{ERROR_TYPE_BASE}/{code}",
        "title": ERROR_TITLES.get(code, "Error"),
        "status": status_code,
        "detail": detail,
        "instance": str(request.url),
        "code": code,
        "transient": transient,
    }
    if errors:
        problem["errors"] = errors

    return JSONResponse(
        status_code=status_code,
        content=problem,
        headers={"Content-Type": "application/problem+json"},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all error handlers on the FastAPI app."""

    @app.exception_handler(ChatbotError)
    async def chatbot_error_handler(
        request: Request, exc: ChatbotError
    ) -> JSONResponse:
        """Core hierarchy → problem+json, status and retryability included."""
        logger.warning(
            "Application error",
            code=exc.code,
            detail=exc.message,
            transient=exc.transient,
            path=str(request.url),
        )
        return make_problem_response(
            request=request,
            code=exc.code,
            detail=exc.message,
            status_code=exc.http_status,
            transient=exc.transient,
            errors=exc.details.get("field_errors"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        logger.warning("Validation error", errors=errors, path=str(request.url))
        return make_problem_response(
            request=request,
            code="validation_error",
            detail="Request validation failed",
            status_code=422,
            transient=False,
            errors=errors,
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
        return make_problem_response(
            request=request,
            code="not_found",
            detail="Resource not found",
            status_code=404,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Last-resort: never leak internals, never return a bare 500."""
        logger.error(
            "Unhandled exception",
            path=str(request.url),
            error=str(exc),
            exc_info=True,
        )
        return make_problem_response(
            request=request,
            code="internal_error",
            detail="An internal error occurred",
            status_code=500,
        )
