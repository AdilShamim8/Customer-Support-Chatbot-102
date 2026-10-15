"""
RAG Evaluation Metrics Implementation.
Covers the three core RAG evaluation dimensions:
  1. Context Relevance  - Are retrieved chunks relevant to the query?
  2. Faithfulness       - Is the answer grounded in the retrieved context?
  3. Answer Correctness - Is the answer factually correct vs ground truth?

Also implements:
  - Answer Relevance    - Does the answer address the question?
  - Citation Precision  - Are cited sources actually used?
  - ROUGE / BERTScore   - Lexical and semantic similarity
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import structlog

from src.generation.llm_client import (
    BaseLLMClient,
    LLMClientFactory,
    LLMRequest,
    Message,
    MessageRole,
)

logger = structlog.get_logger(__name__)


# ─── Metric Result Structures ─────────────────────────────────────────────────

@dataclass
class MetricScore:
    """A single metric evaluation result."""
    metric_name: str
    score: float                        # 0.0 to 1.0
    reasoning: str = ""
    details: dict = field(default_factory=dict)
    passed: bool = True                 # score >= threshold

    def to_dict(self) -> dict:
        return {
            "metric": self.metric_name,
            "score": round(self.score, 4),
            "reasoning": self.reasoning,
            "details": self.details,
            "passed": self.passed,
        }


@dataclass
class EvaluationSample:
    """
    A single RAG evaluation sample.
    All fields needed to evaluate one Q&A interaction.
    """
    question: str
    answer: str                          # Model's generated answer
    contexts: list[str]                  # Retrieved context chunks
    ground_truth: Optional[str] = None  # Reference answer (for correctness)
    question_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Complete evaluation result for one sample."""
    sample: EvaluationSample
    scores: dict[str, MetricScore] = field(default_factory=dict)
    overall_score: float = 0.0
    passed: bool = True

    def add_score(self, score: MetricScore) -> None:
        self.scores[score.metric_name] = score

    def compute_overall(
        self,
        weights: Optional[dict[str, float]] = None,
    ) -> float:
        """Compute weighted average of all metric scores."""
        if not self.scores:
            return 0.0

        default_weights = {
            "context_relevance": 0.25,
            "faithfulness": 0.35,
            "answer_relevance": 0.20,
            "answer_correctness": 0.20,
        }
        weights = weights or default_weights

        total_weight = 0.0
        weighted_sum = 0.0

        for metric_name, score in self.scores.items():
            w = weights.get(metric_name, 0.1)
            weighted_sum += score.score * w
            total_weight += w

        self.overall_score = weighted_sum / total_weight if total_weight > 0 else 0.0
        self.passed = self.overall_score >= 0.7
        return self.overall_score

    def to_dict(self) -> dict:
        return {
            "question": self.sample.question,
            "answer": self.sample.answer,
            "overall_score": round(self.overall_score, 4),
            "passed": self.passed,
            "scores": {
                name: score.to_dict()
                for name, score in self.scores.items()
            },
        }


# ─── LLM-Based Metric Evaluators ─────────────────────────────────────────────

class LLMJudge:
    """
    LLM-as-judge evaluator.
    Uses an LLM to score RAG outputs on various dimensions.
    This is the standard approach used by RAGAS and DeepEval.
    """

    CONTEXT_RELEVANCE_PROMPT = """\
Evaluate how relevant the retrieved context is to the given question.

Question: {question}

Retrieved Context:
{context}

Score the relevance on a scale of 0.0 to 1.0:
- 1.0: Context directly and completely addresses the question
- 0.7: Context mostly relevant with some irrelevant parts
- 0.5: Context partially relevant
- 0.3: Context mostly irrelevant
- 0.0: Context completely irrelevant

Respond with JSON:
{{
  "score": <float 0.0-1.0>,
  "reasoning": "<brief explanation>",
  "relevant_sentences": ["<sentence 1>", "..."],
  "irrelevant_sentences": ["<sentence 1>", "..."]
}}"""

    FAITHFULNESS_PROMPT = """\
Evaluate whether the answer is fully supported by the provided context.
The answer should not contain information not present in the context.

Context:
{context}

Question: {question}

Answer: {answer}

For each claim in the answer, determine if it is supported by the context.

Respond with JSON:
{{
  "score": <float 0.0-1.0>,
  "reasoning": "<brief explanation>",
  "supported_claims": ["<claim 1>", "..."],
  "unsupported_claims": ["<claim 1>", "..."],
  "hallucinated": <true/false>
}}"""

    ANSWER_RELEVANCE_PROMPT = """\
Evaluate whether the answer directly addresses the customer's question.

Question: {question}

Answer: {answer}

Score on a scale of 0.0 to 1.0:
- 1.0: Answer completely and directly addresses the question
- 0.7: Answer mostly addresses the question
- 0.5: Answer partially addresses the question
- 0.3: Answer is tangentially related
- 0.0: Answer does not address the question at all

Respond with JSON:
{{
  "score": <float 0.0-1.0>,
  "reasoning": "<brief explanation>",
  "addressed_aspects": ["<aspect 1>", "..."],
  "missing_aspects": ["<aspect 1>", "..."]
}}"""

    ANSWER_CORRECTNESS_PROMPT = """\
Compare the generated answer to the ground truth answer.
Evaluate factual correctness and completeness.

Question: {question}

Ground Truth Answer: {ground_truth}

Generated Answer: {answer}

Score on a scale of 0.0 to 1.0:
- 1.0: Perfectly correct and complete
- 0.7: Mostly correct with minor gaps or inaccuracies
- 0.5: Partially correct
- 0.3: Mostly incorrect
- 0.0: Completely wrong

Respond with JSON:
{{
  "score": <float 0.0-1.0>,
  "reasoning": "<brief explanation>",
  "correct_facts": ["<fact 1>", "..."],
  "incorrect_facts": ["<fact 1>", "..."],
  "missing_facts": ["<fact 1>", "..."]
}}"""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or LLMClientFactory.create_default()

    def _evaluate(
        self,
        prompt: str,
        metric_name: str,
        threshold: float = 0.7,
    ) -> MetricScore:
        """Call LLM judge and parse the result."""
        try:
            request = LLMRequest(
                messages=[
                    Message(
                        role=MessageRole.SYSTEM,
                        content=(
                            "You are an objective evaluator for AI systems. "
                            "Always respond with valid JSON only."
                        ),
                    ),
                    Message(role=MessageRole.USER, content=prompt),
                ],
                temperature=0.0,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            response = self.llm.complete(request)
            result = json.loads(response.content)

            score = float(result.get("score", 0.0))
            score = max(0.0, min(1.0, score))   # Clamp to [0, 1]

            return MetricScore(
                metric_name=metric_name,
                score=score,
                reasoning=result.get("reasoning", ""),
                details={k: v for k, v in result.items() if k != "reasoning"},
                passed=score >= threshold,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(
                "LLM judge parsing failed",
                metric=metric_name,
                error=str(e),
            )
            return MetricScore(
                metric_name=metric_name,
                score=0.0,
                reasoning=f"Evaluation failed: {str(e)}",
                passed=False,
            )

    def evaluate_context_relevance(
        self,
        question: str,
        contexts: list[str],
        threshold: float = 0.7,
    ) -> MetricScore:
        """
        Evaluate if retrieved contexts are relevant to the question.
        Scores each context and averages.
        """
        if not contexts:
            return MetricScore(
                metric_name="context_relevance",
                score=0.0,
                reasoning="No context retrieved",
                passed=False,
            )

        scores = []
        for ctx in contexts[:5]:   # Evaluate top 5 contexts
            prompt = self.CONTEXT_RELEVANCE_PROMPT.format(
                question=question,
                context=ctx[:1500],
            )
            score = self._evaluate(prompt, "context_relevance", threshold)
            scores.append(score.score)

        avg_score = np.mean(scores) if scores else 0.0

        return MetricScore(
            metric_name="context_relevance",
            score=float(avg_score),
            reasoning=f"Average relevance across {len(scores)} contexts",
            details={
                "individual_scores": scores,
                "num_contexts": len(contexts),
            },
            passed=avg_score >= threshold,
        )

    def evaluate_faithfulness(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        threshold: float = 0.8,
    ) -> MetricScore:
        """
        Evaluate if the answer is grounded in the retrieved context.
        Critical metric - hallucination detection.
        """
        combined_context = "\n\n---\n\n".join(contexts[:5])

        prompt = self.FAITHFULNESS_PROMPT.format(
            context=combined_context[:3000],
            question=question,
            answer=answer,
        )

        score = self._evaluate(prompt, "faithfulness", threshold)

        # Faithfulness has higher threshold - must be grounded
        if score.details.get("hallucinated"):
            score.score = min(score.score, 0.4)
            score.passed = False

        return score

    def evaluate_answer_relevance(
        self,
        question: str,
        answer: str,
        threshold: float = 0.7,
    ) -> MetricScore:
        """Evaluate if the answer is relevant to the question."""
        prompt = self.ANSWER_RELEVANCE_PROMPT.format(
            question=question,
            answer=answer,
        )
        return self._evaluate(prompt, "answer_relevance", threshold)

    def evaluate_answer_correctness(
        self,
        question: str,
        answer: str,
        ground_truth: str,
        threshold: float = 0.7,
    ) -> MetricScore:
        """
        Evaluate factual correctness against ground truth.
        Requires ground truth labels.
        """
        prompt = self.ANSWER_CORRECTNESS_PROMPT.format(
            question=question,
            ground_truth=ground_truth,
            answer=answer,
        )
        return self._evaluate(prompt, "answer_correctness", threshold)


# ─── Statistical Metrics ──────────────────────────────────────────────────────

class StatisticalMetrics:
    """
    Non-LLM statistical metrics.
    Fast, deterministic, no API calls required.
    """

    def rouge_score(
        self,
        prediction: str,
        reference: str,
    ) -> MetricScore:
        """
        ROUGE-L score: Longest Common Subsequence overlap.
        Good proxy for answer completeness.
        """
        try:
            from rouge_score import rouge_scorer
            scorer = rouge_scorer.RougeScorer(
                ["rouge1", "rouge2", "rougeL"],
                use_stemmer=True,
            )
            scores = scorer.score(reference, prediction)

            rouge_l = scores["rougeL"].fmeasure
            rouge_1 = scores["rouge1"].fmeasure
            rouge_2 = scores["rouge2"].fmeasure

            return MetricScore(
                metric_name="rouge",
                score=rouge_l,
                reasoning=f"ROUGE-L: {rouge_l:.3f}",
                details={
                    "rouge_1": rouge_1,
                    "rouge_2": rouge_2,
                    "rouge_l": rouge_l,
                },
                passed=rouge_l >= 0.3,
            )
        except Exception as e:
            logger.error("ROUGE scoring failed", error=str(e))
            return MetricScore(
                metric_name="rouge",
                score=0.0,
                reasoning=f"ROUGE failed: {e}",
                passed=False,
            )

    def context_recall(
        self,
        answer: str,
        contexts: list[str],
    ) -> MetricScore:
        """
        Estimate what fraction of the answer content
        appears in the retrieved contexts.
        Token-overlap based approximation.
        """
        if not contexts or not answer:
            return MetricScore(
                metric_name="context_recall",
                score=0.0,
                reasoning="Empty answer or context",
                passed=False,
            )

        answer_tokens = set(re.findall(r'\b\w+\b', answer.lower()))
        context_text = " ".join(contexts)
        context_tokens = set(re.findall(r'\b\w+\b', context_text.lower()))

        # Remove stop words for meaningful overlap
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were",
            "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "shall", "can", "to",
            "of", "in", "on", "at", "by", "for", "with",
            "from", "up", "about", "into", "through", "and",
            "or", "but", "not", "that", "this", "it", "i",
        }

        answer_meaningful = answer_tokens - stop_words
        context_meaningful = context_tokens - stop_words

        if not answer_meaningful:
            return MetricScore(
                metric_name="context_recall",
                score=0.5,
                reasoning="Answer contains only stop words",
                passed=True,
            )

        overlap = answer_meaningful & context_meaningful
        recall = len(overlap) / len(answer_meaningful)

        return MetricScore(
            metric_name="context_recall",
            score=recall,
            reasoning=f"{len(overlap)}/{len(answer_meaningful)} answer tokens in context",
            details={
                "answer_token_count": len(answer_meaningful),
                "context_token_count": len(context_meaningful),
                "overlap_count": len(overlap),
            },
            passed=recall >= 0.5,
        )

    def answer_length_score(
        self,
        answer: str,
        min_words: int = 20,
        max_words: int = 500,
    ) -> MetricScore:
        """
        Score answer length appropriateness.
        Too short = unhelpful, too long = overwhelming.
        """
        word_count = len(answer.split())

        if word_count < min_words:
            score = word_count / min_words
            reasoning = f"Answer too short ({word_count} words, min {min_words})"
        elif word_count > max_words:
            excess = (word_count - max_words) / max_words
            score = max(0.5, 1.0 - excess * 0.5)
            reasoning = f"Answer too long ({word_count} words, max {max_words})"
        else:
            score = 1.0
            reasoning = f"Answer length appropriate ({word_count} words)"

        return MetricScore(
            metric_name="answer_length",
            score=score,
            reasoning=reasoning,
            details={"word_count": word_count},
            passed=min_words <= word_count <= max_words,
        )

    def citation_precision(
        self,
        answer: str,
        source_titles: list[str],
    ) -> MetricScore:
        """
        Check if cited sources in the answer are from retrieved sources.
        """
        if not source_titles:
            return MetricScore(
                metric_name="citation_precision",
                score=1.0,
                reasoning="No sources to validate",
                passed=True,
            )

        # Check if answer mentions source titles
        answer_lower = answer.lower()
        cited = [
            title for title in source_titles
            if title.lower() in answer_lower
            or any(
                word in answer_lower
                for word in title.lower().split()
                if len(word) > 4
            )
        ]

        if not cited:
            # Answer may be correct but not explicitly citing
            return MetricScore(
                metric_name="citation_precision",
                score=0.8,    # Penalize slightly but not fully
                reasoning="No explicit citations in answer",
                details={"available_sources": source_titles},
                passed=True,
            )

        precision = len(cited) / len(source_titles)
        return MetricScore(
            metric_name="citation_precision",
            score=min(1.0, precision + 0.2),  # Bonus for any citation
            reasoning=f"Cited {len(cited)}/{len(source_titles)} sources",
            details={
                "cited_sources": cited,
                "available_sources": source_titles,
            },
            passed=True,
        )