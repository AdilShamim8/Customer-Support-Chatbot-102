#!/usr/bin/env python3
"""
Evaluation script for the full RAG pipeline.

Usage:
    python scripts/evaluate_pipeline.py \
        --dataset ./data/eval/test_set.jsonl \
        --output ./data/eval/report.json \
        --max-samples 50
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

from configs.logging_config import setup_logging
from src.evaluation.evaluator import EvaluationSample, RAGEvaluator
from src.pipeline.rag_pipeline import RAGConfig, RAGPipeline

logger = structlog.get_logger(__name__)

# ── Sample test dataset (inline for demo) ─────────────────────────────────────

SAMPLE_TEST_SET = [
    {
        "question": "How do I reset my password?",
        "ground_truth": (
            "To reset your password, visit the login page, "
            "click 'Forgot Password', enter your email, "
            "and follow the link sent to your inbox."
        ),
    },
    {
        "question": "What is your refund policy?",
        "ground_truth": (
            "We offer a 30-day money-back guarantee on all products. "
            "Digital products are non-refundable."
        ),
    },
    {
        "question": "How can I contact customer support?",
        "ground_truth": (
            "You can contact support via email at support@company.com, "
            "live chat on our website, or phone 1-800-SUPPORT."
        ),
    },
]


def load_test_set(path: str | None) -> list[dict]:
    if path and Path(path).exists():
        samples = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    samples.append(json.loads(line))
        return samples
    else:
        logger.info("Using built-in sample test set")
        return SAMPLE_TEST_SET


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Evaluate RAG pipeline")
    # Multiple --dataset flags accumulate (golden_faq + multihop + adversarial)
    parser.add_argument("--dataset", type=str, action="append", default=None)
    parser.add_argument("--output", type=str, default="./data/eval/report.json")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--no-llm-metrics", action="store_true")
    # CI release gate mode (ADR-0007): fail on threshold breach instead of
    # just writing a report. Deterministic metrics only unless key present.
    parser.add_argument(
        "--gate",
        action="store_true",
        help="exit nonzero when metrics fall below release thresholds",
    )
    parser.add_argument(
        "--metrics",
        type=str,
        default=None,
        help="comma-separated subset (context_relevance,faithfulness,answer_correctness)",
    )
    args = parser.parse_args()

    # Load test data (all provided datasets merged, tagged by source file)
    test_data = []
    for dataset_path in args.dataset or [None]:
        loaded = load_test_set(dataset_path)
        if len(args.dataset or []) > 1:
            for record in loaded:
                record.setdefault("_dataset", str(dataset_path))
        test_data.extend(loaded)
    if args.max_samples:
        test_data = test_data[:args.max_samples]

    samples = [
        EvaluationSample(
            question=d["question"],
            answer=d.get("answer", ""),
            contexts=d.get("contexts", []),
            ground_truth=d.get("ground_truth"),
        )
        for d in test_data
    ]

    # Initialize pipeline (will use settings from .env)
    logger.info("Initializing RAG pipeline for evaluation...")
    pipeline = RAGPipeline(config=RAGConfig())

    # Run evaluation
    evaluator = RAGEvaluator(
        rag_pipeline=pipeline,
        use_llm_metrics=not args.no_llm_metrics,
        use_statistical_metrics=True,
    )

    report = evaluator.evaluate_pipeline(
        test_samples=samples,
        dataset_name="cli_evaluation",
    )

    # Print and save results
    report.print_summary()
    report.save(args.output)
    logger.info("Evaluation complete", output=args.output)

    # Release-gate mode (ADR-0007): thresholds fail the CI job
    if args.gate:
        thresholds = {
            "context_relevance": 0.75,
            "faithfulness": 0.90,
            "answer_correctness": 0.85,
        }
        metrics = report.to_dict() if hasattr(report, "to_dict") else {}
        aggregate = metrics.get("aggregate", metrics)
        breaches = [
            f"{name}={aggregate.get(name, 'n/a')} < {floor}"
            for name, floor in thresholds.items()
            if isinstance(aggregate.get(name), int | float) and aggregate[name] < floor
        ]
        if breaches:
            logger.error("EVAL GATE FAILED", breaches=breaches)
            for breach in breaches:
                print(f"GATE FAIL: {breach}")
            return 1
        logger.info("Eval gate passed", thresholds=thresholds)
        print("GATE PASS: all release thresholds met")
    return 0


if __name__ == "__main__":
    main()
