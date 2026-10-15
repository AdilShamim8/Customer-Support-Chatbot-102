"""
src/monitoring/metrics.py — RAG-Specific Metrics for the Customer Support Chatbot
Standard HTTP metrics are not enough for a RAG system.
You need RAG-specific metrics to understand quality in production.
"""

from prometheus_client import Counter, Gauge, Histogram, Summary

# ── RAG Pipeline Metrics ───────────────────────────────────────────────────

# Retrieval metrics
RETRIEVAL_LATENCY = Histogram(
    "rag_retrieval_duration_seconds",
    "Time spent in hybrid retrieval",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    labelnames=["store_type", "use_reranking"],
)

RETRIEVAL_SCORE = Histogram(
    "rag_retrieval_confidence_score",
    "Confidence scores of retrieved chunks",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

CHUNKS_RETRIEVED = Histogram(
    "rag_chunks_retrieved_total",
    "Number of chunks retrieved per query",
    buckets=[1, 2, 3, 5, 7, 10, 15, 20],
)

RETRIEVAL_EMPTY = Counter(
    "rag_empty_retrieval_total",
    "Queries that returned no results",
)

# Generation metrics
GENERATION_LATENCY = Histogram(
    "rag_generation_duration_seconds",
    "Time spent in LLM generation",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    labelnames=["model", "stream"],
)

LLM_TOKENS_USED = Counter(
    "rag_llm_tokens_total",
    "Total LLM tokens consumed",
    labelnames=["model", "token_type"],  # prompt/completion
)

LLM_COST_USD = Counter(
    "rag_llm_cost_usd_total",
    "Total LLM cost in USD",
    labelnames=["model"],
)

LLM_ERRORS = Counter(
    "rag_llm_errors_total",
    "LLM API errors",
    labelnames=["model", "error_type"],
)

# Conversation metrics
ACTIVE_CONVERSATIONS = Gauge(
    "rag_active_conversations",
    "Currently active conversation sessions",
)

CONVERSATION_TURNS = Histogram(
    "rag_conversation_turns",
    "Number of turns per conversation",
    buckets=[1, 2, 3, 5, 10, 20],
)

# Document index metrics
INDEX_SIZE = Gauge(
    "rag_index_chunks_total",
    "Total number of indexed chunks",
    labelnames=["store_type"],
)

INGESTION_LATENCY = Histogram(
    "rag_ingestion_duration_seconds",
    "Time to parse + chunk + index a document",
    labelnames=["doc_type", "chunk_strategy"],
)

# Quality metrics (sampled)
HALLUCINATION_DETECTED = Counter(
    "rag_hallucination_detected_total",
    "Responses flagged as potentially hallucinated",
)

FEEDBACK_RATINGS = Histogram(
    "rag_feedback_rating",
    "Customer feedback ratings",
    buckets=[1, 2, 3, 4, 5],
)

QUERY_REFORMULATIONS = Counter(
    "rag_query_reformulations_total",
    "Follow-up queries that were reformulated",
)


class MetricsInstrumentor:
    """
    Instruments the RAG pipeline with Prometheus metrics.
    Use as context manager or decorator.
    """

    @staticmethod
    def record_retrieval(
        latency_seconds: float,
        chunks_count: int,
        avg_score: float,
        store_type: str = "hybrid",
        use_reranking: bool = True,
    ) -> None:
        RETRIEVAL_LATENCY.labels(
            store_type=store_type,
            use_reranking=str(use_reranking),
        ).observe(latency_seconds)
        CHUNKS_RETRIEVED.observe(chunks_count)
        if avg_score > 0:
            RETRIEVAL_SCORE.observe(avg_score)
        if chunks_count == 0:
            RETRIEVAL_EMPTY.inc()

    @staticmethod
    def record_generation(
        latency_seconds: float,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        streamed: bool = False,
    ) -> None:
        GENERATION_LATENCY.labels(
            model=model,
            stream=str(streamed),
        ).observe(latency_seconds)
        LLM_TOKENS_USED.labels(
            model=model,
            token_type="prompt",
        ).inc(prompt_tokens)
        LLM_TOKENS_USED.labels(
            model=model,
            token_type="completion",
        ).inc(completion_tokens)
        LLM_COST_USD.labels(model=model).inc(cost_usd)

    @staticmethod
    def record_feedback(rating: int) -> None:
        FEEDBACK_RATINGS.observe(rating)

    @staticmethod
    def record_hallucination() -> None:
        HALLUCINATION_DETECTED.inc()

    @staticmethod
    def update_index_size(count: int, store_type: str = "chroma") -> None:
        INDEX_SIZE.labels(store_type=store_type).set(count)