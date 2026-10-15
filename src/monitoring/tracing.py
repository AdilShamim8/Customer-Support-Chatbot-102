"""
src/monitoring/tracing.py — Distributed Tracing for the Customer Support Chatbot
Without distributed tracing you cannot debug:
- Which component is slow in production
- Which queries cause LLM timeouts
- Cross-service request flows
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import structlog

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer("customer-support-chatbot")


def setup_tracing(
    service_name: str = "customer-support-chatbot",
    otlp_endpoint: str = "http://localhost:4317",
    environment: str = "development",
) -> None:
    """
    Initialize OpenTelemetry tracing.
    Exports to OTLP endpoint (Jaeger, Tempo, etc.)
    """
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": environment,
    })

    provider = TracerProvider(resource=resource)

    # Export to OTLP (works with Jaeger, Grafana Tempo, etc.)
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    provider.add_span_processor(
        BatchSpanProcessor(otlp_exporter)
    )

    trace.set_tracer_provider(provider)

    # Auto-instrument libraries
    FastAPIInstrumentor.instrument()
    HTTPXClientInstrumentor.instrument()
    RedisInstrumentor.instrument()

    logger.info(
        "OpenTelemetry tracing initialized",
        service=service_name,
        endpoint=otlp_endpoint,
    )


def trace_retrieval(func):
    """Decorator to trace retrieval operations."""
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        with tracer.start_as_current_span("rag.retrieval") as span:
            query = kwargs.get("query", "")
            span.set_attribute("rag.query", str(query)[:200])
            result = await func(*args, **kwargs)
            if hasattr(result, "chunks"):
                span.set_attribute(
                    "rag.chunks_retrieved", len(result.chunks)
                )
            return result
    return wrapper


def trace_generation(func):
    """Decorator to trace LLM generation."""
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        with tracer.start_as_current_span("rag.generation") as span:
            result = await func(*args, **kwargs)
            if hasattr(result, "total_tokens"):
                span.set_attribute(
                    "llm.total_tokens", result.total_tokens
                )
                span.set_attribute(
                    "llm.cost_usd", result.cost_usd
                )
            return result
    return wrapper