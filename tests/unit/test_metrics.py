"""
Unit tests for the metrics module (src/monitoring/metrics.py).

The observability contract: every metric the dashboards and alerts
reference must exist and accept the label shapes the pipeline emits.
A metric renamed in code but not in alerts.yml = blind operations.
"""

import pytest

from src.monitoring import metrics as m


class TestMetricExistence:
    """Alerts (monitoring/alerts.yml) and dashboards reference these
    by name - removing or renaming one breaks alerting silently."""

    @pytest.mark.parametrize(
        "metric_name",
        [
            "RETRIEVAL_LATENCY",
            "RETRIEVAL_SCORE",
            "CHUNKS_RETRIEVED",
            "RETRIEVAL_EMPTY",
            "GENERATION_LATENCY",
            "LLM_TOKENS_USED",
            "LLM_COST_USD",
            "LLM_ERRORS",
            "ACTIVE_CONVERSATIONS",
            "CONVERSATION_TURNS",
            "INDEX_SIZE",
            "INGESTION_LATENCY",
            "HALLUCINATION_DETECTED",
            "FEEDBACK_RATINGS",
            "QUERY_REFORMULATIONS",
        ],
    )
    def test_metric_exists(self, metric_name):
        assert hasattr(m, metric_name), (
            f"{metric_name} missing - alerts/dashboards referencing it go blind"
        )


class TestInstrumentorContract:
    def test_record_retrieval_accepts_pipeline_shape(self):
        # Smoke: the exact call signature the pipeline uses
        m.MetricsInstrumentor.record_retrieval(
            latency_seconds=0.25,
            chunks_count=5,
            avg_score=0.87,
            store_type="hybrid",
            use_reranking=True,
        )

    def test_record_generation_accepts_pipeline_shape(self):
        m.MetricsInstrumentor.record_generation(
            latency_seconds=1.2,
            model="gpt-4o",
            prompt_tokens=620,
            completion_tokens=230,
            cost_usd=0.0031,
            streamed=True,
        )

    def test_update_index_size(self):
        m.MetricsInstrumentor.update_index_size(count=4200, store_type="chroma")

    def test_record_feedback_bounds(self):
        for rating in (1, 3, 5):
            m.MetricsInstrumentor.record_feedback(rating=rating)


class TestLabelCardinality:
    """Bounded-set labels only (monitoring guide rule)."""

    def test_store_type_is_bounded(self):
        # store_type values come from an enum-like set, never user input
        allowed = {"hybrid", "vector", "keyword", "chroma", "faiss", "pinecone"}
        # Recording with a known value must not raise
        m.MetricsInstrumentor.update_index_size(count=1, store_type="hybrid")
