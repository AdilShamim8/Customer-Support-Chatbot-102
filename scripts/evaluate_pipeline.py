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
from src.pipeline.rag_pipeline import RAGPipeline, RAGConfig

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


def load_test_set(path: Optional[str]) -> list[dict]:
    if path and Path(path).exists():
        samples = []
        with open(path, "r", encoding="utf-8") as f:
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
    parser.add_argument("--dataset", type=str, default=None)
    parser.add_argument("--output", type=str, default="./data/eval/report.json")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--no-llm-metrics", action="store_true")
    args = parser.parse_args()

    # Load test data
    test_data = load_test_set(args.dataset)
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


if __name__ == "__main__":
    from typing import Optional
    main()