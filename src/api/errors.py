"""
src/api/errors.py — Error Handling for the Customer Support Chatbot API
RFC 7807 Problem Details for HTTP APIs.
Inconsistent errors break API clients.
"""

from enum import Enum
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)


class ErrorCode(str, Enum):
    """Application-specific error codes."""
    # Auth errors
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    INVALID_API_KEY = "invalid_api_key"

    # Validation errors
    VALIDATION_ERROR = "validation_error"
    INVALID_FILE_TYPE = "invalid_file_type"
    MESSAGE_TOO_LONG = "message_too_long"
    MESSAGE_EMPTY = "message_empty"

    # RAG errors
    NO_RESULTS_FOUND = "no_results_found"
    RETRIEVAL_FAILED = "retrieval_failed"
    GENERATION_FAILED = "generation_failed"
    CONTEXT_TOO_LONG = "context_too_long"

    # Resource errors
    CONVERSATION_NOT_FOUND = "conversation_not_found"
    DOCUMENT_NOT_FOUND = "document_not_found"
    DOCUMENT_ALREADY_EXISTS = "document_already_exists"

    # System errors
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SERVICE_UNAVAILABLE = "service_unavailable"
    LLM_API_ERROR = "llm_api_error"
    INTERNAL_ERROR = "internal_error"


class ProblemDetail(BaseModel):
    """
    RFC 7807 Problem Details response.
    Standard error format for all API errors.
    """
    type: str           # URI reference identifying problem type
    title: str          # Short human-readable summary
    status: int         # HTTP status code
    detail: str         # Specific explanation for this occurrence
    instance: str       # URI reference identifying specific occurrence
    code: ErrorCode     # Application error code
    errors: Optional[list[dict[str, Any]]] = None  # Field-level errors

    class Config:
        use_enum_values = True


class ChatbotError(Exception):
    """Base exception for all chatbot errors."""

    def __init__(
        self,
        code: ErrorCode,
        detail: str,
        status_code: int = 500,
        errors: Optional[list] = None,
    ):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.errors = errors
        super().__init__(detail)


class RetrievalError(ChatbotError):
    def __init__(self, detail: str):
        super().__init__(
            code=ErrorCode.RETRIEVAL_FAILED,
            detail=detail,
            status_code=503,
        )


class GenerationError(ChatbotError):
    def __init__(self, detail: str):
        super().__init__(
            code=ErrorCode.GENERATION_FAILED,
            detail=detail,
            status_code=503,
        )


class NoResultsError(ChatbotError):
    def __init__(self, query: str):
        super().__init__(
            code=ErrorCode.NO_RESULTS_FOUND,
            detail=f"No relevant documents found for: '{query[:100]}'",
            status_code=404,
        )


ERROR_TYPE_BASE = "https://chatbot.yourcompany.com/errors"

ERROR_TITLES = {
    ErrorCode.UNAUTHORIZED: "Authentication Required",
    ErrorCode.FORBIDDEN: "Access Denied",
    ErrorCode.VALIDATION_ERROR: "Request Validation Failed",
    ErrorCode.NO_RESULTS_FOUND: "No Results Found",
    ErrorCode.RETRIEVAL_FAILED: "Retrieval Service Error",
    ErrorCode.GENERATION_FAILED: "Generation Service Error",
    ErrorCode.RATE_LIMIT_EXCEEDED: "Rate Limit Exceeded",
    ErrorCode.INTERNAL_ERROR: "Internal Server Error",
    ErrorCode.LLM_API_ERROR: "LLM Provider Error",
}


def make_problem_response(
    request: Request,
    code: ErrorCode,
    detail: str,
    status_code: int,
    errors: Optional[list] = None,
) -> JSONResponse:
    """Create RFC 7807 compliant error response."""
    problem = {
        "type": f"{ERROR_TYPE_BASE}/{code.value}",
        "title": ERROR_TITLES.get(code, "Error"),
        "status": status_code,
        "detail": detail,
        "instance": str(request.url),
        "code": code.value,
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
        logger.warning(
            "Application error",
            code=exc.code.value,
            detail=exc.detail,
            path=str(request.url),
        )
        return make_problem_response(
            request=request,
            code=exc.code,
            detail=exc.detail,
            status_code=exc.status_code,
            errors=exc.errors,
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
        logger.warning(
            "Validation error",
            errors=errors,
            path=str(request.url),
        )
        return make_problem_response(
            request=request,
            code=ErrorCode.VALIDATION_ERROR,
            detail="Request validation failed. Check the 'errors' field.",
            status_code=422,
            errors=errors,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        code_map = {
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.DOCUMENT_NOT_FOUND,
            429: ErrorCode.RATE_LIMIT_EXCEEDED,
            500: ErrorCode.INTERNAL_ERROR,
            503: ErrorCode.SERVICE_UNAVAILABLE,
        }
        code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return make_problem_response(
            request=request,
            code=code,
            detail=str(exc.detail),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            error=str(exc),
            error_type=type(exc).__name__,
            path=str(request.url),
            exc_info=True,
        )
        from configs.settings import settings
        detail = (
            str(exc) if settings.is_development
            else "An internal error occurred."
        )
        return make_problem_response(
            request=request,
            code=ErrorCode.INTERNAL_ERROR,
            detail=detail,
            status_code=500,
        )