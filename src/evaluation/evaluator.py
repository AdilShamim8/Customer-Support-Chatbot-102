"""
RAG Evaluation Orchestrator.
Runs comprehensive evaluation pipelines and generates reports.
Supports batch evaluation, dataset-level reporting, and pass/fail thresholds.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import structlog
from tqdm import tqdm

from src.evaluation.metrics import (
    EvaluationResult,
    EvaluationSample,
    LLMJudge,
    MetricScore,
    StatisticalMetrics,
)
from src.pipeline.rag_pipeline import RAGPipeline

logger = structlog.get_logger(__name__)


# ─── Evaluation Report ────────────────────────────────────────────────────────

@dataclass
class EvaluationReport:
    """
    Aggregate evaluation report for a dataset.
    Contains per-metric averages, distributions, and pass rates.
    """
    dataset_name: str
    total_samples: int
    results: list[EvaluationResult] = field(default_factory=list)
    metric_averages: dict[str, float] = field(default_factory=dict)
    metric_std: dict[str, float] = field(default_factory=dict)
    pass_rates: dict[str, float] = field(default_factory=dict)
    overall_pass_rate: float = 0.0
    evaluation_time_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)

    def compute_aggregates(self) -> None:
        """Compute aggregate statistics from individual results."""
        if not self.results:
            return

        # Collect scores per metric
        metric_scores: dict[str, list[float]] = {}
        metric_passed: dict[str, list[bool]] = {}

        for result in self.results:
            for metric_name, score in result.scores.items():
                if metric_name not in metric_scores:
                    metric_scores[metric_name] = []
                    metric_passed[metric_name] = []
                metric_scores[metric_name].append(score.score)
                metric_passed[metric_name].append(score.passed)

        # Compute averages and pass rates
        for metric_name, scores in metric_scores.items():
            self.metric_averages[metric_name] = float(np.mean(scores))
            self.metric_std[metric_name] = float(np.std(scores))
            self.pass_rates[metric_name] = float(
                np.mean([1.0 if p else 0.0 for p in metric_passed[metric_name]])
            )

        # Overall pass rate
        self.overall_pass_rate = float(
            np.mean([1.0 if r.passed else 0.0 for r in self.results])
        )

    def to_dict(self) -> dict:
        return {
            "dataset_name": self.dataset_name,
            "total_samples": self.total_samples,
            "overall_pass_rate": round(self.overall_pass_rate, 4),
            "evaluation_time_seconds": round(self.evaluation_time_seconds, 2),
            "metric_averages": {
                k: round(v, 4) for k, v in self.metric_averages.items()
            },
            "metric_std": {
                k: round(v, 4) for k, v in self.metric_std.items()
            },
            "pass_rates": {
                k: round(v, 4) for k, v in self.pass_rates.items()
            },
            "metadata": self.metadata,
        }

    def save(self, output_path: str) -> None:
        """Save report to JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "summary": self.to_dict(),
            "results": [r.to_dict() for r in self.results],
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info("Evaluation report saved", path=str(path))

    def print_summary(self) -> None:
        """Print a formatted summary to console."""
        print("\n" + "=" * 60)
        print(f"  RAG EVALUATION REPORT: {self.dataset_name}")
        print("=" * 60)
        print(f"  Total Samples:     {self.total_samples}")
        print(f"  Overall Pass Rate: {self.overall_pass_rate:.1%}")
        print(f"  Evaluation Time:   {self.evaluation_time_seconds:.1f}s")
        print("\n  Metric Scores:")
        print("  " + "-" * 50)

        for metric, avg in sorted(self.metric_averages.items()):
            std = self.metric_std.get(metric, 0.0)
            pass_rate = self.pass_rates.get(metric, 0.0)
            status = "✅" if pass_rate >= 0.8 else "⚠️" if pass_rate >= 0.6 else "❌"
            print(
                f"  {status} {metric:<25} "
                f"avg={avg:.3f} ± {std:.3f}  "
                f"pass={pass_rate:.1%}"
            )

        print("=" * 60 + "\n")


# ─── Evaluator ────────────────────────────────────────────────────────────────

class RAGEvaluator:
    """
    End-to-end RAG evaluation orchestrator.
    Evaluates a RAG pipeline against labeled test datasets.

    Metrics evaluated:
    - Context Relevance  (LLM-based)
    - Faithfulness       (LLM-based)
    - Answer Relevance   (LLM-based)
    - Answer Correctness (LLM-based, requires ground truth)
    - Context Recall     (statistical)
    - ROUGE-L            (statistical, requires ground truth)
    - Citation Precision (statistical)
    - Answer Length      (statistical)
    """

    def __init__(
        self,
        rag_pipeline: Optional[RAGPipeline] = None,
        llm_judge: Optional[LLMJudge] = None,
        use_llm_metrics: bool = True,
        use_statistical_metrics: bool = True,
    ):
        self.pipeline = rag_pipeline
        self.llm_judge = llm_judge or LLMJudge()
        self.stat_metrics = StatisticalMetrics()
        self.use_llm_metrics = use_llm_metrics
        self.use_statistical_metrics = use_statistical_metrics

    def evaluate_sample(
        self,
        sample: EvaluationSample,
    ) -> EvaluationResult:
        """
        Run all metrics on a single sample.
        Can evaluate pre-generated answers or run the pipeline live.
        """
        result = EvaluationResult(sample=sample)

        # ── LLM-Based Metrics ─────────────────────────────────────────────────
        if self.use_llm_metrics:

            # 1. Context Relevance
            if sample.contexts:
                ctx_relevance = self.llm_judge.evaluate_context_relevance(
                    question=sample.question,
                    contexts=sample.contexts,
                )
                result.add_score(ctx_relevance)

            # 2. Faithfulness
            if sample.answer and sample.contexts:
                faithfulness = self.llm_judge.evaluate_faithfulness(
                    question=sample.question,
                    answer=sample.answer,
                    contexts=sample.contexts,
                )
                result.add_score(faithfulness)

            # 3. Answer Relevance
            if sample.answer:
                answer_relevance = self.llm_judge.evaluate_answer_relevance(
                    question=sample.question,
                    answer=sample.answer,
                )
                result.add_score(answer_relevance)

            # 4. Answer Correctness (requires ground truth)
            if sample.answer and sample.ground_truth:
                correctness = self.llm_judge.evaluate_answer_correctness(
                    question=sample.question,
                    answer=sample.answer,
                    ground_truth=sample.ground_truth,
                )
                result.add_score(correctness)

        # ── Statistical Metrics ───────────────────────────────────────────────
        if self.use_statistical_metrics:

            # 5. Context Recall
            if sample.answer and sample.contexts:
                ctx_recall = self.stat_metrics.context_recall(
                    answer=sample.answer,
                    contexts=sample.contexts,
                )
                result.add_score(ctx_recall)

            # 6. ROUGE Score (requires ground truth)
            if sample.answer and sample.ground_truth:
                rouge = self.stat_metrics.rouge_score(
                    prediction=sample.answer,
                    reference=sample.ground_truth,
                )
                result.add_score(rouge)

            # 7. Answer Length
            if sample.answer:
                length_score = self.stat_metrics.answer_length_score(
                    answer=sample.answer
                )
                result.add_score(length_score)

            # 8. Citation Precision
            if sample.answer:
                sources = sample.metadata.get("source_titles", [])
                if sources:
                    citation = self.stat_metrics.citation_precision(
                        answer=sample.answer,
                        source_titles=sources,
                    )
                    result.add_score(citation)

        # Compute overall score
        result.compute_overall()
        return result

    def evaluate_pipeline(
        self,
        test_samples: list[EvaluationSample],
        dataset_name: str = "test_dataset",
        max_samples: Optional[int] = None,
    ) -> EvaluationReport:
        """
        Evaluate the full RAG pipeline on a test dataset.
        Runs the pipeline to generate answers, then evaluates them.
        """
        if not self.pipeline:
            raise ValueError("RAG pipeline required for pipeline evaluation")

        samples = test_samples[:max_samples] if max_samples else test_samples

        logger.info(
            "Starting pipeline evaluation",
            dataset=dataset_name,
            samples=len(samples),
        )

        report = EvaluationReport(
            dataset_name=dataset_name,
            total_samples=len(samples),
        )

        start_time = time.time()

        for sample in tqdm(samples, desc=f"Evaluating {dataset_name}"):
            try:
                # Run pipeline to get answer and contexts
                rag_response = self.pipeline.query(user_query=sample.question)

                # Populate sample with pipeline outputs
                eval_sample = EvaluationSample(
                    question=sample.question,
                    answer=rag_response.answer,
                    contexts=[
                        chunk.content
                        for chunk in rag_response.retrieval_result.chunks
                    ],
                    ground_truth=sample.ground_truth,
                    question_id=sample.question_id,
                    metadata={
                        **sample.metadata,
                        "source_titles": [
                            s.get("title", "") for s in rag_response.sources
                        ],
                    },
                )

                result = self.evaluate_sample(eval_sample)
                report.results.append(result)

            except Exception as e:
                logger.error(
                    "Sample evaluation failed",
                    question=sample.question[:80],
                    error=str(e),
                )

        report.evaluation_time_seconds = time.time() - start_time
        report.compute_aggregates()

        logger.info(
            "Pipeline evaluation complete",
            dataset=dataset_name,
            samples_evaluated=len(report.results),
            overall_pass_rate=f"{report.overall_pass_rate:.1%}",
        )

        return report

    def evaluate_answers(
        self,
        samples: list[EvaluationSample],
        dataset_name: str = "offline_eval",
    ) -> EvaluationReport:
        """
        Evaluate pre-generated answers without running the pipeline.
        Useful for offline/batch evaluation.
        """
        report = EvaluationReport(
            dataset_name=dataset_name,
            total_samples=len(samples),
        )

        start_time = time.time()

        for sample in tqdm(samples, desc=f"Evaluating {dataset_name}"):
            try:
                result = self.evaluate_sample(sample)
                report.results.append(result)
            except Exception as e:
                logger.error(
                    "Sample evaluation failed",
                    question=sample.question[:80],
                    error=str(e),
                )

        report.evaluation_time_seconds = time.time() - start_time
        report.compute_aggregates()
        return report


# ─── RAGAS Integration ────────────────────────────────────────────────────────

class RAGASEvaluator:
    """
    Integration with the RAGAS evaluation framework.
    RAGAS provides standardized RAG evaluation benchmarks.
    """

    def evaluate(
        self,
        questions: list[str],
        answers: list[str],
        contexts: list[list[str]],
        ground_truths: Optional[list[str]] = None,
    ) -> dict:
        """Run RAGAS evaluation suite."""
        try:
            from ragas import evaluate
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
                context_relevancy,
            )
            from datasets import Dataset

            data = {
                "question": questions,
                "answer": answers,
                "contexts": contexts,
            }

            metrics = [
                faithfulness,
                answer_relevancy,
                context_relevancy,
                context_precision,
            ]

            if ground_truths:
                data["ground_truth"] = ground_truths
                metrics.append(context_recall)

            dataset = Dataset.from_dict(data)
            result = evaluate(dataset, metrics=metrics)

            return result.to_pandas().to_dict(orient="records")[0]

        except ImportError:
            logger.warning("RAGAS not installed, skipping RAGAS evaluation")
            return {}
        except Exception as e:
            logger.error("RAGAS evaluation failed", error=str(e))
            return {}